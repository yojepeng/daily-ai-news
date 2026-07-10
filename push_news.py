#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日科技 推送
流程: 分 4 个板块抓取 RSS -> 各板块用 DeepSeek 总结成详细报道 -> Server酱 推送到微信

板块:
  一、科技新闻  二、Vibe Coding  三、AI 应用  四、AI 动向  (每个板块各 8 条)

依赖环境变量 (在 GitHub Secrets 中配置):
  DEEPSEEK_API_KEY   : DeepSeek 平台的 API Key
  SERVERCHAN_SENDKEY : Server酱 Turbo 的 SendKey

可选环境变量:
  ITEMS_PER_TOPIC : 每个板块的新闻条数上限, 默认 8
  HOURS_BACK      : 只保留最近多少小时内的新闻, 默认 48
"""

import os
import sys
import time
import html
import datetime as dt
import urllib.parse
from email.utils import parsedate_to_datetime

import requests
import feedparser

# ----------------------------------------------------------------------------
# 配置区: 4 个板块, 各用 Google News 搜索 RSS (中/英) 聚合
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
        "feeds": [
            gn("科技 OR 半导体 OR 芯片 OR 智能手机 OR 科技创新 when:2d", "zh-CN", "CN", "CN:zh"),
            gn("technology OR semiconductor OR smartphone OR chip when:2d", "en-US", "US", "US:en"),
            "https://www.jiqizhixin.com/rss",
            "https://www.theverge.com/rss/index.xml",
        ],
    },
    {
        "section": "二、Vibe Coding",
        "feeds": [
            gn("vibe coding OR AI coding OR Cursor IDE OR agentic coding when:2d", "en-US", "US", "US:en"),
            gn("Vibe Coding OR AI编程 OR Cursor OR 智能编程 when:2d", "zh-CN", "CN", "CN:zh"),
        ],
    },
    {
        "section": "三、AI 应用",
        "feeds": [
            gn("AI应用 OR AI代理 OR AI工具 OR 大模型应用 when:2d", "zh-CN", "CN", "CN:zh"),
            gn("AI application OR AI agent OR new AI tool when:2d", "en-US", "US", "US:en"),
        ],
    },
    {
        "section": "四、AI 动向",
        "feeds": [
            gn("大模型 OR 人工智能 融资 OR 开源大模型 when:2d", "zh-CN", "CN", "CN:zh"),
            gn("OpenAI OR Anthropic OR Google AI OR LLM release when:2d", "en-US", "US", "US:en"),
        ],
    },
]

ITEMS_PER_TOPIC = int(os.getenv("ITEMS_PER_TOPIC", "8"))
HOURS_BACK = int(os.getenv("HOURS_BACK", "48"))

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
    """抓取一个板块的所有 RSS, 按时间过滤 + 去重, 返回该板块新闻列表(上限 ITEMS_PER_TOPIC)。"""
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
    log(f"  该板块有效新闻 {len(items)} 条, 取前 {ITEMS_PER_TOPIC} 条")
    return items[:ITEMS_PER_TOPIC]


def summarize_topic(section: str, items):
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
        "4. 最多 8 条，按重要性排序；相似内容合并为一条；\n"
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

    sections = []
    any_content = False

    for topic in TOPICS:
        log(f"板块: {topic['section']}")
        items = fetch_topic(topic["feeds"])
        if items:
            any_content = True

        if DEEPSEEK_API_KEY:
            try:
                content = summarize_topic(topic["section"], items)
            except Exception as ex:
                log(f"  DeepSeek 调用失败, 使用原始列表兜底: {ex}")
                content = build_fallback(topic["section"], items) if items else f"_{topic['section']}：今日暂无足够的新内容。_"
        else:
            log("  未配置 DEEPSEEK_API_KEY, 使用原始列表。")
            content = build_fallback(topic["section"], items) if items else f"_{topic['section']}：今日暂无足够的新内容。_"

        sections.append(f"## {topic['section']}\n\n{content}")

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
