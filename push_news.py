#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日科技 推送
流程: 分板块抓取 RSS -> 各板块用 DeepSeek 总结成详细报道 -> Server酱 推送到微信

板块 (共 3 个):
  一、科技新闻        (8 条)
  二、Vibe Coding     (8 条)
  三、AI 应用与动向   (10 条, 由原"AI 应用"与"AI 动向"合并)

去重策略:
  - 板块间 / 数据源间: 全局标题归一化去重, 同一新闻不会出现在两个板块。
  - 跨天历史: 已推送过的标题记入 history.json, 之后 N 天内不再重复推送。
"""

import os
import re
import sys
import time
import html
import json
import datetime as dt
import urllib.parse
from email.utils import parsedate_to_datetime

import requests
import feedparser

# ----------------------------------------------------------------------------
# 配置区: 板块与对应的 RSS 源
# 说明: 脚本运行在 GitHub 的海外服务器上, 因此 Google News RSS 稳定可用。
# ----------------------------------------------------------------------------
def gn(query: str, hl: str, gl: str, ceid: str) -> str:
    """构造 Google News 搜索 RSS 链接。"""
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + f"&hl={hl}&gl={gl}&ceid={ceid}"
    )

TOPICS = [
    {
        "section": "一、科技新闻",
        "n": 8,
        "feeds": [
            gn("科技 OR 半导体 OR 芯片 OR 智能手机 OR 科技创新 when:2d", "zh-CN", "CN", "CN:zh"),
            gn("technology OR semiconductor OR smartphone OR chip when:2d", "en-US", "US", "US:en"),
            "https://www.jiqizhixin.com/rss",
            "https://www.theverge.com/rss/index.xml",
        ],
    },
    {
        "section": "二、Vibe Coding",
        "n": 8,
        "feeds": [
            gn("vibe coding OR AI coding OR Cursor IDE OR agentic coding when:2d", "en-US", "US", "US:en"),
            gn("Vibe Coding OR AI编程 OR Cursor OR 智能编程 when:2d", "zh-CN", "CN", "CN:zh"),
        ],
    },
    {
        "section": "三、AI 应用与动向",
        "n": 10,
        "feeds": [
            # 原 "AI 应用"
            gn("AI应用 OR AI代理 OR AI工具 OR 大模型应用 when:2d", "zh-CN", "CN", "CN:zh"),
            gn("AI application OR AI agent OR new AI tool when:2d", "en-US", "US", "US:en"),
            # 原 "AI 动向"
            gn("大模型 OR 人工智能 融资 OR 开源大模型 when:2d", "zh-CN", "CN", "CN:zh"),
            gn("OpenAI OR Anthropic OR Google AI OR LLM release when:2d", "en-US", "US", "US:en"),
        ],
    },
]

HOURS_BACK = int(os.getenv("HOURS_BACK", "48"))
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "3"))
HISTORY_FILE = os.getenv("HISTORY_FILE", "history.json")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY", "").strip()

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

BEIJING = dt.timezone(dt.timedelta(hours=8))


def log(msg: str) -> None:
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def normalize_key(s: str) -> str:
    """把标题归一化成去重键: 转小写、去空白与标点、保留中英文字符、取前 40 字。"""
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return s[:40]


def load_history():
    """读取历史记录(已推送标题), 并裁剪掉超过 HISTORY_DAYS 天的旧条目。返回 (key集合, 完整列表)。"""
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set(), []
    now = time.time()
    window = HISTORY_DAYS * 86400
    fresh = [e for e in data if now - float(e.get("t", 0)) < window]
    return set(e["k"] for e in fresh), fresh


def save_history(keys_new):
    """把本次推送的标题键追加进历史记录并写回文件。"""
    _, hist = load_history()
    now = time.time()
    for k in keys_new:
        hist.append({"k": k, "t": now})
    window = HISTORY_DAYS * 86400
    hist = [e for e in hist if now - float(e.get("t", 0)) < window]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        log(f"  历史记录写入失败(不影响推送): {ex}")


def entry_time(entry) -> dt.datetime:
    """尽量解析出条目发布时间, 失败则返回当前时间 (确保不被时间过滤误删)。"""
    for key in ("published", "updated"):
        val = entry.get(key)
        if val:
            try:
                d = parsedate_to_datetime(val)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=dt.timezone.utc)
                return d.astimezone(dt.timezone.utc)
            except Exception:
                pass
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return dt.datetime.fromtimestamp(time.mktime(val), tz=dt.timezone.utc)
            except Exception:
                pass
    return dt.datetime.now(dt.timezone.utc)


def fetch_topic(feeds):
    """抓取某板块的全部 RSS, 按时间过滤 + 源内去重, 返回(按时间倒序的)新闻列表。"""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=HOURS_BACK)
    seen_titles = set()
    items = []

    for url in feeds:
        try:
            log(f"  抓取: {url[:68]}...")
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            feed = feedparser.parse(resp.content)
            source = feed.feed.get("title", "未知来源")
            for e in feed.entries:
                title = html.unescape((e.get("title") or "").strip())
                link = (e.get("link") or "").strip()
                if not title or not link:
                    continue
                pub = entry_time(e)
                if pub < cutoff:
                    continue
                key = title[:40]
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                items.append({"title": title, "link": link, "source": source, "time": pub})
        except Exception as ex:
            log(f"    跳过 (抓取失败): {ex}")

    items.sort(key=lambda x: x["time"], reverse=True)
    log(f"  该板块候选新闻 {len(items)} 条")
    return items


def summarize_topic(section: str, n: int, items):
    """调用 DeepSeek 把某板块新闻整理成详细的 Markdown 报道。"""
    if not items:
        return f"_{section}：今日暂无足够的新内容。_"

    news_text = "\n".join(
        f"{i+1}. 【{it['source']}】{it['title']}\n   链接: {it['link']}"
        for i, it in enumerate(items)
    )

    prompt = (
        f"你是一名资深科技媒体编辑。下面是关于「{section}」的今日新闻标题与链接，"
        "请整理成一份详细、有信息量的中文报道。要求：\n"
        "1. 用 Markdown 格式，每条独立成段并加粗标题；\n"
        "2. 每条用 2-4 句话具体说明：发生了什么、涉及哪些公司/人物/数据/产品、为什么重要；不要只复述标题；\n"
        "3. 保留原文链接，用 [原文](URL) 形式附在每条末尾；\n"
        f"4. 最多 {n} 条，不足则按实际条数；按重要性排序；相似内容合并为一条；\n"
        "5. 剔除纯营销软文、无实质信息的水稿；\n"
        "6. 开头用一两句话概述该领域今日走势。\n\n"
        f"新闻列表：\n{news_text}"
    )

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    log(f"  调用 DeepSeek 生成「{section}」...")
    resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    log(f"  「{section}」生成完成")
    return content


def build_fallback(section: str, items):
    """DeepSeek 不可用时, 直接拼接原始新闻列表。"""
    lines = [f"**{section}**（未经 AI 总结，原始列表）\n"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. **{it['title']}**  \n   来源：{it['source']} · [原文]({it['link']})")
    return "\n".join(lines)


def push_serverchan(title: str, desp: str) -> None:
    """通过 Server酱 Turbo 推送到微信。"""
    if not SERVERCHAN_SENDKEY:
        log("未配置 SERVERCHAN_SENDKEY, 跳过推送。以下为内容预览：")
        print(desp)
        return
    url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
    resp = requests.post(url, data={"title": title, "desp": desp}, timeout=30)
    log(f"Server酱 推送响应: {resp.status_code} {resp.text[:120]}")
    resp.raise_for_status()


def main():
    now_bj = dt.datetime.now(BEIJING)
    today = now_bj.strftime("%Y-%m-%d")
    log(f"开始生成「每日科技 {today}」...")

    history_set, _ = load_history()
    global_seen = set()
    dispatched = []
    sections = []
    any_content = False

    for topic in TOPICS:
        n = topic["n"]
        log(f"板块: {topic['section']} (目标 {n} 条)")
        raw = fetch_topic(topic["feeds"])

        picked = []
        for it in raw:
            k = normalize_key(it["title"])
            if k in global_seen or k in history_set:
                continue
            global_seen.add(k)
            picked.append(it)
            if len(picked) >= n:
                break

        if picked:
            any_content = True
        dispatched.extend(normalize_key(it["title"]) for it in picked)

        if DEEPSEEK_API_KEY:
            try:
                content = summarize_topic(topic["section"], n, picked)
            except Exception as ex:
                log(f"  DeepSeek 调用失败, 使用原始列表兜底: {ex}")
                content = build_fallback(topic["section"], picked) if picked else f"_{topic['section']}：今日暂无足够的新内容。_"
        else:
            log("  未配置 DEEPSEEK_API_KEY, 使用原始列表。")
            content = build_fallback(topic["section"], picked) if picked else f"_{topic['section']}：今日暂无足够的新内容。_"

        sections.append(f"## {topic['section']}\n\n{content}")

    # 无论推送是否成功, 都记录已处理的新闻, 避免跨天重复
    save_history(dispatched)

    if not any_content:
        log("今日所有板块均未抓取到新闻, 结束。")
        push_serverchan(f"每日科技 {today}", "今日未抓取到符合条件的新闻。")
        return

    body = "\n\n".join(sections)
    footer = (
        f"\n\n---\n_自动生成于 {now_bj.strftime('%Y-%m-%d %H:%M')}（北京时间）· 每日科技_"
    )
    push_serverchan(f"每日科技 {today}", body + footer)
    log("全部完成 ✅")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        log(f"运行出错: {ex}")
        sys.exit(1)
