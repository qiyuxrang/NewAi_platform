"""Bounded, server-owned chapter and review contracts; no provider I/O."""

import json


_NAME = "chapter_contract_v1"
_FIELDS = ("chapter_id", "title", "paragraphs", "source_ids")
_FORMAT_LIMIT = 32768
_SOURCE_LIMIT = 256
_REVIEW_SPEC = {"passed": "boolean", "issues": ["string"]}
_GUIDE_SPEC = {**_REVIEW_SPEC, "guide_checks": [{
    "id": "exact-guide-requirement-id", "status": "covered/partial/not_seen/not_applicable/pending",
    "evidence": [{"chapter_id": "saved-chapter-id", "quote": "exact-sent-body-quote"}], "reason": "string"}]}


def _review_format(guide):
    properties = {"passed": {"type": "boolean"},
                  "issues": {"type": "array", "maxItems": 100,
                             "items": {"type": "string", "maxLength": 2000}}}
    if guide:
        evidence = {"type": "object", "properties": {
            "chapter_id": {"type": "string"}, "quote": {"type": "string", "minLength": 1, "maxLength": 2000}},
            "required": ["chapter_id", "quote"], "additionalProperties": False}
        properties["guide_checks"] = {"type": "array", "items": {
            "type": "object", "properties": {
                "id": {"type": "string"},
                "status": {"type": "string", "enum": ["covered", "partial", "not_seen", "not_applicable", "pending"]},
                "evidence": {"type": "array", "maxItems": 5, "items": evidence},
                "reason": {"type": "string", "minLength": 1, "maxLength": 2000}},
            "required": ["id", "status", "evidence", "reason"], "additionalProperties": False}}
    return {"type": "json_schema", "json_schema": {
        "name": "guide_review_contract_v1" if guide else "review_contract_v1", "strict": True,
        "schema": {"type": "object", "properties": properties,
                   "required": list(properties), "additionalProperties": False}}}


def review_response_format(schema):
    """Build a strict contract only for the two existing review specifications."""
    if type(schema) is not dict or (schema != _REVIEW_SPEC and schema != _GUIDE_SPEC):
        raise ValueError("invalid response format")
    return _review_format("guide_checks" in schema)


def _text(value, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("invalid response format")
    return value


def _sources(values):
    if type(values) is not list or not 1 <= len(values) <= _SOURCE_LIMIT:
        raise ValueError("invalid response format")
    result = [_text(value, 200) for value in values]
    if len(set(result)) != len(result):
        raise ValueError("invalid response format")
    return result


def _format(chapter_id, title, sources):
    return {"type": "json_schema", "json_schema": {
        "name": _NAME, "strict": True, "schema": {
            "type": "object", "properties": {
                "chapter_id": {"type": "string", "const": chapter_id},
                "title": {"type": "string", "const": title},
                "paragraphs": {"type": "array", "minItems": 1,
                               "items": {"type": "string"}},
                "source_ids": {"type": "array", "minItems": 1,
                               "items": {"type": "string", "enum": sources}},
            }, "required": list(_FIELDS), "additionalProperties": False,
        }}}


def chapter_response_format(chapter):
    """Build the one supported schema from an already approved chapter."""
    if type(chapter) is not dict:
        raise ValueError("invalid response format")
    chapter_id = _text(chapter.get("id"), 200)
    title = _text(chapter.get("title"), 1000)
    values = chapter.get("source_ids")
    if type(values) is not list or not 1 <= len(values) <= _SOURCE_LIMIT:
        raise ValueError("invalid response format")
    sources = list(dict.fromkeys(_text(value, 200) for value in values))
    return validate_response_format(_format(chapter_id, title, sources))


def validate_response_format(value):
    """Return a fresh canonical contract, rejecting arbitrary schema/options."""
    if value is None:
        return None
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")) > _FORMAT_LIMIT:
            raise ValueError
        if type(value) is not dict or set(value) != {"type", "json_schema"} or value["type"] != "json_schema":
            raise ValueError
        contract = value["json_schema"]
        if (type(contract) is not dict or set(contract) != {"name", "strict", "schema"}
                or contract["strict"] is not True):
            raise ValueError
        if contract["name"] in ("review_contract_v1", "guide_review_contract_v1"):
            expected = _review_format(contract["name"] == "guide_review_contract_v1")
            # JSON comparison also distinguishes bools from Python's equal 0/1.
            if (value != expected or json.dumps(value, sort_keys=True) != json.dumps(expected, sort_keys=True)):
                raise ValueError
            return expected
        if contract["name"] != _NAME:
            raise ValueError
        schema = contract["schema"]
        if (type(schema) is not dict or set(schema) != {"type", "properties", "required", "additionalProperties"}
                or schema["type"] != "object" or schema["additionalProperties"] is not False
                or type(schema["required"]) is not list or schema["required"] != list(_FIELDS)):
            raise ValueError
        props = schema["properties"]
        if type(props) is not dict or set(props) != set(_FIELDS):
            raise ValueError
        for name in ("chapter_id", "title"):
            prop = props[name]
            if type(prop) is not dict or set(prop) != {"type", "const"} or prop["type"] != "string":
                raise ValueError
        for name in ("paragraphs", "source_ids"):
            prop = props[name]
            if (type(prop) is not dict or set(prop) != {"type", "minItems", "items"}
                    or prop["type"] != "array" or type(prop["minItems"]) is not int or prop["minItems"] != 1):
                raise ValueError
        if props["paragraphs"]["items"] != {"type": "string"} or type(props["paragraphs"]["items"]) is not dict:
            raise ValueError
        items = props["source_ids"]["items"]
        if type(items) is not dict or set(items) != {"type", "enum"} or items["type"] != "string":
            raise ValueError
        return _format(_text(props["chapter_id"]["const"], 200),
                       _text(props["title"]["const"], 1000), _sources(items["enum"]))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ValueError("invalid response format") from None


def supports_chapter_response_format(provider, model):
    """Allow fixed contracts only on the exact verified provider/model pair."""
    def field(value, name):
        return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
    return (field(provider, "protocol") == "openai_chat"
            and field(provider, "base_url") == "https://dashscope.aliyuncs.com/compatible-mode/v1"
            and field(model, "model_name") == "qwen3.8-flash")


def generation_profile_metadata(profile):
    """Fixed metadata for hashing/checkpoints; never contains model prose."""
    if profile is None:
        return None
    if type(profile) is not str or profile != "bounded_chapter_v1":
        raise ValueError("invalid generation profile")
    return {"name": "bounded_chapter_v1", "enable_thinking": True,
            "thinking_budget": 512, "maximum_requested_tokens": 4096,
            "token_parameter": "max_completion_tokens", "token_safety_margin": 10,
            "maximum_timeout_seconds": 120}


def validate_generation_profile(profile, *, provider, model, response_format, messages=None,
                                purpose="business", stream=False, agent_tools=None,
                                tool_choice=None, requested=None):
    """Validate the single server-owned opt-in before reservation or I/O."""
    if profile is None:
        return None
    generation_profile_metadata(profile)
    def field(value, name):
        return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
    maximum = field(model, "max_output_tokens")
    timeout = field(model, "timeout_seconds")
    tokens = maximum if requested is None else requested
    if (not supports_chapter_response_format(provider, model)
            or validate_response_format(response_format) is None
            or response_format["json_schema"]["name"] != _NAME
            or purpose != "business" or stream is not False
            or agent_tools is not None or tool_choice is not None
            or type(maximum) is not int or type(tokens) is not int or not 522 < tokens <= maximum
            or type(timeout) not in (int, float) or not 1 <= timeout <= 120):
        raise ValueError("invalid generation profile")
    if messages is not None and (
            type(messages) is not list or not 1 <= len(messages) <= 32
            or any(type(message) is not dict or set(message) != {"role", "content"}
                   or message["role"] not in ("system", "user", "assistant")
                   or type(message["content"]) is not str or not message["content"].strip()
                   for message in messages)):
        raise ValueError("invalid generation profile")
    return profile


def validate_profile_usage(result, requested):
    """Bound numerical usage without retaining any reasoning content."""
    if type(requested) is not int or requested <= 522:
        raise ValueError("invalid profile usage")
    completion = result.get("completion_tokens")
    if completion is not None and (
            type(completion) is not int or not 0 <= completion <= min(requested, 4096)):
        raise ValueError("invalid profile usage")
    if "reasoning_tokens" in result:
        reasoning = result["reasoning_tokens"]
        if (type(reasoning) is not int or type(completion) is not int
                or not 0 <= reasoning <= completion):
            raise ValueError("invalid profile usage")
