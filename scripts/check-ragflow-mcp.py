"""Read-only MCP initialize/tools-list probe; never prints credentials/catalogs."""

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def decode_rpc(raw):
    text = raw.decode("utf-8")
    if text.lstrip().startswith("data:") or "\ndata:" in text:
        records = [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith("data:")]
        data = next(item for item in records if isinstance(item, dict) and "result" in item)
    else:
        data = json.loads(text)
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or not isinstance(data.get("result"), dict):
        raise ValueError("not a successful MCP response")
    return data["result"]


def probe(url, token):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = "Bearer " + token
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def post(payload):
        request = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with opener.open(request, timeout=5) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if payload.get("id") is None:
                return {}
            if not any(mime in content_type for mime in ("application/json", "text/event-stream")):
                raise ValueError("endpoint is not MCP JSON/SSE")
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("MCP metadata response exceeds probe limit")
            session = response.headers.get("Mcp-Session-Id")
            if session:
                headers["Mcp-Session-Id"] = session
            return decode_rpc(raw)

    try:
        initialized = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "MultiUserClaw-readonly-check", "version": "1"}}})
        headers["MCP-Protocol-Version"] = initialized["protocolVersion"]
        post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        catalog = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = catalog.get("tools")
        if not isinstance(tools, list) or not all(isinstance(t, dict) and isinstance(t.get("name"), str) for t in tools):
            raise ValueError("invalid tools/list response")
        names = [t["name"] for t in tools]
        return {"available": "ragflow_retrieval" in names, "status": "mcp_ready" if "ragflow_retrieval" in names else "unexpected_tools",
                "protocol_version": initialized["protocolVersion"], "tools": names,
                "portal_document_authorization_verified": False}
    except HTTPError as exc:
        return {"available": False, "status": "authentication_required" if exc.code in {401, 403} else "http_error", "http_status": exc.code}
    except (URLError, OSError) as exc:
        return {"available": False, "status": "connection_failed", "error_type": type(exc).__name__}
    except (ValueError, KeyError, StopIteration, UnicodeError):
        return {"available": False, "status": "invalid_mcp_response"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:19982/mcp")
    parser.add_argument("--token-env", default="RAGFLOW_MCP_API_KEY")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = {"protocolVersion": "2024-11-05"}
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
        assert decode_rpc(raw) == result
        assert decode_rpc(b"event: message\ndata: " + raw + b"\n\n") == result
        for value in (b"<html>login</html>", b'{"jsonrpc":"2.0","error":{"code":-1}}'):
            try:
                decode_rpc(value)
                raise AssertionError("non-MCP response accepted")
            except ValueError:
                pass
        print("MCP response checks passed")
        return 0
    parsed = urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("probe URL must be a local MCP endpoint without credentials")
    result = probe(args.url, os.environ.get(args.token_env, ""))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
