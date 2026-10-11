import json
import copy
from types import SimpleNamespace
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from portal import model_gateway
from portal.model_messages import TEXT_REQUEST_LIMIT, validate_messages
from portal.model_response_format import (chapter_response_format, supports_chapter_response_format,
                                         validate_response_format, generation_profile_metadata,
                                         validate_generation_profile, validate_profile_usage)
from portal.models import AuditEvent, GatewayModel, ModelCallLog, ModelRoute, Module, Provider, Role

from .base import PortalTestCase


LOCAL_PROVIDER_URL = "http://127.0.0.1:19880/api/v1/openai/0123456789abcdef0123456789abcdef"


class ChapterResponseFormatTests(SimpleTestCase):
    def setUp(self):
        self.chapter = {"id": "approved-chapter", "title": "批准标题", "source_ids": ["source-1", "source-2"]}
        self.format = chapter_response_format(self.chapter)
        self.config = {
            "provider": {"protocol": "openai_chat", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                         "api_key_env": "PORTAL_MODEL_KEY_TEST"},
            "model": {"model_name": "qwen3.8-flash", "token_parameter": "max_tokens",
                      "max_output_tokens": 4096, "timeout_seconds": 120},
        }
        self.messages = [{"role": "user", "content": "synthetic chapter JSON"}]
        self.user = SimpleNamespace(grant_version=1)
        self.model = SimpleNamespace(provider=SimpleNamespace(updated_at=1), updated_at=1,
                                     supports_vision=False, public_id="model", pk=1)
        self.route = SimpleNamespace(updated_at=1, code="solution")

    def test_fixed_schema_is_detached_and_binds_approved_values(self):
        schema = self.format["json_schema"]["schema"]
        self.assertIs(self.format["json_schema"]["strict"], True)
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), {"chapter_id", "title", "paragraphs", "source_ids"})
        self.assertEqual(schema["properties"]["chapter_id"]["const"], self.chapter["id"])
        self.assertEqual(schema["properties"]["title"]["const"], self.chapter["title"])
        self.assertEqual(schema["properties"]["source_ids"]["items"]["enum"], self.chapter["source_ids"])
        self.assertEqual(schema["properties"]["source_ids"]["minItems"], 1)
        self.assertEqual(schema["properties"]["paragraphs"], {"type": "array", "minItems": 1, "items": {"type": "string"}})
        normalized = validate_response_format(self.format)
        normalized["json_schema"]["schema"]["properties"]["source_ids"]["items"]["enum"].append("new")
        self.assertEqual(self.chapter["source_ids"], ["source-1", "source-2"])
        self.assertEqual(self.format["json_schema"]["schema"]["properties"]["source_ids"]["items"]["enum"], ["source-1", "source-2"])
        self.assertIsNone(validate_response_format(None))

    def test_arbitrary_schema_options_and_unbounded_values_are_rejected(self):
        changes = [
            lambda x: x.update(type="json_object"),
            lambda x: x.update(extra="private-sentinel"),
            lambda x: x["json_schema"].update(strict=1),
            lambda x: x["json_schema"].update(name="arbitrary"),
            lambda x: x["json_schema"]["schema"].update(additionalProperties=0),
            lambda x: x["json_schema"]["schema"].update(required=[]),
            lambda x: x["json_schema"]["schema"].update(anyOf=[]),
            lambda x: x["json_schema"]["schema"]["properties"]["paragraphs"].update(minItems=True),
            lambda x: x["json_schema"]["schema"]["properties"]["paragraphs"]["items"].update(pattern=".*"),
            lambda x: x["json_schema"]["schema"]["properties"]["chapter_id"].update(const=True),
            lambda x: x["json_schema"]["schema"]["properties"]["title"].update(const="x" * 1001),
            lambda x: x["json_schema"]["schema"]["properties"]["source_ids"]["items"].update(enum=[]),
            lambda x: x["json_schema"]["schema"]["properties"]["source_ids"]["items"].update(enum=["s"] * 2),
            lambda x: x["json_schema"]["schema"]["properties"]["source_ids"]["items"].update(enum=[True]),
            lambda x: x["json_schema"]["schema"]["properties"]["source_ids"]["items"].update(enum=[str(i) for i in range(257)]),
            lambda x: x["json_schema"]["schema"]["properties"]["source_ids"]["items"].update(enum=[str(i) + "文" * 190 for i in range(100)]),
        ]
        for index, change in enumerate(changes):
            value = copy.deepcopy(self.format)
            change(value)
            with self.subTest(index=index), self.assertRaises(ValueError) as caught:
                validate_response_format(value)
            self.assertEqual(str(caught.exception), "invalid response format")
        for value in (False, [], "json_schema", {"id": "c", "title": "t", "source_ids": []},
                      {**self.chapter, "id": "x" * 201}, {**self.chapter, "source_ids": ["x" * 201]}):
            with self.subTest(chapter=value), self.assertRaises(ValueError):
                chapter_response_format(value)

    def test_support_is_exact_for_dicts_and_public_model_objects(self):
        self.assertTrue(supports_chapter_response_format(self.config["provider"], self.config["model"]))
        self.assertTrue(supports_chapter_response_format(SimpleNamespace(**self.config["provider"]),
                                                       SimpleNamespace(**self.config["model"])))
        for provider, model in (
                ({**self.config["provider"], "protocol": "other"}, self.config["model"]),
                ({**self.config["provider"], "base_url": self.config["provider"]["base_url"] + "/"}, self.config["model"]),
                (self.config["provider"], {**self.config["model"], "model_name": "qwen3.7-flash"})):
            self.assertFalse(supports_chapter_response_format(provider, model))

    def test_invalid_opt_in_precedes_reservation_and_outbound(self):
        for config, messages, purpose, value in (
                (self.config, self.messages, "business", {"type": "json_object"}),
                ({**self.config, "model": {**self.config["model"], "model_name": "unknown"}}, self.messages, "business", self.format),
                (self.config, [{"role": "user", "content": [{"type": "text", "text": "image path"}]}], "business", self.format),
                (self.config, self.messages, "test", self.format)):
            with patch.object(model_gateway, "_model_config", return_value=config), \
                    patch.object(model_gateway, "_reserve") as reserve, \
                    patch.object(model_gateway, "_request_gateway") as outbound:
                with self.assertRaises(model_gateway.GatewayError) as caught:
                    model_gateway._invoke(self.user, self.model, messages, purpose, self.route,
                                          response_format=value)
                self.assertEqual(caught.exception.code, "invalid_request")
                reserve.assert_not_called()
                outbound.assert_not_called()

    def test_generate_for_use_optional_argument_and_authorization_are_preserved(self):
        with patch.object(model_gateway, "_route_for", return_value=(self.user, self.route)) as route, \
                patch.object(model_gateway, "_select_route_model", return_value=(self.model, None, "version")) as select, \
                patch.object(model_gateway, "_invoke", return_value={}) as invoke:
            model_gateway.generate_for_use(self.user, "solution", self.messages)
            self.assertNotIn("response_format", invoke.call_args.kwargs)
            model_gateway.generate_for_use(self.user, "solution", self.messages, response_format=self.format)
            self.assertEqual(invoke.call_args.kwargs["response_format"], self.format)
            self.assertEqual(route.call_count, 2)
            self.assertEqual(select.call_count, 2)
        with patch.object(model_gateway, "_route_for", side_effect=model_gateway.GatewayError("forbidden")), \
                patch.object(model_gateway, "_invoke") as invoke:
            with self.assertRaises(model_gateway.GatewayError) as caught:
                model_gateway.generate_for_use(self.user, "solution", self.messages, response_format=self.format)
            self.assertEqual(caught.exception.code, "forbidden")
            invoke.assert_not_called()

    def test_opt_in_one_call_retains_refresh_audit_and_failures(self):
        reply = {"content": "synthetic", "prompt_tokens": 1, "completion_tokens": 2}
        for output_format, revoked in ((None, False), (self.format, False), (self.format, True)):
            record = MagicMock()
            fresh = SimpleNamespace(grant_version=2) if revoked else self.user
            with patch.object(model_gateway, "_model_config", return_value=self.config), \
                    patch.object(model_gateway, "_reserve", return_value=record) as reserve, \
                    patch.object(model_gateway, "_request_gateway", return_value=reply) as outbound, \
                    patch.object(model_gateway, "_fresh_user", return_value=fresh), \
                    patch.object(model_gateway, "_route_for", return_value=(self.user, self.route)), \
                    patch.object(model_gateway, "_select_route_model", return_value=(self.model, None, "version")), \
                    patch.object(model_gateway, "audit") as audit:
                if revoked:
                    with self.assertRaises(model_gateway.GatewayError) as caught:
                        model_gateway._invoke(self.user, self.model, self.messages, "business", self.route,
                                              "version", response_format=output_format)
                    self.assertEqual(caught.exception.code, "forbidden")
                else:
                    self.assertEqual(model_gateway._invoke(self.user, self.model, self.messages, "business", self.route,
                                                          "version", response_format=output_format), reply)
                reserve.assert_called_once()
                outbound.assert_called_once()
                record.save.assert_called_once()
                audit.assert_called_once()
                payload = outbound.call_args.args[0]
                if output_format is None:
                    self.assertEqual(payload, {**self.config, "messages": self.messages, "purpose": "business"})
                else:
                    self.assertEqual(payload["response_format"], self.format)

    def test_bounded_profile_metadata_is_fixed_and_detached(self):
        metadata = generation_profile_metadata("bounded_chapter_v1")
        self.assertEqual(metadata, {"name": "bounded_chapter_v1", "enable_thinking": True,
                                   "thinking_budget": 512, "maximum_requested_tokens": 4096,
                                   "token_parameter": "max_completion_tokens", "token_safety_margin": 10,
                                   "maximum_timeout_seconds": 120})
        metadata["thinking_budget"] = 999
        self.assertEqual(generation_profile_metadata("bounded_chapter_v1")["thinking_budget"], 512)
        self.assertIsNone(generation_profile_metadata(None))
        for value in (True, {}, "arbitrary-profile"):
            with self.assertRaises(ValueError):
                generation_profile_metadata(value)

    def test_bounded_profile_context_and_request_boundaries(self):
        options = {"provider": self.config["provider"], "model": self.config["model"],
                   "response_format": self.format, "messages": self.messages}
        self.assertEqual(validate_generation_profile("bounded_chapter_v1", **options), "bounded_chapter_v1")
        self.assertIsNone(validate_generation_profile(None, provider={}, model={}, response_format=None))
        for tokens in (523, 4096, 8192):
            changed = {**options, "model": {**self.config["model"], "max_output_tokens": tokens}}
            self.assertEqual(validate_generation_profile("bounded_chapter_v1", **changed), "bounded_chapter_v1")
        changes = [{"response_format": None}, {"response_format": {"type": "json_object"}},
                   {"purpose": "test"}, {"stream": True}, {"agent_tools": []}, {"tool_choice": "none"},
                   {"messages": [{"role": "user", "content": []}]},
                   {"model": {**self.config["model"], "timeout_seconds": 121}},
                   {"model": {**self.config["model"], "timeout_seconds": True}},
                   {"provider": {**self.config["provider"], "base_url": "https://unknown.example/v1"}}]
        changes += [{"requested": x} for x in (0, 522, True, 523.0, 4097)]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_generation_profile("bounded_chapter_v1", **{**options, **change})
        self.assertIsNone(validate_profile_usage({"completion_tokens": 4096, "reasoning_tokens": 4096}, 4096))
        for usage in ({"completion_tokens": 4097}, {"completion_tokens": True},
                      {"completion_tokens": 1, "reasoning_tokens": 2},
                      {"completion_tokens": None, "reasoning_tokens": 0},
                      {"completion_tokens": 1, "reasoning_tokens": False}):
            with self.assertRaises(ValueError):
                validate_profile_usage(usage, 4096)

    def test_profile_invalid_context_precedes_reservation(self):
        for config, profile, output_format in (
                (self.config, "unknown", self.format), (self.config, "bounded_chapter_v1", None),
                ({**self.config, "model": {**self.config["model"], "timeout_seconds": 121}}, "bounded_chapter_v1", self.format),
                ({**self.config, "model": {**self.config["model"], "max_output_tokens": 522}}, "bounded_chapter_v1", self.format)):
            with patch.object(model_gateway, "_model_config", return_value=config), \
                    patch.object(model_gateway, "_reserve") as reserve, \
                    patch.object(model_gateway, "_request_gateway") as outbound:
                with self.assertRaises(model_gateway.GatewayError) as caught:
                    model_gateway._invoke(self.user, self.model, self.messages, "business", self.route,
                                          response_format=output_format, generation_profile=profile)
                self.assertEqual(caught.exception.code, "invalid_request")
                reserve.assert_not_called()
                outbound.assert_not_called()

    def test_profile_generation_one_call_and_authorization_refresh(self):
        reply = {"content": "synthetic", "prompt_tokens": 1, "completion_tokens": 1000, "reasoning_tokens": 512}
        for revoked in (False, True):
            record = MagicMock()
            fresh = SimpleNamespace(grant_version=2) if revoked else self.user
            with patch.object(model_gateway, "_model_config", return_value=self.config), \
                    patch.object(model_gateway, "_reserve", return_value=record) as reserve, \
                    patch.object(model_gateway, "_request_gateway", return_value=reply) as outbound, \
                    patch.object(model_gateway, "_fresh_user", return_value=fresh), \
                    patch.object(model_gateway, "_route_for", return_value=(self.user, self.route)), \
                    patch.object(model_gateway, "_select_route_model", return_value=(self.model, None, "version")), \
                    patch.object(model_gateway, "audit") as audit:
                if revoked:
                    with self.assertRaises(model_gateway.GatewayError) as caught:
                        model_gateway.generate_for_use(self.user, "solution", self.messages,
                                                       response_format=self.format, generation_profile="bounded_chapter_v1")
                    self.assertEqual(caught.exception.code, "forbidden")
                else:
                    result = model_gateway.generate_for_use(self.user, "solution", self.messages,
                                                            response_format=self.format, generation_profile="bounded_chapter_v1")
                    self.assertEqual(result["reasoning_tokens"], 512)
                reserve.assert_called_once()
                outbound.assert_called_once()
                self.assertEqual(outbound.call_args.args[0]["generation_profile"], "bounded_chapter_v1")
                audit.assert_called_once()
                record.save.assert_called_once()

    def test_profile_optional_usage_response_contract_and_budget(self):
        reply = {"content": "synthetic", "duration_ms": 1, "prompt_tokens": 2, "completion_tokens": 4096}
        payload = {**self.config, "messages": self.messages, "purpose": "business"}
        cases = [(None, reply, True), (None, {**reply, "reasoning_tokens": 0}, False),
                 ("bounded_chapter_v1", reply, True),
                 ("bounded_chapter_v1", {**reply, "reasoning_tokens": 0}, True),
                 ("bounded_chapter_v1", {**reply, "reasoning_tokens": 4096}, True),
                 ("bounded_chapter_v1", {**reply, "reasoning_tokens": 4097}, False),
                 ("bounded_chapter_v1", {**reply, "reasoning_tokens": True}, False),
                 ("bounded_chapter_v1", {**reply, "completion_tokens": 4097}, False),
                 ("bounded_chapter_v1", {**reply, "reasoning_content": "private-sentinel"}, False)]
        for profile, value, valid in cases:
            body = json.dumps(value).encode()
            response = MagicMock()
            response.__enter__.return_value.read.return_value = body
            request_payload = {**payload, **({"generation_profile": profile} if profile else {})}
            with patch.object(model_gateway, "_gateway_request", return_value=(MagicMock(), 5)), \
                    patch.object(model_gateway, "build_opener") as opener:
                opener.return_value.open.return_value = response
                if valid:
                    self.assertEqual(model_gateway._request_gateway(request_payload), value)
                else:
                    with self.assertRaises(model_gateway.GatewayError) as caught:
                        model_gateway._request_gateway(request_payload)
                    self.assertEqual(caught.exception.code, "invalid_response")

    def test_explicit_none_profile_does_not_add_invoke_kwargs(self):
        with patch.object(model_gateway, "_route_for", return_value=(self.user, self.route)), \
                patch.object(model_gateway, "_select_route_model", return_value=(self.model, None, "version")), \
                patch.object(model_gateway, "_invoke", return_value={}) as invoke:
            model_gateway.generate_for_use(self.user, "solution", self.messages, generation_profile=None)
            self.assertEqual(invoke.call_args.kwargs, {"selection_pinned": False})


class MessageSizeTests(SimpleTestCase):
    def test_full_document_text_is_preserved(self):
        messages = [{"role": "user", "content": "完整设备清册与技术论证。" * 16000}]
        self.assertIs(model_gateway._messages(messages), messages)
        self.assertEqual(validate_messages(messages), 0)

    def test_long_vision_text_block_is_preserved(self):
        messages = [{"role": "user", "content": [{"type": "text", "text": "完整项目背景" * 16000}]}]
        self.assertIs(model_gateway._messages(messages, supports_vision=True), messages)
        self.assertEqual(validate_messages(messages, vision=True), 0)

    def test_text_resource_limit_counts_utf8_bytes(self):
        messages = [{"role": "user", "content": "设备" * (TEXT_REQUEST_LIMIT // 6)}]
        self.assertLess(len(messages[0]["content"]), TEXT_REQUEST_LIMIT)
        with self.assertRaises(model_gateway.GatewayError) as caught:
            model_gateway._messages(messages)
        self.assertEqual(caught.exception.code, "request_too_large")
        with self.assertRaises(ValueError):
            validate_messages(messages)

    def test_empty_and_nontext_messages_remain_invalid(self):
        for content in ("", None, 12, {"text": "not a string"}):
            with self.subTest(content=content):
                with self.assertRaises(model_gateway.GatewayError):
                    model_gateway._messages([{"role": "user", "content": content}])
                with self.assertRaises(ValueError):
                    validate_messages([{"role": "user", "content": content}])


class ProviderUrlValidationTests(SimpleTestCase):
    @override_settings(MODEL_GATEWAY_URL="http://127.0.0.1:18410", MODEL_GATEWAY_TOKEN="x" * 48,
        MODEL_GATEWAY_ALLOWED_URLS=("http://127.0.0.1:18410",))
    def test_long_document_requests_keep_gateway_response_margin(self):
        for seconds, expected in ((20, 25), (60, 65), (300, 330), (600, 630)):
            with self.subTest(seconds=seconds):
                _, timeout = model_gateway._gateway_request({
                    "model": {"timeout_seconds": seconds},
                    "messages": [{"role": "user", "content": "test"}],
                })
                self.assertEqual(timeout, expected)

    @override_settings(MODEL_GATEWAY_URL="http://127.0.0.1:18410", MODEL_GATEWAY_TOKEN="x" * 48)
    @patch("portal.model_gateway.build_opener")
    def test_malformed_upstream_error_codes_are_sanitized_for_both_transports(self, opener):
        payload = {"model": {"timeout_seconds": 2}, "messages": [{"role": "user", "content": "test"}]}
        for code in ([], {}, None, 123, "unknown-private-error"):
            for streaming in (False, True):
                with self.subTest(code=code, streaming=streaming):
                    body = BytesIO(json.dumps({"code": code, "detail": "private upstream data"}).encode())
                    opener.return_value.open.side_effect = HTTPError("http://127.0.0.1:18410", 502, "error", {}, body)
                    with self.assertRaises(model_gateway.GatewayError) as caught:
                        if streaming:
                            list(model_gateway._request_gateway_stream(payload))
                        else:
                            model_gateway._request_gateway(payload)
                    self.assertEqual(caught.exception.code, "upstream_error")
                    self.assertEqual(caught.exception.status, 502)
                    self.assertNotIn("private", str(caught.exception))
                    self.assertTrue(body.closed)

    @override_settings(DEBUG=True, MODEL_PROVIDER_LOCAL_HTTP=True)
    def test_exact_local_provider_url_allowed_for_opted_in_development(self):
        model_gateway.validate_provider_url(LOCAL_PROVIDER_URL)

    @override_settings(DEBUG=False, MODEL_PROVIDER_LOCAL_HTTP=True)
    def test_local_provider_url_rejected_in_production(self):
        with self.assertRaises(ValidationError):
            model_gateway.validate_provider_url(LOCAL_PROVIDER_URL)

    @override_settings(DEBUG=True, MODEL_PROVIDER_LOCAL_HTTP=False)
    def test_local_provider_url_rejected_without_opt_in(self):
        with self.assertRaises(ValidationError):
            model_gateway.validate_provider_url(LOCAL_PROVIDER_URL)

    @override_settings(DEBUG=True, MODEL_PROVIDER_LOCAL_HTTP=True)
    def test_local_provider_url_rejects_nonloopback_credentials_queries_and_fragments(self):
        identifier = "0123456789abcdef0123456789abcdef"
        for invalid in (
            f"http://localhost:19880/api/v1/openai/{identifier}",
            f"http://192.168.1.10:19880/api/v1/openai/{identifier}",
            f"http://user@127.0.0.1:19880/api/v1/openai/{identifier}",
            f"{LOCAL_PROVIDER_URL}?model=test",
            f"{LOCAL_PROVIDER_URL}#fragment",
            f"http://127.0.0.1:19880/api/v1/openai/{identifier.upper()}",
            f"{LOCAL_PROVIDER_URL}/",
        ):
            with self.subTest(url=invalid), self.assertRaises(ValidationError):
                model_gateway.validate_provider_url(invalid)


class ModelGatewayTests(PortalTestCase):
    def setUp(self):
        self.user = self.create_user("model-product", "product")
        self.admin = self.create_admin("model-admin")
        self.provider = Provider.objects.create(code="test", name="隔离服务", protocol="openai_chat",
                                                base_url="https://provider.example/v1", api_key_env="PORTAL_MODEL_KEY_TEST", enabled=True)
        self.model = GatewayModel.objects.create(name="隔离模型", provider=self.provider, model_name="test-model", enabled=True)
        self.route = ModelRoute.objects.create(code="solution", name="方案编写", module=Module.objects.get(code="product"), model=self.model, enabled=True)
        self.messages = [{"role": "user", "content": "synthetic-private-input"}]
        self.reply = {"content": "synthetic-private-result", "duration_ms": 1, "prompt_tokens": 3, "completion_tokens": 4}

    @patch('portal.model_gateway._request_gateway')
    def test_images_require_declared_model_capability(self, request):
        import base64
        url = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nimage').decode()
        messages = [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': url}}]}]
        self.assert_error('unsupported_capability', model_gateway.generate_for_use, self.user, 'solution', messages)
        request.assert_not_called()
        self.model.supports_vision = True
        self.model.save()
        request.return_value = self.reply
        result = model_gateway.generate_for_use(self.user, 'solution', messages)
        self.assertEqual(result['content'], self.reply['content'])
        self.assertEqual(request.call_args.args[0]['messages'], messages)

    def assert_error(self, code, function, *args):
        with self.assertRaises(model_gateway.GatewayError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    @patch("portal.model_gateway._request_gateway")
    def test_admin_has_no_implicit_business_access(self, request):
        self.assert_error("forbidden", model_gateway.generate_for_use, self.admin, "solution", self.messages)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_unmapped_use_and_revoked_role_fail_before_outbound(self, request):
        self.assert_error("forbidden", model_gateway.generate_for_use, self.user, "missing", self.messages)
        self.user.roles.clear()
        self.assert_error("forbidden", model_gateway.generate_for_use, self.user, "solution", self.messages)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_disabled_user_module_route_model_provider(self, request):
        for target in (self.user, self.route.module, self.route, self.model, self.provider):
            field = "is_active" if target is self.user else "enabled"
            setattr(target, field, False)
            target.save()
            expected = "forbidden" if target in (self.user, self.route.module) else "disabled"
            self.assert_error(expected, model_gateway.generate_for_use, self.user, "solution", self.messages)
            setattr(target, field, True)
            target.save()
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_success_logs_metadata_not_prompts_responses_or_key(self, request):
        request.return_value = self.reply
        result = model_gateway.generate_for_use(self.user, "solution", self.messages)
        self.assertEqual(result["content"], self.reply["content"])
        record = ModelCallLog.objects.get()
        self.assertEqual(record.status, "success")
        self.assertEqual(record.prompt_tokens, 3)
        logs = json.dumps(list(ModelCallLog.objects.values()) + list(AuditEvent.objects.values()), default=str)
        self.assertNotIn("synthetic-private-input", logs)
        self.assertNotIn("synthetic-private-result", logs)
        self.assertNotIn("PORTAL_MODEL_KEY_TEST", logs)

    @patch("portal.model_gateway._request_gateway")
    def test_route_switch_preserves_business_call(self, request):
        request.return_value = self.reply
        model_gateway.generate_for_use(self.user, "solution", self.messages)
        second = Provider.objects.create(code="second", name="第二服务", protocol="openai_chat",
                                         base_url="https://second.example/v1", api_key_env="PORTAL_MODEL_KEY_SECOND", enabled=True)
        model = GatewayModel.objects.create(name="第二模型", provider=second, model_name="second-model", enabled=True)
        self.route.model = model
        self.route.save()
        model_gateway.generate_for_use(self.user, "solution", self.messages)
        payload = request.call_args.args[0]
        self.assertEqual(payload["model"]["model_name"], "second-model")
        self.assertEqual(payload["provider"]["base_url"], "https://second.example/v1")
        self.assertEqual(payload["messages"], self.messages)

    @patch("portal.model_gateway._request_gateway")
    def test_revocation_in_flight_discards_output(self, request):
        def revoke(payload):
            self.user.roles.clear()
            return self.reply
        request.side_effect = revoke
        self.assert_error("forbidden", model_gateway.generate_for_use, self.user, "solution", self.messages)
        self.assertEqual(ModelCallLog.objects.get().status, "forbidden")

    @patch("portal.model_gateway._request_gateway")
    def test_config_change_in_flight_discards_output(self, request):
        def change(payload):
            self.model.model_name = "new-model"
            self.model.save()
            return self.reply
        request.side_effect = change
        self.assert_error("disabled", model_gateway.generate_for_use, self.user, "solution", self.messages)

    @patch("portal.model_gateway._request_gateway")
    def test_revocation_then_restore_still_discards_inflight_output(self, request):
        def revoke_restore(payload):
            self.user.roles.clear()
            self.user.roles.add(Role.objects.get(code="product"))
            return self.reply
        request.side_effect = revoke_restore
        self.assert_error("forbidden", model_gateway.generate_for_use, self.user, "solution", self.messages)

    @patch("portal.model_gateway._request_gateway")
    def test_configuration_change_then_restore_still_discards_output(self, request):
        def change_restore(payload):
            self.model.model_name = "temporary-model"
            self.model.save()
            self.model.model_name = "test-model"
            self.model.save()
            return self.reply
        request.side_effect = change_restore
        self.assert_error("disabled", model_gateway.generate_for_use, self.user, "solution", self.messages)

    @override_settings(MODEL_GATEWAY_URL="https://unapproved-gateway.example", MODEL_GATEWAY_TOKEN="x" * 48)
    @patch("portal.model_gateway.build_opener")
    def test_service_token_never_sent_to_unapproved_gateway(self, opener):
        self.assert_error("unconfigured", model_gateway._request_gateway, {})
        opener.assert_not_called()

    def test_admin_model_choices_are_readable_and_audit_repr_stays_minimal(self):
        from django.test import RequestFactory
        from portal.admin import site

        request = RequestFactory().get("/admin/")
        request.user = self.admin
        field = site._registry[GatewayModel].formfield_for_foreignkey(GatewayModel._meta.get_field("provider"), request)
        self.assertIn("隔离服务", field.label_from_instance(self.provider))
        field = site._registry[ModelRoute].formfield_for_foreignkey(ModelRoute._meta.get_field("model"), request)
        self.assertIn("隔离模型", field.label_from_instance(self.model))
        self.assertNotIn("隔离服务", str(self.provider))
        record = ModelCallLog(status="target_not_allowed")
        self.assertEqual(site._registry[ModelCallLog].status_label(record), "模型服务地址未获允许。")

    @patch("portal.model_gateway._request_gateway")
    def test_admin_probe_is_fixed_and_rate_limited(self, request):
        request.return_value = {**self.reply, "content": None}
        model_gateway.test_connection(self.admin, self.model.pk)
        self.assertEqual(request.call_args.args[0]["messages"], [{"role": "user", "content": "Reply with OK."}])
        self.assertEqual(request.call_args.args[0]["purpose"], "test")
        self.assert_error("rate_limited", model_gateway.test_connection, self.admin, self.model.pk)
        self.assertEqual(request.call_count, 1)

    @patch("portal.model_gateway._request_gateway")
    def test_ordinary_user_cannot_probe(self, request):
        self.assert_error("forbidden", model_gateway.test_connection, self.user, self.model.pk)
        request.assert_not_called()

    @patch("portal.model_gateway._request_gateway")
    def test_unexpected_exception_is_redacted_and_logged(self, request):
        request.side_effect = RuntimeError("must-not-echo-secret")
        self.assert_error("internal_error", model_gateway.generate_for_use, self.user, "solution", self.messages)
        self.assertEqual(ModelCallLog.objects.get().status, "internal_error")

    @patch("portal.model_gateway._request_gateway")
    def test_model_capability_and_request_shape_checked(self, request):
        self.model.supports_text = False
        self.model.save()
        self.assert_error("unsupported_capability", model_gateway.generate_for_use, self.user, "solution", self.messages)
        self.model.supports_text = True
        self.model.save()
        for invalid in ([], [{"role": "tool", "content": "text"}], [{"role": "user", "content": "text", "base_url": "https://evil.example"}]):
            self.assert_error("invalid_request", model_gateway.generate_for_use, self.user, "solution", invalid)
        request.assert_not_called()

    @override_settings(MODEL_GATEWAY_URL="http://169.254.169.254", MODEL_GATEWAY_TOKEN="x" * 48)
    @patch("portal.model_gateway.build_opener")
    def test_internal_http_only_loopback(self, opener):
        self.assert_error("unconfigured", model_gateway._request_gateway, {})
        opener.assert_not_called()

    def knowledge_route(self):
        self.route.code = "product_knowledge"
        self.route.save()

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_success_logs_metadata_and_rechecks(self, request):
        self.knowledge_route()
        def source(payload):
            yield {"delta": "private-model-output"}
            yield {"done": True, "prompt_tokens": 3, "completion_tokens": 4}
        request.side_effect = source
        self.assertEqual(list(model_gateway.stream_for_use(self.user, self.route.code, self.messages)),
                         [{"delta": "private-model-output"},
                          {"done": True, "prompt_tokens": 3, "completion_tokens": 4}])
        self.assertEqual(ModelCallLog.objects.get().status, "success")
        self.assertEqual(ModelCallLog.objects.get().prompt_tokens, 3)
        self.assertNotIn("private-model-output", json.dumps(list(ModelCallLog.objects.values()), default=str))
        self.assertEqual(request.call_args.args[0]["purpose"], "business")

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_revoked_before_done_is_not_success(self, request):
        self.knowledge_route()
        def revoke(payload):
            yield {"delta": "partial"}
            self.user.roles.clear()
            yield {"done": True, "prompt_tokens": 1, "completion_tokens": 1}
        request.side_effect = revoke
        stream = model_gateway.stream_for_use(self.user, self.route.code, self.messages)
        self.assertEqual(next(stream), {"delta": "partial"})
        self.assert_error("forbidden", list, stream)
        self.assertEqual(ModelCallLog.objects.get().status, "forbidden")

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_config_change_before_done_is_rejected(self, request):
        self.knowledge_route()
        def change(payload):
            yield {"delta": "partial"}
            self.model.model_name = "changed-model"
            self.model.save()
            yield {"done": True, "prompt_tokens": 1, "completion_tokens": 1}
        request.side_effect = change
        self.assert_error("disabled", list, model_gateway.stream_for_use(self.user, self.route.code, self.messages))
        self.assertEqual(ModelCallLog.objects.get().status, "disabled")

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_is_only_for_knowledge_route(self, request):
        self.assert_error("forbidden", list, model_gateway.stream_for_use(self.user, "solution", self.messages))
        request.assert_not_called()
        self.assertFalse(ModelCallLog.objects.exists())

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_cancel_closes_source_and_audits(self, request):
        self.knowledge_route()
        def source(payload):
            try:
                yield {"delta": "partial"}
                yield {"done": True, "prompt_tokens": 1, "completion_tokens": 1}
            finally:
                source.closed = True
        source.closed = False
        request.side_effect = source
        stream = model_gateway.stream_for_use(self.user, self.route.code, self.messages)
        next(stream)
        stream.close()
        self.assertTrue(source.closed)
        self.assertEqual(ModelCallLog.objects.get().status, "cancelled")
        self.assertEqual(AuditEvent.objects.filter(action="model_call").count(), 1)

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway._request_gateway_stream")
    def test_stream_failure_and_truncation_logged(self, request):
        self.knowledge_route()
        def partial(payload):
            yield {"delta": "fragment"}
        request.side_effect = partial
        self.assert_error("invalid_response", list, model_gateway.stream_for_use(self.user, self.route.code, self.messages))
        self.assertEqual(ModelCallLog.objects.latest("pk").status, "invalid_response")
        def failure(payload):
            yield {"delta": "fragment"}
            raise model_gateway.GatewayError("output_truncated")
        request.side_effect = failure
        self.assert_error("output_truncated", list, model_gateway.stream_for_use(self.user, self.route.code, self.messages))

    @override_settings(MODEL_GATEWAY_URL="http://127.0.0.1:18410", MODEL_GATEWAY_TOKEN="x" * 48)
    @patch("portal.model_gateway.build_opener")
    def test_stream_wire_success_invalid_incomplete_oversized_and_error(self, opener):
        payload = {"model": {"timeout_seconds": 2}, "messages": self.messages}
        class LineOnlyResponse(BytesIO):
            def read(self, size=-1):
                raise AssertionError("streaming must not wait for a fixed-size read")
        def send(body, content_type="text/event-stream"):
            response = LineOnlyResponse(body)
            response.headers = {"Content-Type": content_type}
            opener.return_value.open.return_value = response
            return response
        done = b'data: {"done":true,"prompt_tokens":1,"completion_tokens":2}\n\n'
        response = send(b'data: {"delta":"ok"}\r\n\r\n' + done)
        self.assertEqual(list(model_gateway._request_gateway_stream(payload)),
                         [{"delta": "ok"}, {"done": True, "prompt_tokens": 1, "completion_tokens": 2}])
        self.assertTrue(response.closed)
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:18410/v1/generate-stream")
        self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 7)
        for body, code in ((b'data: {"delta":"partial"}\n\n', "invalid_response"),
                           (b'data: {"delta":"broken"}', "invalid_response"),
                           (b'data: {"delta":"' + b'x' * 1048576 + b'"}\n\n', "response_too_large"),
                           (b'data: {"error":{"code":"rate_limited","detail":"secret"}}\n\n', "rate_limited")):
            with self.subTest(code=code, body=body[:30]):
                response = send(body)
                self.assert_error(code, list, model_gateway._request_gateway_stream(payload))
                self.assertTrue(response.closed)

    @override_settings(PRODUCT_KNOWLEDGE_MODEL_ROUTE="product_knowledge")
    @patch("portal.model_gateway.build_opener")
    def test_stream_rejects_disallowed_internal_url(self, opener):
        self.knowledge_route()
        with override_settings(MODEL_GATEWAY_URL="http://169.254.169.254", MODEL_GATEWAY_TOKEN="x" * 48):
            self.assert_error("unconfigured", list, model_gateway.stream_for_use(self.user, self.route.code, self.messages))
        opener.assert_not_called()
        self.assertEqual(ModelCallLog.objects.get().status, "unconfigured")
