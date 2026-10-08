"""Read-only MCP endpoint discovery. Never runs a retrieval or changes datasets."""
import json
import sys
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:19880"
for path in ("/", "/mcp", "/sse"):
    request = urllib.request.Request(base + path, headers={"Accept": "application/json, text/event-stream"})
    try:
        with opener.open(request, timeout=3) as response:
            print(json.dumps({"path": path, "status": response.status,
                              "type": response.headers.get("Content-Type")}, ensure_ascii=False))
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                print(response.readline().decode(errors="replace").strip())
                print(response.readline().decode(errors="replace").strip())
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print(json.dumps({"path": path, "error": str(error)[:120]}, ensure_ascii=False))

payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26", "capabilities": {},
    "clientInfo": {"name": "aicompany-migration-probe", "version": "1.0"}}}
for path in ("/mcp", "/api/v1/mcp"):
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read(8192)
            try:
                data = json.loads(raw)
                print(json.dumps({"initialize": path, "status": response.status, "result": data.get("result"),
                                  "error": data.get("error")}, ensure_ascii=False))
            except ValueError:
                print(json.dumps({"initialize": path, "status": response.status,
                                  "type": response.headers.get("Content-Type")}, ensure_ascii=False))
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print(json.dumps({"initialize": path, "error": str(error)[:120]}, ensure_ascii=False))
