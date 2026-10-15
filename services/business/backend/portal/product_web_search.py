"""Bounded public search using the providers already supported by OpenClaw.

Only fixed professional categories leave the server, never project source text.
Search results are untrusted public references, not project facts.
"""
import ipaddress
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

# Each topic needs both facets in retrieved text; titles/queries alone are not evidence.
FEASIBILITY_TOPICS = {
    "政策规范与编制依据": (("政策", "法规", "编制依据"), ("标准", "规范", "通用大纲")),
    "需求规模与方案论证": (("需求分析", "必要性", "需求预测"), ("规模", "方案比选", "方案论证")),
    "实施采购与运营管理": (("实施", "工期", "进度"), ("招标", "采购", "运营", "运维")),
    "投资估算与资金筹措": (("投资估算", "概算", "费用构成"), ("资金筹措", "资金来源", "资金安排")),
    "绩效效益与风险评价": (("绩效", "效益", "节能", "环境影响"), ("风险", "敏感性", "社会稳定")),
}
FEASIBILITY_SUFFIX = " 可行性研究报告 编制指南 方法 适用条件"

ERRORS = {
    "web_search_unconfigured": "知识证据不足，联网搜索尚未启用或缺少有效服务配置；配置后可重新检索。",
    "web_search_unavailable": "联网搜索暂时不可用，已保存知识库来源；请稍后重新检索。",
    "web_search_invalid_response": "联网搜索返回格式不符合协议，已暂停生成；可重新检索或补充资料。",
    "web_search_no_hits": "联网搜索未获得覆盖写作参考缺口的有效来源；请补充资料或重新检索。",
}


def fail(code):
    raise ProductError(code, ERRORS[code], 409)


def _mentions(content, words):
    return any(bool(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", content))
               if word.isascii() else word in content for word in words)


def technical_domains(payload):
    # Classification stays local. Only labels from DOMAINS can become a query.
    local = "\n".join(str(payload.get(key, "")) for key in ("project", "requirements", "background"))
    local += "\n" + "\n".join(str(item.get(key, "")) for item in payload.get("items", [])
                               if isinstance(item, dict) for key in ("name", "specification", "source_section"))
    local += "\n" + "\n".join(str(source.get("text", "")) for source in payload.get("source_materials", [])
                               if isinstance(source, dict))
    local = local.casefold()
    return [label for label, words in DOMAINS.items() if _mentions(local, words)]


def evidence_coverage(payload, sources, *, feasibility=False):
    domains = technical_domains(payload)
    if feasibility:
        content = "\n".join(str(source.get("text", "")) for source in sources
                            if source.get("content_kind") != "search_title").casefold()
    else:
        content = "\n".join(str(source.get("title", "")) + "\n" + str(source.get("text", ""))
                             for source in sources if source.get("text", "").strip()).casefold()
    covered = [label for label in domains if _mentions(content, DOMAINS[label])]
    missing = [label for label in domains if label not in covered]
    # ponytail: broad domain heuristic; human blueprint review checks exact applicability.
    # Half the broad domains avoids demanding an individual hit for every equipment term.
    sufficient = bool(content) and (not domains or len(covered) * 2 >= len(domains))
    result = {"method": "broad_technical_domains_v1", "domains": domains,
              "covered_domains": covered, "missing_domains": missing, "sufficient": sufficient}
    if feasibility:
        topics = [label for label, facets in FEASIBILITY_TOPICS.items()
                  if all(_mentions(content, words) for words in facets)]
        result.update(method="feasibility_public_topics_v2", writing_topics=list(FEASIBILITY_TOPICS),
                      covered_writing_topics=topics,
                      missing_writing_topics=[label for label in FEASIBILITY_TOPICS if label not in topics],
                      sufficient=sufficient and len(topics) == len(FEASIBILITY_TOPICS))
        # ponytail: keyword facets check reference coverage, not legal validity or project applicability; model/human review must verify both.
    return result


def public_queries(coverage):
    if "missing_writing_topics" in coverage:
        labels = coverage["missing_writing_topics"] + coverage["missing_domains"]
        # At most three requests for actual gaps, without injecting IT into generic projects.
        size = max(1, (len(labels) + 2) // 3)
        return [" ".join(labels[index:index + size]) + FEASIBILITY_SUFFIX
                for index in range(0, len(labels), size)]
    labels = coverage["missing_domains"] or coverage["domains"]
    return [(" ".join(labels) if labels else "信息化系统集成") + " 技术设计规范 验收要求"]


def configuration():
    provider = getattr(settings, "PRODUCT_WEB_SEARCH_PROVIDER", "tavily")
    if getattr(settings, "PRODUCT_WEB_SEARCH_ENABLED", False) is not True:
        fail("web_search_unconfigured")
    if provider == "searxng":
        base_url = getattr(settings, "PRODUCT_WEB_SEARCH_SEARXNG_URL", "")
        if not _valid_searxng_url(base_url):
            fail("web_search_unconfigured")
        return provider, base_url.rstrip("/")
    name = getattr(settings, "PRODUCT_WEB_SEARCH_TOKEN_ENV", "") or {
        "tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}.get(provider, "")
    if (provider not in {"tavily", "brave"}
            or not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name)):
        fail("web_search_unconfigured")
    token = os.environ.get(name, "")
    if not 10 <= len(token) <= 512 or any(ord(char) < 33 or ord(char) > 126 for char in token):
        fail("web_search_unconfigured")
    return provider, token


def _valid_searxng_url(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 2048
            or any(ord(char) <= 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
        return False
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"https", "http"} or not parsed.netloc or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "@" in parsed.netloc or parsed.netloc.endswith(":") or "?" in value or "#" in value):
            return False
        port = parsed.port
        if port == 0:
            return False
        host = parsed.hostname.rstrip(".").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
            numeric_host = re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host) is not None
            labels = host.split(".")
            if ("%" in host or len(host) > 253 or not all(
                    len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
                    for label in labels)):
                return False
        if parsed.scheme == "http":
            if address is not None:
                private = address.is_private or address.is_loopback
            else:
                # Docker/Kubernetes service names and reserved local DNS suffixes.
                private = not numeric_host and (
                    "." not in host or host.endswith((".localhost", ".local", ".internal", ".test", ".svc"))
                    or host.endswith(".cluster.local") or host.endswith(".home.arpa"))
            if not private:
                return False
        return True
    except ValueError:
        return False


def _source(row, provider, query, retrieved_at):
    if not isinstance(row, dict):
        fail("web_search_invalid_response")
    title, url = row.get("title"), row.get("url")
    content = row.get("content" if provider in {"tavily", "searxng"} else "description")
    title_only = False
    if provider == "searxng" and (not isinstance(content, str) or not content.strip()):
        content = title if isinstance(title, str) else ""
        title_only = True
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
            "untrusted": True, "source_trust": "UNKNOWN", "timeliness": "UNKNOWN",
            "content_kind": "search_title" if title_only else "search_snippet",
            "content_truncated": len(content) > 4000,
            "applicability": "PENDING_HUMAN"}


def search_public_references(queries):
    """At most three allow-listed professional queries; no automatic retry."""
    if (not isinstance(queries, list) or not 1 <= len(queries) <= 3
            or any(not isinstance(query, str) for query in queries)):
        fail("web_search_invalid_response")
    for query in queries:
        suffix = FEASIBILITY_SUFFIX if query.endswith(FEASIBILITY_SUFFIX) else " 技术设计规范 验收要求"
        allowed = {*DOMAINS, *FEASIBILITY_TOPICS} if suffix == FEASIBILITY_SUFFIX else {*DOMAINS, "信息化系统集成"}
        labels = query.removesuffix(suffix).split(" ")
        if (not query.endswith(suffix) or not 1 <= len(labels) <= len(allowed)
                or any(label not in allowed for label in labels)):
            fail("web_search_invalid_response")
    sources = {}
    for query in queries:
        for source in _provider_search(query):
            sources.setdefault(source["id"], source)
    return list(sources.values())


def search_public_query(query):
    """Explicitly opted-in current user question; never history or source material."""
    if (not isinstance(query, str) or not query.strip() or len(query) > 2000
            or any((ord(char) < 32 and char not in "\r\n\t") or 0xD800 <= ord(char) <= 0xDFFF for char in query)):
        fail("web_search_invalid_response")
    return _provider_search(query)


def _provider_search(query):
    provider, credential = configuration()
    if provider == "tavily":
        request = Request("https://api.tavily.com/search", method="POST",
            data=json.dumps({"query": query, "max_results": 6, "search_depth": "basic",
                             "include_answer": False, "include_raw_content": False}).encode("utf-8"),
            headers={"Authorization": "Bearer " + credential, "Accept": "application/json", "Content-Type": "application/json"})
    elif provider == "brave":
        request = Request("https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": 6}),
            headers={"X-Subscription-Token": credential, "Accept": "application/json"})
    else:
        request = Request(credential.rstrip("/") + "/search?" + urlencode({"q": query, "format": "json"}),
            headers={"Accept": "application/json"})
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
    if provider == "brave":
        rows = payload.get("web", {}).get("results") if isinstance(payload.get("web"), dict) else None
    else:
        rows = payload.get("results")
    if not isinstance(rows, list) or (provider != "searxng" and len(rows) > 20):
        fail("web_search_invalid_response")
    retrieved_at = timezone.now().isoformat()
    unique = {}
    # ponytail: scan at most 50 SearXNG rows; enough for normal result pages while keeping malformed feeds bounded.
    for row in rows[:50] if provider == "searxng" else rows:
        try:
            source = _source(row, provider, query, retrieved_at)
        except ProductError:
            if provider != "searxng":
                raise
            continue
        unique.setdefault(source["id"], source)
        if provider == "searxng" and len(unique) >= 6:
            break
    return list(unique.values())[:6]
