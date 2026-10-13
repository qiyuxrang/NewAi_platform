"""Bounded public search using the providers already supported by OpenClaw.

Only fixed technical categories leave the server, never project source text.
Search results are untrusted public references, not project facts.
"""
import json
import os
import re
from http.client import HTTPException
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request

from django.conf import settings
from django.utils import timezone

from .product_knowledge_service import _open, decode
from .product_service import ProductError, digest


DOMAINS = {
    "网络与安全": ("网络", "交换机", "路由", "防火墙", "等保", "信息安全"),
    "视频监控": ("视频监控", "摄像", "安防", "录像"),
    "综合布线": ("布线", "光纤", "网线"),
    "计算与存储": ("服务器", "存储", "数据中心", "虚拟化"),
    "供配电": ("配电", "供电", "ups", "电源"),
    "暖通": ("空调", "暖通", "制冷"),
    "音视频会议": ("会议", "音响", "广播", "显示屏", "拼接屏"),
    "门禁": ("门禁", "出入口"),
    "工业控制": ("工业控制", "自控", "plc", "scada"),
    "软件平台": ("软件", "数据库", "业务系统", "平台"),
}

ERRORS = {
    "web_search_unconfigured": "知识证据不足，联网搜索尚未启用或缺少服务密钥；配置后可重新检索。",
    "web_search_unavailable": "联网搜索暂时不可用，已保存知识库来源；请稍后重新检索。",
    "web_search_invalid_response": "联网搜索返回格式不符合协议，已暂停生成；可重新检索或补充资料。",
    "web_search_no_hits": "联网搜索未获得覆盖技术缺口的有效来源；请补充资料或重新检索。",
}


def fail(code):
    raise ProductError(code, ERRORS[code], 409)


def _mentions(content, words):
    return any(bool(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", content))
               if word.isascii() else word in content for word in words)


def technical_domains(payload):
    # Classification stays local. Only labels from DOMAINS can become a query.
    local = "\n".join(str(payload.get(key, "")) for key in ("project", "requirements", "background"))
    local += "\n" + "\n".join(str(item.get("name", "")) for item in payload.get("items", []) if isinstance(item, dict))
    local = local.casefold()
    return [label for label, words in DOMAINS.items() if _mentions(local, words)]


def evidence_coverage(payload, sources):
    domains = technical_domains(payload)
    content = "\n".join(str(source.get("title", "")) + "\n" + str(source.get("text", ""))
                         for source in sources if source.get("text", "").strip()).casefold()
    covered = [label for label in domains if _mentions(content, DOMAINS[label])]
    missing = [label for label in domains if label not in covered]
    # ponytail: broad domain heuristic; human blueprint review checks exact applicability.
    # Half the broad domains avoids demanding an individual hit for every equipment term.
    sufficient = bool(content) and (not domains or len(covered) * 2 >= len(domains))
    return {"method": "broad_technical_domains_v1", "domains": domains,
            "covered_domains": covered, "missing_domains": missing, "sufficient": sufficient}


def public_queries(coverage):
    labels = coverage["missing_domains"] or coverage["domains"]
    return [(" ".join(labels) if labels else "信息化系统集成") + " 技术设计规范 验收要求"]


def configuration():
    provider = getattr(settings, "PRODUCT_WEB_SEARCH_PROVIDER", "tavily")
    name = getattr(settings, "PRODUCT_WEB_SEARCH_TOKEN_ENV", "") or {
        "tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}.get(provider, "")
    if (getattr(settings, "PRODUCT_WEB_SEARCH_ENABLED", False) is not True
            or provider not in {"tavily", "brave"}
            or not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name)):
        fail("web_search_unconfigured")
    token = os.environ.get(name, "")
    if not 10 <= len(token) <= 512 or any(ord(char) < 33 or ord(char) > 126 for char in token):
        fail("web_search_unconfigured")
    return provider, token


def _source(row, provider, query, retrieved_at):
    if not isinstance(row, dict):
        fail("web_search_invalid_response")
    title, url = row.get("title"), row.get("url")
    content = row.get("content" if provider == "tavily" else "description")
    if (not isinstance(title, str) or not title.strip() or len(title) > 1000
            or not isinstance(content, str) or not content.strip() or len(content) > 20000
            or not isinstance(url, str) or not 1 <= len(url) <= 2048
            or any((ord(char) < 32 and char not in "\n\r\t") or 0xD800 <= ord(char) <= 0xDFFF for char in title + content)
            or any(ord(char) < 33 or 0xD800 <= ord(char) <= 0xDFFF for char in url)):
        fail("web_search_invalid_response")
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        parsed.port
    except ValueError:
        fail("web_search_invalid_response")
    return {"id": "web:" + digest({"url": url})[:32], "provider": provider,
            "title": title[:300], "url": url, "text": content[:4000],
            "retrieved_at": retrieved_at, "query_hash": digest({"query": query}),
            "fact_scope": "PUBLIC_REFERENCE", "reference_only": True,
            "untrusted": True, "source_trust": "UNKNOWN", "timeliness": "UNKNOWN"}


def search_public_references(queries):
    """One explicit invocation, one bounded provider request; no automatic retry."""
    if not isinstance(queries, list) or len(queries) != 1 or not isinstance(queries[0], str):
        fail("web_search_invalid_response")
    labels = queries[0].removesuffix(" 技术设计规范 验收要求").split(" ")
    if (not queries[0].endswith(" 技术设计规范 验收要求") or not 1 <= len(labels) <= len(DOMAINS)
            or any(label not in {*DOMAINS, "信息化系统集成"} for label in labels)):
        fail("web_search_invalid_response")
    provider, token = configuration()
    query = queries[0]
    if provider == "tavily":
        request = Request("https://api.tavily.com/search", method="POST",
            data=json.dumps({"query": query, "max_results": 6, "search_depth": "basic",
                             "include_answer": False, "include_raw_content": False}).encode("utf-8"),
            headers={"Authorization": "Bearer " + token, "Accept": "application/json", "Content-Type": "application/json"})
    else:
        request = Request("https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": 6}),
            headers={"X-Subscription-Token": token, "Accept": "application/json"})
    deadline = monotonic() + 20
    try:
        with _open(request, 10) as response:
            if response.status != 200:
                fail("web_search_unavailable")
            parts, size = [], 0
            while True:
                if monotonic() >= deadline:
                    fail("web_search_unavailable")
                part = response.read1(min(8192, 262145 - size))
                if monotonic() >= deadline:
                    fail("web_search_unavailable")
                if not isinstance(part, bytes):
                    fail("web_search_invalid_response")
                if not part:
                    break
                parts.append(part)
                size += len(part)
                if size > 262144:
                    fail("web_search_invalid_response")
    except HTTPError as error:
        error.close()
        fail("web_search_unavailable")
    except (URLError, OSError, TimeoutError, HTTPException):
        fail("web_search_unavailable")
    try:
        payload = decode(b"".join(parts))
    except ProductError:
        fail("web_search_invalid_response")
    if not isinstance(payload, dict):
        fail("web_search_invalid_response")
    rows = payload.get("results") if provider == "tavily" else payload.get("web", {}).get("results") if isinstance(payload.get("web"), dict) else None
    if not isinstance(rows, list) or len(rows) > 20:
        fail("web_search_invalid_response")
    retrieved_at = timezone.now().isoformat()
    unique = {}
    for row in rows:
        source = _source(row, provider, query, retrieved_at)
        unique.setdefault(source["id"], source)
    return list(unique.values())[:6]
