# -*- coding: utf-8 -*-
"""Crawl4AI 冒烟测试：用本机 Edge 抓一个搜索页，确认渲染与抽取可用。

用法：  .venv\\Scripts\\python.exe tools\\crawl_smoke.py "关键词"
"""
import asyncio
import os
import sys
import urllib.parse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "tmp")


async def main():
    kw = sys.argv[1] if len(sys.argv) > 1 else "海康威视 网络摄像机 200万 筒型"
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(kw, safe="")

    browser = BrowserConfig(
        browser_type="chromium",
        chrome_channel="msedge",   # 复用本机 Edge，不下载 Chromium
        headless=True,
        text_mode=True,
        viewport_width=1366,
        viewport_height=900,
        user_agent_mode="random",
        verbose=False,
    )
    run = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000)

    async with AsyncWebCrawler(config=browser) as crawler:
        res = await crawler.arun(url, config=run)

    print("success:", res.success, "| status:", res.status_code)
    md = res.markdown or ""
    print("markdown 长度:", len(md))
    ext = (res.links or {}).get("external") or []
    print("外链数:", len(ext))
    for l in ext[:12]:
        print("   ", (l.get("href") or "")[:110])

    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "bing_smoke.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(md)
    print("→", p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
