"""Read-only assistant tools. Authority and outbound queries stay on the server."""
import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
from html.parser import HTMLParser
from http.client import HTTPException
import re
import json
import threading
from time import monotonic
from urllib.parse import urlsplit

from django.utils import timezone

from . import product_knowledge_service as knowledge
from . import product_web_search as web
from .product_service import ProductError


def schema(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": list(required),
                       "additionalProperties": False}}}


STRING = {"type": "string", "minLength": 1, "maxLength": 2000}
TOOLS = [
    schema("knowledge_search", "检索当前账号已授权的企业知识；可以换关键词继续检索。不能指定或扩大授权范围。",
           {"query": STRING}, ("query",)),
    schema("knowledge_list", "列出已授权知识文档的名称和标识，用于查找或浏览可读取的文件。",
           {"dataset_id": STRING, "page": {"type": "integer", "minimum": 1, "maximum": 20}}),
    schema("knowledge_read", "分页读取已授权文档正文，须使用知识库返回的真实标识，不接受文件路径。",
           {"dataset_id": STRING, "document_id": STRING,
            "page": {"type": "integer", "minimum": 1, "maximum": 500}}, ("dataset_id", "document_id")),
    schema("calculate", "精确计算算术表达式，支持加减乘除、括号和有限整数次幂；不执行程序。",
           {"expression": {"type": "string", "minLength": 1, "maxLength": 256}}, ("expression",)),
    schema("plan", "复杂任务可记录最多6条简短执行步骤或更新完成状态；只描述实际工作，不输出私有推理。",
           {"steps": {"type": "array", "minItems": 1, "maxItems": 6,
                      "items": {"type": "string", "maxLength": 160}}}, ("steps",)),
]
PUBLIC_QUERY_TERMS = ("招标公告", "招标", "中标公告", "中标结果", "中标", "建设进展", "在建", "开工",
                      "工程项目", "工程", "项目", "官网", "官方网站", "公共资源交易", "政府", "业主",
                      "最新", "近期", "新闻", "公告", "公开", "发布日期")
PUBLIC_QUERY_GUIDANCE = ("公开检索必须保留本次问题的主题原词，仅可补充通用词：" + "、".join(PUBLIC_QUERY_TERMS)
                         + "，以及当前年份或当前年月日（数字或中文日期）；不能添加企业资料、历史内容或其他模型补词。")
PUBLIC_TOOLS = [
    schema("web_search", "搜索公开网页；" + PUBLIC_QUERY_GUIDANCE + "可调整空白、标点和词序；省略query则搜索本次问题。",
           {"query": STRING}),
    schema("web_fetch", "读取本次搜索结果或用户本次明确给出的HTTPS网页。不能访问内网、任意新网址或修改URL参数。读取失败表示正文未读，只能使用已有搜索摘要，不要重试同址。",
           {"url": {"type": "string", "minLength": 1, "maxLength": 2048}}, ("url",)),
]
QUERY_SEPARATORS = re.compile(r"[\s,，。；、？！!?;：\"'“”‘’()（）\[\]【】{}]+")


def calculate(expression):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 256:
        raise ValueError("invalid expression")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 64:
        raise ValueError("expression too complex")

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = Decimal(ast.get_source_segment(expression, node).replace("_", ""))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.Div):
                value = left / right
            elif isinstance(node.op, ast.Pow) and right == int(right) and abs(right) <= 12:
                value = left ** int(right)
            else:
                raise ValueError("unsupported operator")
        else:
            raise ValueError("unsupported expression")
        if not value.is_finite() or abs(value) > Decimal("1e30") or value and value.adjusted() < -100:
            raise ValueError("number out of range")
        return value

    with localcontext() as context:
        context.prec = 28
        return format(evaluate(tree.body), "f")


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def fetch_public_page(url):
    # Reuse the gateway's DNS validation and pinned TLS socket, including rebinding protection.
    from model_gateway.transport import _resolve, _PinnedHTTPSConnection
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment or "\\" in url
            or any(ord(char) < 33 or ord(char) > 126 for char in url)):
        raise ValueError("only public HTTPS pages are supported")
    deadline = monotonic() + 20
    connection = _PinnedHTTPSConnection(parsed.hostname, _resolve(parsed.hostname, deadline), deadline)
    timer = threading.Timer(20, connection.abort)
    timer.daemon = True
    timer.start()
    try:
        connection.request("GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                           headers={"Accept": "text/html, text/plain", "Accept-Encoding": "identity",
                                    "User-Agent": "EnterpriseAssistant/1.0"})
        response = connection.getresponse()
        if (response.status != 200 or response.getheader("Content-Encoding", "identity") != "identity"
                or response.getheader("Content-Type", "").split(";", 1)[0].lower() not in {"text/html", "text/plain"}):
            raise ValueError("page unavailable, redirected or unsupported format")
        raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024 or monotonic() >= deadline:
            raise ValueError("page exceeds reading limit")
        encoding = response.headers.get_content_charset() or "utf-8"
        content = raw.decode(encoding, errors="replace")
        if response.getheader("Content-Type", "").startswith("text/html"):
            parser = _PageText()
            parser.feed(content)
            content = " ".join(parser.parts)
        content = re.sub(r"[ \t]+", " ", content).strip()[:10000]
        if not content:
            raise ValueError("empty page")
        return content
    finally:
        timer.cancel()
        connection.close()


class AssistantTools:
    def __init__(self, question, scope, config, *, web_search, recheck):
        self.question, self.scope, self.config = question, scope, config
        self.web_search, self.recheck = web_search, recheck
        self.sources = []
        self.allowed_urls = set(re.findall(r"https://[^\s<>\"'，。；）)]+", question))
        self.calls = 0
        self._results = {}
        self.no_new_evidence = 0

    @property
    def schemas(self):
        available = bool(self.config and self.scope.get("datasets"))
        return [item for item in TOOLS if available or not item["function"]["name"].startswith("knowledge_")] + (
            PUBLIC_TOOLS if self.web_search else [])

    def _public_query(self, value):
        query = knowledge.text(value, 2000).strip()
        today = timezone.localdate()
        dates = {str(today.year): str(today.year), f"{today.year}年": str(today.year),
                 today.strftime("%Y-%m"): today.strftime("%Y-%m"), today.isoformat(): today.isoformat(),
                 f"{today.year}年{today.month}月": today.strftime("%Y-%m"),
                 f"{today.year}年{today.month}月{today.day}日": today.isoformat()}
        additions = set(PUBLIC_QUERY_TERMS) | dates.keys()
        pattern = "(" + "|".join(re.escape(term) for term in sorted(additions, key=lambda term: (-len(term), term))) + ")"
        # Only fixed public additions may accompany literal current-question terms; never fall back to the whole question.
        terms = list(dict.fromkeys(part for term in QUERY_SEPARATORS.split(query) if term
                                  for part in re.split(pattern, term if term in self.question else term.rstrip(".:")) if part))
        projected = []
        for term in terms:
            if term in self.question or term in additions:
                projected.append(term)
                continue
            # Only rejoin literal Chinese phrases; bound segmentation and forbid single-character assembly.
            if len(term) > 64 or not re.fullmatch(r"[\u4e00-\u9fff]+", term):
                return None
            segments = [None] * (len(term) + 1)
            segments[0] = []
            for end in range(2, len(term) + 1):
                for start in range(end - 1):
                    if segments[start] is not None and term[start:end] in self.question:
                        segments[end] = segments[start] + [term[start:end]]
                        break
            if segments[-1] is None:
                return None
            projected.extend(segments[-1])
        terms = list(dict.fromkeys(projected))
        if (not terms or any(term not in self.question and term not in additions for term in terms)
                or not any(term in self.question and term not in additions for term in terms)):
            return None
        terms = list(dict.fromkeys(dates.get(term, term) for term in terms))
        return " ".join(sorted(terms, key=lambda term: (0, self.question.index(term)) if term in self.question else (1, term)))

    def _request_key(self, name, arguments):
        args = dict(arguments)
        if name == "web_search":
            query = self._public_query(args.get("query", self.question))
            if query is not None:
                args["query"] = sorted(set(filter(None, QUERY_SEPARATORS.split(query))))
        elif name == "knowledge_search":
            args["query"] = " ".join(args["query"].split())
        elif name in {"knowledge_read", "knowledge_list"}:
            args.setdefault("page", 1)
        return name, json.dumps(args, ensure_ascii=False, sort_keys=True)

    def _check_knowledge_configuration(self, name):
        if not name.startswith("knowledge_"):
            return
        try:
            if knowledge.configuration() != self.config:
                raise ProductError("knowledge_unavailable", "知识服务配置已变更，当前请求不能继续读取；可说明限制后回答。", 503)
        except ProductError:
            self._results = {key: result for key, result in self._results.items()
                             if not key[0].startswith("knowledge_")}
            raise

    def _feedback(self, name, result, *, cached=False, new_evidence=0):
        if name in {"knowledge_search", "knowledge_read", "web_search", "web_fetch"}:
            self.no_new_evidence = 0 if new_evidence else self.no_new_evidence + 1
            result = {**result, "tool_status": {"cached": cached, "new_evidence": new_evidence,
                "consecutive_no_new_evidence": self.no_new_evidence,
                "guidance": ("相同请求已执行，复用返回结果；不要重复调用。" if cached else "") + (
                    "新增来源不代表证据充分；请检查是否覆盖问题。" if new_evidence else
                    "本次未新增证据。若仍有明确缺口，可改用不同合法检索词或未读页面；否则据实回答并说明未证实部分。")}}
        elif cached:
            result = {**result, "tool_status": {"cached": True, "guidance": "相同请求已执行，请复用结果，不要重复调用。"}}
        return result

    def add_source(self, source):
        kind = source.get("type", "knowledge")
        key = (kind, source.get("url")) if kind == "web" else (
            kind, source.get("dataset_id"), source.get("document_id"), source.get("content"))
        for previous in self.sources:
            previous_key = (previous["type"], previous.get("url")) if kind == "web" else (
                previous["type"], previous.get("dataset_id"), previous.get("document_id"), previous.get("content"))
            if key == previous_key:
                if len(source.get("content", "")) > len(previous.get("content", "")):
                    previous["content"] = source["content"]
                return previous
        if len(self.sources) >= 24:
            raise ProductError("source_budget", "本轮参考来源数量已达上限，请停止新增检索，基于已有来源回答并说明资料缺口；无需更换参数重试。", 409)
        item = {**source, "id": ("W" if kind == "web" else "K") + str(len(self.sources) + 1), "type": kind}
        self.sources.append(item)
        return item

    def execute(self, name, arguments):
        self.recheck()
        self.calls += 1
        if self.calls > 12:
            raise ProductError("assistant_budget", "本次工具调用已达上限，请缩小问题后重试。", 409)
        definition = next((item["function"] for item in self.schemas if item["function"]["name"] == name), None)
        if (definition is None or not isinstance(arguments, dict)
                or set(arguments) - set(definition["parameters"]["properties"])
                or set(definition["parameters"]["required"]) - set(arguments)):
            raise ProductError("invalid_response", "智能助手工具请求无效。", 502)
        for key, value in arguments.items():
            spec = definition["parameters"]["properties"][key]
            if (spec["type"] == "string" and (not isinstance(value, str) or not 1 <= len(value) <= spec["maxLength"])
                    or spec["type"] == "integer" and (type(value) is not int or not spec["minimum"] <= value <= spec["maximum"])
                    or spec["type"] == "array" and (not isinstance(value, list) or not 1 <= len(value) <= 6)):
                raise ProductError("invalid_response", "智能助手工具参数无效。", 502)
        key = None
        before = {item["id"]: item["content"] for item in self.sources}
        previous_sources = self.sources
        self.sources = deepcopy(self.sources)
        try:
            self._check_knowledge_configuration(name)
            key = self._request_key(name, arguments)
            if key in self._results:
                self.recheck()
                self._check_knowledge_configuration(name)
                return self._feedback(name, deepcopy(self._results[key]), cached=True)
            result = self._execute(name, arguments)
            self.recheck()
            self._check_knowledge_configuration(name)
        except (ValueError, SyntaxError, InvalidOperation, ArithmeticError, LookupError):
            self.sources = previous_sources
            self.recheck()
            result = {"error": "invalid_tool_arguments", "detail": "参数或页面不符合读取范围，请调整后重试。"}
        except ProductError as error:
            self.sources = previous_sources
            self.recheck()  # Revocation and lease failures always terminate, never become model context.
            if error.status in (401, 403):
                raise
            result = {"error": error.code, "detail": error.detail}
        if key is not None:
            self._results[key] = deepcopy(result)
        new_evidence = sum(before.get(item["id"]) != item["content"] for item in self.sources)
        return self._feedback(name, result, new_evidence=new_evidence)

    def _execute(self, name, args):
        if name.startswith("knowledge_") and not (self.config and self.scope.get("datasets")):
            raise ProductError("forbidden", "当前请求没有可用的授权知识工具。", 403)
        datasets = self.scope["datasets"]
        if name == "knowledge_search":
            query = knowledge.text(args["query"], 2000)
            return {"sources": [self.add_source({**item, "type": "knowledge"})
                                for item in knowledge.retrieve(query, [], self.scope, self.config)]}
        if name == "knowledge_list":
            dataset = args.get("dataset_id")
            if dataset is not None and dataset not in datasets:
                raise ValueError("dataset reference is outside the current scope")
            page = args.get("page", 1)
            if type(page) is not int or not 1 <= page <= 20:
                raise ValueError
            result = []
            for identifier in ([dataset] if dataset else datasets):
                self.recheck()
                documents = knowledge.list_documents(identifier, datasets[identifier], page, 20, "", self.config)
                self.recheck()
                result.append({"dataset_id": identifier, **documents})
            return {"datasets": result}
        if name == "knowledge_read":
            dataset, document = args["dataset_id"], args["document_id"]
            if not isinstance(dataset, str) or not isinstance(document, str) or document not in datasets.get(dataset, []):
                raise ValueError("document reference is outside the current scope")
            page = args.get("page", 1)
            if type(page) is not int or not 1 <= page <= 500:
                raise ValueError
            result = knowledge.list_chunks(dataset, document, page, 4, self.config)
            return {"sources": [self.add_source({"type": "knowledge", "dataset_id": dataset,
                "document_id": document, "title": result["document"]["name"], "content": chunk["content"][:6000]})
                for chunk in result["chunks"]], "page": page, "has_more": result["has_more"]}
        if name == "calculate":
            return {"expression": args["expression"], "value": calculate(args["expression"])}
        if name == "plan":
            steps = args["steps"]
            if not isinstance(steps, list) or not 1 <= len(steps) <= 6:
                raise ValueError
            return {"steps": [knowledge.text(step, 160) for step in steps]}
        if name == "web_search":
            query = self._public_query(args.get("query", self.question))
            if query is None:
                return {"error": "public_query_only", "detail": "搜索词包含本轮未提供的词，已停止本次搜索。", "guidance": PUBLIC_QUERY_GUIDANCE
                    + "如果主题仅在历史对话中，请先用中文请用户补充本轮可公开检索的关键词；不得自动外发历史企业资料，也不要改搜完整问题。"}
            found = web.search_public_query(query)
            self.allowed_urls.update(item["url"] for item in found)
            return {"sources": [self.add_source({"type": "web", "title": item["title"],
                    "url": item["url"], "content": item["text"][:2000]}) for item in found],
                    "reference_only": True, "summary_only": True}
        if name == "web_fetch":
            from model_gateway.errors import GatewayError
            url = args["url"]
            if not isinstance(url, str) or url not in self.allowed_urls:
                raise ValueError
            try:
                content = fetch_public_page(url)
            except (OSError, ValueError, LookupError, HTTPException, GatewayError):
                return {"error": "web_fetch_unavailable", "page_read": False,
                        "summary_available": any(item["type"] == "web" and item.get("url") == url for item in self.sources),
                        "detail": "网页正文未读取，可能需要跳转或登录；如已有搜索摘要仅作摘要引用，不能声称已核验全文；不要重试同一网址。"}
            # Gateway transport exceptions deliberately do not include target or credential values.
            return {"sources": [self.add_source({"type": "web", "title": urlsplit(url).hostname,
                    "url": url, "content": content[:6000]})], "reference_only": True, "page_read": True}
        raise ValueError
