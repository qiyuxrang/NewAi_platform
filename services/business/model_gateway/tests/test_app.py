import copy
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.portal.model_messages import TEXT_REQUEST_LIMIT
from backend.portal.model_response_format import chapter_response_format, review_response_format
from model_gateway.app import app, slots
from model_gateway.errors import GatewayError


class GatewayAppTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"MODEL_GATEWAY_SERVICE_TOKEN": "isolated-test-token-" * 4})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + os.environ["MODEL_GATEWAY_SERVICE_TOKEN"]}
        self.payload = {"provider": {"protocol": "openai_chat", "base_url": "https://provider.example/v1", "api_key_env": "PORTAL_MODEL_KEY_TEST"},
                        "model": {"model_name": "test-model", "timeout_seconds": 10, "max_output_tokens": 512, "token_parameter": "max_tokens"},
                        "messages": [{"role": "user", "content": "synthetic-private-input"}], "purpose": "business"}

    def post(self, payload=None):
        return self.client.post("/v1/generate", json=self.payload if payload is None else payload, headers=self.headers)

    def chapter_payload(self):
        payload = copy.deepcopy(self.payload)
        payload["provider"]["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        payload["model"].update(model_name="qwen3.8-flash", max_output_tokens=4096, timeout_seconds=120)
        payload["response_format"] = chapter_response_format({"id": "c", "title": "approved", "source_ids": ["s"]})
        return payload

    @patch("model_gateway.app.chat_completion", return_value={"content": '{"passed":true,"issues":[]}',
                                                             "prompt_tokens": 1, "completion_tokens": 2})
    def test_review_contract_forwarded_and_existing_context_gates_hold(self, call):
        payload = self.chapter_payload()
        basic = {"passed": "boolean", "issues": ["string"]}
        guide = {**basic, "guide_checks": [{
            "id": "exact-guide-requirement-id", "status": "covered/partial/not_seen/not_applicable/pending",
            "evidence": [{"chapter_id": "saved-chapter-id", "quote": "exact-sent-body-quote"}], "reason": "string"}]}
        for specification in (basic, guide):
            payload["response_format"] = review_response_format(specification)
            self.assertEqual(self.post(payload).status_code, 200)
            call.assert_called_once()
            self.assertEqual(call.call_args.kwargs["response_format"], payload["response_format"])
            call.reset_mock()
        for change in (
                lambda p: p["provider"].update(base_url="https://other.example/v1"),
                lambda p: p["model"].update(model_name="unknown"),
                lambda p: p.update(purpose="test"),
                lambda p: p.update(generation_profile="bounded_chapter_v1"),
                lambda p: p["response_format"]["json_schema"]["schema"]["properties"]["passed"].update(type="string"),
                lambda p: p["response_format"]["json_schema"]["schema"].update(additionalProperties=0)):
            invalid = copy.deepcopy(payload)
            change(invalid)
            self.assertEqual(self.post(invalid).status_code, 422)
        for endpoint, status in (("/v1/generate-vision", 422), ("/v1/generate-stream", 400),
                                 ("/v1/generate-agent", 422)):
            self.assertEqual(self.client.post(endpoint, json=payload, headers=self.headers).status_code, status)
        call.assert_not_called()

    @patch("model_gateway.app.chat_completion")
    def test_upstream_diagnostic_crosses_gateway_http_boundary(self, call):
        call.side_effect = GatewayError("upstream_invalid_request", "模型服务拒绝调用参数。", status=400,
                                        diagnostic={"upstream_status": 400, "upstream_code": "InvalidParameter"})
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["diagnostic"],
                         {"upstream_status": 400, "upstream_code": "InvalidParameter"})
        self.assertNotIn("synthetic-private-input", response.text)
        call.assert_called_once()

    @patch("model_gateway.app.chat_completion", return_value={"content": "synthetic", "prompt_tokens": 1,
                                                             "completion_tokens": 1000, "reasoning_tokens": 512})
    def test_bounded_profile_dto_forwarded_once_with_safe_optional_usage(self, call):
        payload = {**self.chapter_payload(), "generation_profile": "bounded_chapter_v1"}
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reasoning_tokens"], 512)
        self.assertNotIn("reasoning_content", response.json())
        call.assert_called_once()
        self.assertEqual(call.call_args.kwargs["generation_profile"], "bounded_chapter_v1")
        call.return_value = {"content": "synthetic", "prompt_tokens": 1, "completion_tokens": 2}
        self.assertNotIn("reasoning_tokens", self.post(payload).json())
        self.assertEqual(set(self.post().json()), {"content", "duration_ms", "prompt_tokens", "completion_tokens"})
        self.assertNotIn("generation_profile", call.call_args.kwargs)
        self.assertEqual(set(self.post({**self.payload, "generation_profile": None}).json()),
                         {"content", "duration_ms", "prompt_tokens", "completion_tokens"})
        self.assertNotIn("generation_profile", call.call_args.kwargs)

    @patch("model_gateway.app.chat_completion")
    @patch("model_gateway.app.stream_completion")
    def test_bounded_profile_rejects_invalid_contexts_before_transport(self, stream, call):
        changes = [lambda p: p.update(generation_profile="unknown"),
                   lambda p: p.update(generation_profile=True),
                   lambda p: p.update(response_format=None),
                   lambda p: p.update(purpose="test"),
                   lambda p: p["provider"].update(base_url="https://unknown.example/v1"),
                   lambda p: p["model"].update(model_name="qwen3.7-flash"),
                   lambda p: p["model"].update(max_output_tokens=522),
                   lambda p: p["model"].update(timeout_seconds=121),
                   lambda p: p.update(thinking_budget=512), lambda p: p.update(reasoning_effort="low")]
        for index, change in enumerate(changes):
            payload = {**self.chapter_payload(), "generation_profile": "bounded_chapter_v1"}
            change(payload)
            with self.subTest(index=index):
                response = self.post(payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "invalid_request")
        for endpoint, status in (("/v1/generate-vision", 422), ("/v1/generate-stream", 400),
                                 ("/v1/generate-agent", 422)):
            response = self.client.post(endpoint, json={**self.chapter_payload(), "generation_profile": "bounded_chapter_v1"}, headers=self.headers)
            self.assertEqual(response.status_code, status)
        call.assert_not_called()
        stream.assert_not_called()

    @patch("model_gateway.app.chat_completion")
    def test_bounded_profile_rejects_bad_numeric_usage_without_retry(self, call):
        payload = {**self.chapter_payload(), "generation_profile": "bounded_chapter_v1"}
        for usage, valid in (({"completion_tokens": 0, "reasoning_tokens": 0}, True),
                             ({"completion_tokens": 4096, "reasoning_tokens": 4096}, True),
                             ({"completion_tokens": 4097}, False),
                             ({"completion_tokens": True}, False),
                             ({"completion_tokens": 100, "reasoning_tokens": 101}, False),
                             ({"completion_tokens": 100, "reasoning_tokens": -1}, False),
                             ({"completion_tokens": 100, "reasoning_tokens": True}, False)):
            call.reset_mock()
            call.return_value = {"content": "synthetic", "prompt_tokens": 1, **usage}
            response = self.post(payload)
            self.assertEqual(response.status_code, 200 if valid else 502)
            if not valid:
                self.assertEqual(response.json()["code"], "invalid_response")
            call.assert_called_once()

    @patch("model_gateway.app.chat_completion", side_effect=GatewayError("output_truncated", "模型输出被截断。"))
    def test_bounded_profile_transport_failure_has_no_fallback(self, call):
        response = self.post({**self.chapter_payload(), "generation_profile": "bounded_chapter_v1"})
        self.assertEqual(response.json()["code"], "output_truncated")
        call.assert_called_once()

    @patch("model_gateway.app.chat_completion", return_value={"content": "synthetic", "prompt_tokens": 1, "completion_tokens": 2})
    def test_chapter_response_format_forwarded_once_and_default_not_forwarded(self, call):
        payload = self.chapter_payload()
        self.assertEqual(self.post(payload).status_code, 200)
        call.assert_called_once()
        self.assertEqual(call.call_args.kwargs["response_format"], payload["response_format"])
        self.assertEqual(call.call_args.args[1]["max_output_tokens"], 4096)
        self.assertEqual(call.call_args.args[1]["timeout_seconds"], 120)
        call.reset_mock()
        self.assertEqual(self.post().status_code, 200)
        self.assertNotIn("response_format", call.call_args.kwargs)
        self.assertEqual(self.post({**self.payload, "response_format": None}).status_code, 200)
        self.assertNotIn("response_format", call.call_args.kwargs)

    @patch("model_gateway.app.chat_completion")
    def test_chapter_format_invalid_contract_and_unknown_combinations_fail_before_outbound(self, call):
        changes = [lambda p: p.update(response_format={"type": "json_object"}),
                   lambda p: p["response_format"]["json_schema"].update(strict=True, unknown="private-sentinel"),
                   lambda p: p["model"].update(model_name="unknown"),
                   lambda p: p["provider"].update(base_url="https://other.example/v1"),
                   lambda p: p.update(purpose="test"),
                   lambda p: p.update(tools=[]), lambda p: p.update(stream=True)]
        for index, change in enumerate(changes):
            payload = self.chapter_payload()
            change(payload)
            with self.subTest(index=index):
                response = self.post(payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "invalid_request")
                self.assertNotIn("private-sentinel", response.text)
        call.assert_not_called()

    @patch("model_gateway.app.stream_completion")
    @patch("model_gateway.app.chat_completion")
    def test_chapter_mode_vision_stream_agent_rejected_without_transport(self, call, stream):
        for endpoint, status in (("/v1/generate-vision", 422), ("/v1/generate-stream", 400),
                                 ("/v1/generate-agent", 422)):
            response = self.client.post(endpoint, json=self.chapter_payload(), headers=self.headers)
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["code"], "invalid_request")
        call.assert_not_called()
        stream.assert_not_called()

    @patch("model_gateway.app.chat_completion", side_effect=GatewayError("output_truncated", "模型输出被截断。"))
    def test_chapter_format_transport_error_has_no_fallback(self, call):
        response = self.post(self.chapter_payload())
        self.assertEqual(response.json()["code"], "output_truncated")
        call.assert_called_once()

    @patch("model_gateway.app.list_models", return_value=["qwen-plus", "qwen-flash"])
    def test_catalog_requires_service_token_and_provider_only(self, listing):
        body = {"provider": self.payload["provider"]}
        self.assertEqual(self.client.post("/v1/models", json=body).status_code, 401)
        self.assertEqual(self.client.post("/v1/models", json={**body, "key": "private"}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/v1/models", json=body, headers=self.headers).json(),
                         {"models": ["qwen-plus", "qwen-flash"]})
        listing.assert_called_once_with(body["provider"])

    @patch("model_gateway.app.chat_completion")
    def test_authentication_precedes_payload_and_outbound(self, call):
        for headers in ({}, {"Authorization": "Bearer invalid"}):
            response = self.client.post("/v1/generate", content="invalid-secret-payload", headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("invalid-secret", response.text)
        call.assert_not_called()

    def test_missing_service_token_fails_closed(self):
        with patch.dict(os.environ, {"MODEL_GATEWAY_SERVICE_TOKEN": ""}):
            self.assertEqual(self.post().status_code, 503)

    def test_health_is_liveness_not_model_verification(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "service": "model-gateway"})
        self.assertEqual(self.client.get("/docs", headers=self.headers).status_code, 404)

    @patch("model_gateway.app.chat_completion")
    def test_request_size_limit_precedes_parsing(self, call):
        response = self.client.post("/v1/generate", content=b"x" * (TEXT_REQUEST_LIMIT + 65537), headers=self.headers)
        self.assertEqual(response.status_code, 413)
        call.assert_not_called()

    @patch("model_gateway.app.list_models")
    def test_non_generation_request_size_limit_remains_64k(self, listing):
        response = self.client.post("/v1/models", content=b"x" * 65537, headers=self.headers)
        self.assertEqual(response.status_code, 413)
        listing.assert_not_called()

    @patch("model_gateway.app.chat_completion")
    def test_validation_does_not_echo_secrets(self, call):
        payload = copy.deepcopy(self.payload)
        payload["provider"]["api_key"] = "must-not-echo-secret"
        response = self.post(payload)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("must-not-echo-secret", response.text)
        self.assertNotIn("synthetic-private-input", response.text)
        call.assert_not_called()

    def test_unknown_protocol_and_unsupported_roles_fail(self):
        payload = copy.deepcopy(self.payload)
        payload["provider"]["protocol"] = "unimplemented"
        self.assertEqual(self.post(payload).status_code, 422)
        payload = copy.deepcopy(self.payload)
        payload["messages"][0]["role"] = "tool"
        self.assertEqual(self.post(payload).status_code, 422)

    @patch("model_gateway.app.chat_completion", return_value={"content": "synthetic-result", "prompt_tokens": None, "completion_tokens": None})
    def test_timeout_boundaries_precede_outbound(self, call):
        for timeout in (20, 300, 600, 0, 601, True, False, float("nan"), float("inf"), float("-inf")):
            payload = copy.deepcopy(self.payload)
            payload["model"]["timeout_seconds"] = timeout
            call.reset_mock()
            with self.subTest(timeout=timeout):
                response = self.client.post("/v1/generate", content=json.dumps(payload),
                    headers={**self.headers, "Content-Type": "application/json"})
                if type(timeout) is int and 1 <= timeout <= 600:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(call.call_args.args[1]["timeout_seconds"], timeout)
                else:
                    self.assertEqual(response.status_code, 422)
                    call.assert_not_called()

    @patch("model_gateway.app.chat_completion")
    def test_invalid_message_content_still_fails_closed(self, call):
        for content in ("", [], {"invalid": True}):
            payload = copy.deepcopy(self.payload)
            payload["messages"][0]["content"] = content
            with self.subTest(content=content):
                self.assertEqual(self.post(payload).status_code, 422)
        call.assert_not_called()

    @patch("model_gateway.app.chat_completion", return_value={"content": "synthetic-result", "prompt_tokens": None, "completion_tokens": None})
    def test_business_call_and_missing_usage(self, call):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "synthetic-result")
        self.assertIsNone(response.json()["prompt_tokens"])
        self.assertGreaterEqual(response.json()["duration_ms"], 0)
        self.assertEqual(call.call_args.args[2], self.payload["messages"])

    @patch("model_gateway.app.chat_completion", return_value={"content": "synthetic-result", "prompt_tokens": 1, "completion_tokens": 1})
    def test_business_call_forwards_long_utf8_message(self, call):
        text = "中文" * 12000
        payload = copy.deepcopy(self.payload)
        payload["messages"] = [{"role": "user", "content": text}]

        response = self.post(payload)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(len(text), 16000)
        self.assertGreater(len(text.encode("utf-8")), 65536)
        self.assertEqual(call.call_args.args[2], payload["messages"])

    @patch("model_gateway.app.stream_completion")
    def test_stream_forwards_long_utf8_message(self, call):
        text = "中文" * 12000
        payload = copy.deepcopy(self.payload)
        payload["messages"] = [{"role": "user", "content": text}]
        stream = MagicMock()
        stream.__next__.side_effect = [
            {"delta": "收到"}, {"done": True, "prompt_tokens": 1, "completion_tokens": 1}, StopIteration,
        ]
        call.return_value = stream

        response = self.client.post("/v1/generate-stream", json=payload, headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("收到", response.text)
        self.assertGreater(len(text), 16000)
        self.assertGreater(len(text.encode("utf-8")), 65536)
        self.assertEqual(call.call_args.args[2], payload["messages"])

    @patch("model_gateway.app.chat_completion")
    def test_generate_total_body_limit_rejects_before_outbound(self, call):
        total_limit = TEXT_REQUEST_LIMIT + 65536
        text = "长" * (total_limit // 3 + 1)
        payload = copy.deepcopy(self.payload)
        payload["messages"] = [{"role": "user", "content": text}]
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        self.assertGreater(len(body), total_limit)
        response = self.client.post("/v1/generate", content=body,
                                    headers={**self.headers, "Content-Type": "application/json"})

        self.assertEqual(response.status_code, 413)
        call.assert_not_called()

    @patch("model_gateway.app.chat_completion", return_value={"content": "do-not-return-test-output", "prompt_tokens": 8, "completion_tokens": 1})
    def test_connection_probe_overrides_input_and_restricts_tokens(self, call):
        self.payload["purpose"] = "test"
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["content"])
        self.assertNotIn("do-not-return-test-output", response.text)
        self.assertEqual(call.call_args.args[2], [{"role": "user", "content": "Reply with OK."}])
        self.assertEqual(call.call_args.kwargs["max_output_tokens"], 16)

    @patch("model_gateway.app.chat_completion")
    def test_bounded_concurrency_rejects_without_call(self, call):
        slots.acquire()
        slots.acquire()
        try:
            self.assertEqual(self.post().status_code, 429)
            call.assert_not_called()
        finally:
            slots.release()
            slots.release()

    @patch("model_gateway.app.chat_completion", side_effect=GatewayError("rate_limited", "模型服务限流。", 429))
    def test_safe_transport_error_and_released_capacity(self, call):
        self.assertEqual(self.post().status_code, 429)
        self.assertTrue(slots.acquire(blocking=False))
        slots.release()

    @patch("model_gateway.app.chat_completion", side_effect=RuntimeError("private-upstream-key"))
    def test_unexpected_error_does_not_escape(self, call):
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-upstream-key", response.text)

    @patch("model_gateway.app.chat_completion", return_value={"content": "result", "prompt_tokens": 2, "completion_tokens": 3})
    def test_switch_provider_and_model_changes_no_business_input(self, call):
        self.assertEqual(self.post().status_code, 200)
        self.payload["provider"]["base_url"] = "https://second.example/v1"
        self.payload["provider"]["api_key_env"] = "PORTAL_MODEL_KEY_SECOND"
        self.payload["model"]["model_name"] = "second-model"
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(call.call_args.args[0]["base_url"], "https://second.example/v1")
        self.assertEqual(call.call_args.args[1]["model_name"], "second-model")
        self.assertEqual(call.call_args_list[0].args[2], call.call_args_list[1].args[2])
