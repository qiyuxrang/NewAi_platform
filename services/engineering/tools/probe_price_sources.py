# -*- coding: utf-8 -*-
"""探测哪些价格源能被抓取：用本机 Edge 渲染后统计『价格字样』并保存 markdown。

用法：  .venv\\Scripts\\python.exe tools\\probe_price_sources.py "关键词"
"""
import asyncio
import os
import re
import sys
import urllib.parse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "tmp", "sources")

Q = urllib.parse.quote

SOURCES = [
    ("京东搜索",   lambda k: "https://search.jd.com/Search?keyword=" + Q(k)),
    ("震坤行",     lambda k: "https://www.zkh.com/search.html?keyword=" + Q(k)),
    ("西域",       lambda k: "https://www.ehsy.com/search?keyword=" + Q(k)),
    ("百度爱采购", lambda k: "https://b2b.baidu.com/s?q=" + Q(k)),
    ("慧聪",       lambda k: "https://s.hc360.com/?w=" + Q(k) + "&mc=seller"),
    ("马可波罗",   lambda k: "https://www.makepolo.com/search/?q=" + Q(k)),
    ("中关村在线", lambda k: "https://detail.zol.com.cn/index.php?c=SearchList&keyword=" + Q(k)),
    ("百度",       lambda k: "https://www.baidu.com/s?wd=" + Q(k)),
    ("谷歌",       lambda k: "https://www.google.com/search?q=" + Q(k)),
    ("必应",       lambda k: "https://cn.bing.com/search?q=" + Q(k)),
    ("京东商品页", lambda k: "https://www.jd.com/"),
    ("中国政府采购网", lambda k: "https://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index=1"
                          "&bidSort=0&pinMu=0&bidType=0&dbselect=bidx&timeType=6&kw=" + Q(k)),
]

PRICE_RE = re.compile(r"(?:¥|￥)\s?\d{1,6}(?:\.\d{1,2})?|\d{1,6}(?:\.\d{1,2})?\s*元")


async def main():
    args = sys.argv[1:]
    timeout_s = 15
    only = None
    if "--timeout" in args:
        i = args.index("--timeout")
        timeout_s = int(args[i + 1])
        del args[i:i + 2]
    if "--only" in args:
        i = args.index("--only")
        only = [x.strip() for x in args[i + 1].split(",") if x.strip()]
        del args[i:i + 2]
    kw = args[0] if args else "网络摄像机 200万 POE"
    sources = [s for s in SOURCES if not only or s[0] in only]
    browser = BrowserConfig(
        browser_type="chromium",
        chrome_channel="msedge",
        headless=True,
        text_mode=True,
        viewport_width=1366,
        viewport_height=900,
        user_agent_mode="random",
        verbose=False,
        ignore_https_errors=True,
    )
    run = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=timeout_s * 1000,
        wait_until="domcontentloaded",
    )
    os.makedirs(OUT, exist_ok=True)

    async with AsyncWebCrawler(config=browser) as crawler:
        results = []
        for name, build in sources:
            t0 = __import__("time").time()
            try:
                # crawl4ai 自带的 page_timeout 对部分站点不生效，外面再套一层硬超时
                res = await asyncio.wait_for(
                    crawler.arun(build(kw), config=run), timeout=timeout_s + 5)
            except asyncio.TimeoutError:
                res = None
            except Exception as e:  # noqa: BLE001
                res = None
                print("  %s 异常：%s" % (name, str(e)[:60]))
            print("  %-12s %5.1fs %s" % (name, __import__("time").time() - t0,
                                         "超时" if res is None else "完成"))
            sys.stdout.flush()
            results.append(res)

    print("%-12s %-6s %-8s %9s %8s  %s" % ("源", "成功", "状态", "markdown", "价格字样", "标题"))
    for (name, _), res in zip(sources, results):
        if res is None:
            print("%-12s %-6s %-8s %9s %8s" % (name, "超时", "-", "-", "-"))
            continue
        md = getattr(res, "markdown", "") or ""
        hits = len(PRICE_RE.findall(md))
        title = ""
        m = re.search(r"<title>(.*?)</title>", getattr(res, "html", "") or "", re.S)
        if m:
            title = m.group(1).strip()[:40]
        print("%-12s %-6s %-8s %9d %8d  %s" % (
            name, getattr(res, "success", "?"), getattr(res, "status_code", "?"),
            len(md), hits, title))
        p = os.path.join(OUT, "%s.md" % name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
