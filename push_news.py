#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日 AI 新闻推送
流程: 抓取 AI 资讯 RSS 聚合 -> DeepSeek 总结成日报 -> Server酱 推送到微信

依赖环境变量 (在 GitHub Secrets 中配置):
  DEEPSEEK_API_KEY   : DeepSeek 平台的 API Key
  SERVERCHAN_SENDKEY : Server酱 Turbo 的 SendKey

可选环境变量:
  MAX_ITEMS   : 参与总结的新闻条数上限, 默认 15
  HOURS_BACK  : 只保留最近多少小时内的新闻, 默认 48
"""

import os
import sys
import time
import html
import datetime as dt
from email.utils import parsedate_to_datetime

import requests
import feedparser

# ----------------------------------------------------------------------------
# 配置区: 新闻来源 (可自行增删)
# 说明: 脚本运行在 GitHub 的海外服务器上, 因此 Google News RSS 稳定可用。
# ----------------------------------------------------------------------------
RSS_FEEDS = [
    # Google News 中文「人工智能」聚合 (海外服务器可直连, 更新快)
    "https://news.google.com/rss/search?q=%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD+OR+%E5%A4%A7%E6%A8%A1%E5%9E%8B+when:2d&hl=zh-CN&gl=CN&ceid=CN:zh",
    # Google News 英文 AI 聚合
    "https://news.google.com/rss/search?q=artificial+intelligence+OR+LLM+when:2d&hl=en-US&gl=US&ceid=US:en",
    # 机器之心
    "https://www.jiqizhixin.com/rss",
    # MIT Technology Review - AI
    "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    # Hugging Face 博客
    "https://huggingface.co/blog/feed.xml",
]

MAX_ITEMS = int(os.getenv("MAX_ITEMS", "15"))
HOURS_BACK = int(os.getenv("HOURS_BACK", "48"))

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY", "").strip()

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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


def fetch_news():
    """抓取所有 RSS, 按时间过滤 + 去重, 返回新闻列表。"""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=HOURS_BACK)
    seen_titles = set()
    items = []

    for url in RSS_FEEDS:
        try:
            log(f"抓取: {url[:70]}...")
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
            log(f"  跳过 (抓取失败): {ex}")

    items.sort(key=lambda x: x["time"], reverse=True)
    log(f"共获取有效新闻 {len(items)} 条, 取前 {MAX_ITEMS} 条")
    return items[:MAX_ITEMS]


def summarize_with_deepseek(items):
    """调用 DeepSeek 把新闻整理成一份中文日报 (Markdown)。"""
    if not items:
        return None

    news_text = "\n".join(
        f"{i+1}. 【{it['source']}】{it['title']}\n   链接: {it['link']}"
        for i, it in enumerate(items)
    )

    prompt = (
        "你是一名资深 AI 行业分析师。下面是今天抓取到的 AI 相关新闻标题与链接，"
        "请挑选其中最重要、最有信息量的内容，整理成一份简洁的中文《每日 AI 要闻》。要求：\n"
        "1. 用 Markdown 格式，每条 1-2 句话概括核心信息，不要照抄标题；\n"
        "2. 相似或重复的新闻合并；营销软文、无实质内容的条目请剔除；\n"
        "3. 每条末尾用 Markdown 链接格式附上原文链接，如 [原文](URL)；\n"
        "4. 最多保留 8 条，按重要性排序；\n"
        "5. 开头写一句今日总体趋势的概览。\n\n"
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

    log("调用 DeepSeek 生成日报...")
    resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    log("日报生成完成")
    return content


def build_fallback(items):
    """DeepSeek 不可用时, 直接拼接原始新闻列表。"""
    lines = ["> 今日 AI 要闻（未经 AI 总结，原始列表）\n"]
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
    today = dt.datetime.now().strftime("%Y-%m-%d")
    items = fetch_news()

    if not items:
        log("今日未抓取到新闻, 结束。")
        push_serverchan(f"每日 AI 要闻 {today}", "今日未抓取到符合条件的新闻。")
        return

    digest = None
    if DEEPSEEK_API_KEY:
        try:
            digest = summarize_with_deepseek(items)
        except Exception as ex:
            log(f"DeepSeek 调用失败, 使用原始列表兜底: {ex}")
    else:
        log("未配置 DEEPSEEK_API_KEY, 使用原始列表。")

    if not digest:
        digest = build_fallback(items)

    footer = f"\n\n---\n_自动生成于 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · 每日 AI 新闻推送_"
    push_serverchan(f"每日 AI 要闻 {today}", digest + footer)
    log("全部完成 ✅")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        log(f"运行出错: {ex}")
        sys.exit(1)
