"""Experimental private RSS discovery; never a verified company-data source.

Fixed endpoint, explicit local-development opt-in, bounded requests, no retries,
redirects or challenge handling. Public-page acquisition keeps its separate DNS
pinned transport. No upstream implementation or result index is copied here.
"""
import ipaddress
import re
import ssl
from html.parser import HTMLParser
from http.client import HTTPException
from threading import Lock
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener, getproxies
from xml.etree import ElementTree

from django.conf import settings

from .product_knowledge_service import NoRedirect
from .product_service import ProductError

ENDPOINT = "https://www.bing.com/search"
MAX_BYTES = 262144
MAX_ITEMS = 50
MAX_RESULTS = 6
_rate_lock = Lock()
_last_request_at = None


def fail(code="web_search_invalid_response"):
    messages = {"web_search_unconfigured": "本地RSS搜索尚未明确启用或代理配置无效。",
                "web_search_unavailable": "公开RSS搜索暂不可用，未取得来源。",
                "web_search_invalid_response": "公开RSS响应或来源地址不符合读取范围。",
                "web_search_rate_limited": "公开RSS搜索请求过于频繁，请稍后重试。"}
    raise ProductError(code, messages[code], 429 if code == "web_search_rate_limited" else 409)


def configured():
    if (getattr(settings, "DEBUG", False) is not True
            or getattr(settings, "PRODUCT_WEB_SEARCH_BING_RSS_ENABLED", False) is not True):
        fail("web_search_unconfigured")
    return ENDPOINT


def _proxy_configuration():
    if getattr(settings, "PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY", False) is not True:
        return {}
    value = getproxies().get("https", "")
    try:
        proxy = urlsplit(value)
        if (proxy.scheme != "http" or not proxy.hostname or proxy.username is not None or proxy.password is not None
                or proxy.path not in {"", "/"} or proxy.query or proxy.fragment or proxy.port is None
                or not 1 <= proxy.port <= 65535 or any(ord(char) < 33 for char in value)):
            raise ValueError
        host = proxy.hostname
        if host == "localhost":
            host = "127.0.0.1"  # Do not re-resolve a proxy alias.
        address = ipaddress.ip_address(host)
        if not address.is_loopback:
            raise ValueError
        host = f"[{address}]" if address.version == 6 else str(address)
        return {"https": f"http://{host}:{proxy.port}"}
    except (ValueError, TypeError):
        fail("web_search_unconfigured")


def _open(request, timeout):
    # This opener is exclusive to the fixed Bing endpoint. Shared knowledge,
    # SearXNG and DNS-pinned public-page transports remain unchanged.
    target = urlsplit(request.full_url)
    if (target.scheme != "https" or target.hostname != "www.bing.com" or target.port not in (None, 443)
            or target.netloc not in {"www.bing.com", "www.bing.com:443"} or target.path != "/search"
            or target.fragment or request.get_method() != "GET"):
        fail("web_search_unconfigured")
    context = ssl.create_default_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    return build_opener(ProxyHandler(_proxy_configuration()), NoRedirect(), HTTPSHandler(context=context)).open(request, timeout=timeout)


class _Snippet(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _text(element):
    raw = "" if element is None else " ".join(element.itertext())
    if len(raw) > 20000:
        fail()
    parser = _Snippet()
    parser.feed(raw)
    return " ".join(" ".join(parser.parts).split())


def _public_link(value, deadline, checked_hosts):
    from model_gateway.errors import GatewayError
    from model_gateway.transport import _resolve
    try:
        parsed = urlsplit(value)
        if (not 1 <= len(value) <= 2048 or parsed.scheme not in {"https", "http"}
                or not parsed.hostname or parsed.username is not None or parsed.password is not None
                or any(ord(char) <= 32 or ord(char) >= 127 for char in value) or "\\" in value
                or parsed.port not in (None, 443 if parsed.scheme == "https" else 80)):
            raise ValueError
        # _resolve validates EVERY returned address against the gateway's public
        # IP policy and its finite DNS deadline, including mapped/reserved IPs.
        # This is discovery validation only; the later fetch resolves and pins
        # afresh and cannot inherit this result as a DNS authorization.
        host = parsed.hostname.rstrip(".").lower()
        if host not in checked_hosts:
            _resolve(host, deadline)
            checked_hosts.add(host)
        return value
    except (ValueError, GatewayError):
        fail()


def search(query):
    global _last_request_at
    configured()
    if (not isinstance(query, str) or not query.strip() or len(query) > 2000
            or any((ord(char) < 32 and char not in "\r\n\t") or 0xD800 <= ord(char) <= 0xDFFF for char in query)):
        fail()
    request = Request(ENDPOINT + "?" + urlencode({"q": query, "format": "rss"}),
                      headers={"Accept": "application/rss+xml, application/xml", "Accept-Encoding": "identity",
                               "User-Agent": "Baichuan-public-reference/1.0"})
    # The process makes at most one new request per second, without waiting,
    # retries or proxy/engine rotation. Existing job source budgets still apply.
    with _rate_lock:
        now = monotonic()
        if _last_request_at is not None and now - _last_request_at < 1:
            fail("web_search_rate_limited")
        _last_request_at = now
    deadline = monotonic() + 20
    try:
        with _open(request, 8) as response:
            if response.status != 200 or response.getheader("Content-Encoding", "identity").lower() != "identity":
                fail("web_search_unavailable")
            parts, size = [], 0
            while True:
                if monotonic() >= deadline:
                    fail("web_search_unavailable")
                part = response.read1(min(8192, MAX_BYTES + 1 - size))
                if monotonic() >= deadline:
                    fail("web_search_unavailable")
                if not isinstance(part, bytes):
                    fail()
                if not part:
                    break
                parts.append(part)
                size += len(part)
                if size > MAX_BYTES:
                    fail()
    except HTTPError as error:
        error.close()
        fail("web_search_unavailable")
    except (URLError, OSError, TimeoutError, HTTPException):
        fail("web_search_unavailable")
    raw = b"".join(parts)
    # RSS here must use UTF-8. Reject UTF-16/NUL and declarations BEFORE parsing
    # so internal/external entity expansion and DTD processing never occur.
    if b"\x00" in raw or re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I):
        fail()
    try:
        text = raw.decode("utf-8-sig")
        if "<?xml" in text and not re.match(r"\s*<\?xml[^?]*\?>", text):
            fail()
        root = ElementTree.fromstring(text)
    except (UnicodeError, ElementTree.ParseError, RecursionError):
        fail()
    channels = root.findall("channel")
    if root.tag != "rss" or root.get("version") != "2.0" or len(channels) != 1:
        fail()
    pending, nodes = [(root, 0)], 0
    while pending:
        element, depth = pending.pop()
        nodes += 1
        if depth > 12 or nodes > 2048:
            fail()
        pending.extend((child, depth + 1) for child in element)
    items = channels[0].findall("item")
    if len(items) > MAX_ITEMS:
        fail()
    results, seen, checked_hosts = [], set(), set()
    for item in items:
        if len(results) == MAX_RESULTS:
            break
        if any(len(item.findall(field)) != 1 for field in ("title", "link")) or len(item.findall("description")) > 1:
            fail()
        title, url = _text(item.find("title")), item.findtext("link", "").strip()
        if not title or len(title) > 1000:
            fail()
        url = _public_link(url, deadline, checked_hosts)
        content = _text(item.find("description"))
        if url not in seen:
            results.append({"title": title, "url": url, "content": content, "title_only": not bool(content)})
            seen.add(url)
    if monotonic() >= deadline:
        fail("web_search_unavailable")
    return results
