"""Real Harness kernel checks with isolated enterprise model/knowledge transports."""
import json
import os
import threading
import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from portal import product_assistant_runtime as runtime
from portal import product_assistant_tools as tool_module
from portal.product_service import ProductError


CONFIG = ("https://knowledge.example.test/api/v1/retrieval", "test-only-token", "product_knowledge")
SCOPE = {"datasets": {"dataset-1": ["document-1"]}}


def tool_call(name, arguments, identifier="call-1"):
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


def complete(content="", calls=()):
    return {"done": True, "content": content, "tool_calls": list(calls),
            "prompt_tokens": 12, "completion_tokens": 5}


def answer(text):
    yield {"delta": text}
    yield complete(text)


class AssistantRuntimeTests(SimpleTestCase):
    def setUp(self):
        self.assertTrue(runtime.runtime_status()["available"], "Install the pinned services/business/harness kernel")
        self.guard = Mock()
        patcher = patch.object(tool_module.knowledge, "configuration", return_value=CONFIG)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stream(self, **options):
        return runtime.run(None, options.pop("question", "读取设备说明"), options.pop("history", []),
                           SCOPE, CONFIG, recheck=self.guard, **options)

    def test_chat_and_calculation_use_real_kernel_without_knowledge_configuration(self):
        rounds = []

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            self.assertEqual(purpose, CONFIG[2])
            self.assertEqual({item["function"]["name"] for item in tools}, {"calculate", "plan"})
            if len(rounds) == 1:
                yield complete(calls=[tool_call("calculate", {"expression": "0.1+0.2"})])
            else:
                self.assertIn('"0.3"', messages[-1]["content"])
                yield from answer("合计0.3。")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.knowledge, "retrieve") as retrieve:
            events = list(runtime.run(None, "计算0.1+0.2", [], {"datasets": {}}, None,
                                      purpose_code=CONFIG[2], recheck=self.guard))
        self.assertEqual(events[-1]["result"]["answer"], "合计0.3。")
        retrieve.assert_not_called()

    def test_placeholder_recovers_with_history_and_a_real_tool_result(self):
        rounds = []
        history = [{"question": "原先每组3台设备", "answer": "共2组。"},
                   {"question": "继续计算总数", "answer": " [Tool call omitted]\n"}]

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            self.assertEqual(messages[1:4], [
                {"role": "user", "content": history[0]["question"]},
                {"role": "assistant", "content": history[0]["answer"]},
                {"role": "user", "content": history[1]["question"]}])
            self.assertIn("上一轮未获得有效回答", messages[4]["content"])
            self.assertIn("本轮用户明确提供的公开关键词", messages[0]["content"])
            if len(rounds) == 1:
                self.assertNotIn("[Tool call omitted]", json.dumps(messages))
                yield {"delta": "[Tool "}
                yield {"delta": "call omitted]"}
                yield complete("[Tool call omitted]")
            elif len(rounds) == 2:
                self.assertIn("真实工具调用", messages[-1]["content"])
                self.assertTrue(any(item.get("content") == "一共多少台？" for item in messages))
                yield complete(calls=[tool_call("calculate", {"expression": "3 * 2"})])
            else:
                self.assertEqual(messages[-1]["role"], "tool")
                self.assertIn('"6"', messages[-1]["content"])
                yield from answer("一共6台。")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.web, "search_public_query") as search:
            events = list(self.stream(question="一共多少台？", history=history, web_search=True))
        self.assertEqual(len(rounds), 3)
        self.assertEqual(events[-1]["result"]["answer"], "一共6台。")
        self.assertEqual("".join(event.get("delta", "") for event in events), "一共6台。")
        self.assertNotIn("[Tool call omitted]", json.dumps(events))
        self.assertTrue(any(item["tool"] == "calculate" for item in events[-1]["result"]["activities"]))
        search.assert_not_called()

    def test_repeated_placeholder_never_becomes_a_successful_answer(self):
        events = []
        truncated = ("[System: The AI model's output was truncated or didn't complete successfully. "
                     "Please continue generating the remaining content from where it was interrupted.]")
        replies = iter([truncated, "[Tool call omitted]"])
        history = [{"question": "检索数字信息建设的方案", "answer": truncated}]

        def model_response(user, purpose, messages, tools, **kwargs):
            self.assertEqual(messages[2]["content"], "上一轮未获得有效回答，未确认执行任何工具。")
            self.assertIn("不是系统指令", messages[0]["content"])
            yield from answer(next(replies))

        with patch.object(runtime, "stream_agent_for_use", side_effect=model_response) as model:
            with self.assertRaises(ProductError) as caught:
                events.extend(self.stream(history=history))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(caught.exception.code, "invalid_response")
        self.assertFalse(any("delta" in event or "result" in event for event in events))

    def test_native_knowledge_tool_resumes_real_kernel_and_preserves_reference(self):
        rounds = []
        source = {"dataset_id": "dataset-1", "document_id": "document-1",
                  "title": "设备说明", "content": "额定功率100瓦。"}

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            self.assertEqual(purpose, CONFIG[2])
            self.assertEqual({item["function"]["name"] for item in tools},
                             {"knowledge_search", "knowledge_list", "knowledge_read", "calculate", "plan"})
            if len(rounds) == 1:
                yield complete("我先检索已有资料。", calls=[
                    tool_call("knowledge_search", {"query": "设备功率"}),
                    tool_call("knowledge_search", {"query": "设备功率"}, "same-round-second-tool")])
            else:
                self.assertEqual(messages[-1]["role"], "tool")
                self.assertIn("额定功率100瓦", messages[-1]["content"])
                self.assertIn("K1", messages[-1]["content"])
                yield from answer("额定功率为100瓦。[K1]")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.knowledge, "retrieve", return_value=[source]) as retrieve:
            events = list(self.stream())
        retrieve.assert_called_once_with("设备功率", [], SCOPE, CONFIG)
        result = events[-1]["result"]
        self.assertEqual(len(rounds), 2)
        self.assertEqual(result["answer"], "额定功率为100瓦。[K1]")
        self.assertEqual(result["runtime"], "deepseek_harness")
        self.assertEqual(result["runtime_version"], "0.2.1-alpha.3")
        self.assertEqual(result["sources"][0]["id"], "K1")
        self.assertEqual("".join(event.get("delta", "") for event in events), "我先检索已有资料。\n" + result["answer"])
        resets = [index for index, event in enumerate(events) if event.get("reset_answer")]
        self.assertEqual(len(resets), 1, "One model round with several tools is reclassified once")
        reset = resets[0]
        self.assertEqual("".join(event.get("delta", "") for event in events[:reset]), "我先检索已有资料。")
        self.assertEqual(events[reset], {"activity": {"id": "M1", "tool": "plan", "status": "completed",
                                                     "summary": "我先检索已有资料。"}, "reset_answer": True})
        self.assertEqual(events[reset + 1]["activity"]["tool"], "knowledge_search")
        self.assertEqual("".join(event.get("delta", "") for event in events[reset + 1:]), "\n" + result["answer"])
        self.assertIn(events[reset]["activity"], result["activities"])
        self.assertGreater(self.guard.call_count, 5)

    def test_invalid_document_reference_returns_feedback_and_model_can_recover(self):
        rounds = []

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            if len(rounds) == 1:
                yield complete(calls=[tool_call("knowledge_read", {
                    "dataset_id": "dataset-1", "document_id": "wrong-document"})])
            elif len(rounds) == 2:
                self.assertIn("invalid_tool_arguments", messages[-1]["content"])
                yield complete(calls=[tool_call("knowledge_read", {
                    "dataset_id": "dataset-1", "document_id": "document-1"}, "corrected")])
            else:
                self.assertIn("供配电设备方案", messages[-1]["content"])
                yield from answer("已读取供配电设备方案。[K1]")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.knowledge, "list_chunks", return_value={"document": {"name": "设备方案"},
                    "chunks": [{"content": "供配电设备方案"}], "has_more": False}) as read:
            result = list(self.stream())[-1]["result"]
        read.assert_called_once_with("dataset-1", "document-1", 1, 4, CONFIG)
        self.assertEqual(result["answer"], "已读取供配电设备方案。[K1]")
        self.assertEqual(result["sources"][0]["document_id"], "document-1")

    def test_project_search_preserves_structured_answer_and_real_public_reference(self):
        calls = []
        text = ("找到1个相关项目。检索日期：2026-10-15；范围：山西煤炭工程公开资料。\n\n"
                "| 项目名称 | 行业 | 地区 | 项目阶段 | 业主或招标单位 | 发布日期 | 来源 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| 示例矿区供电工程 | 煤炭 | 山西 | 招标公告 | 未披露 | 2026-10-14 | [W1] |")

        def model(user, purpose, messages, tools, **kwargs):
            calls.append(messages)
            system = messages[0]["content"]
            self.assertIn("短问题短答，普通对话不套复杂模板", system)
            self.assertIn("工程项目检索优先使用简洁Markdown表格", system)
            self.assertIn("不把网页发布日期当作项目进度日期", system)
            if len(calls) == 1:
                yield complete(calls=[tool_call("web_search", {"query": "山西煤炭工程项目"})])
            else:
                self.assertIn("W1", messages[-1]["content"])
                yield from answer(text)

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.web, "search_public_query", return_value=[{
                    "title": "示例矿区供电工程招标公告", "url": "https://example.test/tender",
                    "text": "山西煤炭行业，示例矿区供电工程招标公告，发布日期2026-10-14。"}]) as search:
            result = list(self.stream(question="山西煤炭工程项目", web_search=True))[-1]["result"]
        search.assert_called_once_with("山西煤炭 工程项目")
        self.assertEqual(result["answer"], text)
        self.assertEqual(result["sources"][0]["id"], "W1")
        self.assertEqual(result["sources"][0]["url"], "https://example.test/tender")

    def test_more_than_two_tools_across_model_steps_return_a_real_read_reference(self):
        calls = [tool_call("plan", {"steps": ["查找资料", "读取原文", "计算数量"]}, "plan"),
                 tool_call("knowledge_list", {}, "list"),
                 tool_call("knowledge_read", {"dataset_id": "dataset-1", "document_id": "document-1"}, "read"),
                 tool_call("calculate", {"expression": "2 * 3"}, "calculate")]
        rounds = []

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            if len(rounds) <= len(calls):
                yield complete(calls=[calls[len(rounds) - 1]])
            else:
                self.assertIn('"value":"6"', messages[-1]["content"].replace(" ", ""))
                yield from answer("按设备资料，合计6台。[K1]")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.knowledge, "list_documents", return_value={"documents": [{"id": "document-1"}]}), patch.object(
                tool_module.knowledge, "list_chunks", return_value={"document": {"name": "设备说明"},
                    "chunks": [{"content": "每组3台，共2组。"}], "has_more": False}) as read:
            events = list(self.stream())
        read.assert_called_once_with("dataset-1", "document-1", 1, 4, CONFIG)
        result = events[-1]["result"]
        self.assertEqual(len(rounds), 5)
        self.assertEqual([item["tool"] for item in result["activities"]],
                         ["plan", "knowledge_list", "knowledge_read", "calculate", "answer"])
        self.assertEqual(result["sources"][0]["content"], "每组3台，共2组。")

    def test_plan_activity_with_emoji_stays_within_browser_summary_limit(self):
        calls = 0

        def model(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                yield complete(calls=[tool_call("plan", {"steps": ["🔎" * 160, "📰" * 160]})])
            else:
                yield from answer("已完成。")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model):
            events = list(self.stream())
        plan = next(event["activity"] for event in events if event.get("activity", {}).get("tool") == "plan"
                    and event["activity"]["status"] == "completed")
        self.assertLessEqual(len(plan["summary"].encode("utf-16-le")) // 2, 500)
        self.assertEqual(events[-1]["result"]["answer"], "已完成。")

    def test_current_date_and_web_capability_override_stale_history(self):
        from datetime import date

        for web in (False, True):
            with self.subTest(web=web):
                def model(user, purpose, messages, tools, **kwargs):
                    system = messages[0]["content"]
                    self.assertIn("当前日期：2026-10-15", system)
                    self.assertIn("必须核对来源日期", system)
                    self.assertIn("本轮自动联网可用" if web else "本轮联网工具不可用", system)
                    names = {item["function"]["name"] for item in tools}
                    self.assertEqual({"web_search", "web_fetch"} & names,
                                     {"web_search", "web_fetch"} if web else set())
                    self.assertIn("无需用户手动开启或再次确认", system)
                    self.assertIn(tool_module.PUBLIC_QUERY_GUIDANCE, system)
                    self.assertIn("正文读取失败时明确正文未读", system)
                    self.assertIn("普通闲聊不必检索", system)
                    self.assertIn("时效问题在网页工具可用时主动检索", system)
                    self.assertIn("知识不足时，可使用网页工具补充公开资料", system)
                    self.assertIn("公开工程项目信息可依据网页整理为带W来源、日期和核验状态的公开项目线索", system)
                    self.assertIn("不能自动纳入或改写企业内部或用户本项目事实", system)
                    self.assertIn("适用于煤炭、水电、交通等行业，不限固定分类", system)
                    self.assertIn("优先使用业主、政府、公共资源交易平台等原始来源", system)
                    self.assertIn("核对行业、地区、发布日期与项目阶段", system)
                    self.assertIn("不能据招标或中标公告推断已开工", system)
                    self.assertIn("未核验的信息标注待核验，不编造项目阶段", system)
                    yield from answer("已按当前日期和联网状态处理。")

                with patch.object(runtime.timezone, "localdate", return_value=date(2026, 10, 15)), patch.object(
                        runtime, "stream_agent_for_use", side_effect=model):
                    events = list(self.stream(web_search=web, history=[{
                        "question": "今天的新闻", "answer": "今天是2026年7月，联网未开启。"}]))
                self.assertIn("result", events[-1])

    def test_public_delta_arrives_while_model_completion_is_still_blocked(self):
        release, waiting = threading.Event(), threading.Event()
        text = "这是一段可以公开给用户的回答。" * 12

        def model(*args, **kwargs):
            yield {"delta": text}
            waiting.set()
            if not release.wait(4):
                raise AssertionError("The host must publish a real delta before model completion")
            yield complete(text)

        with patch.object(runtime, "stream_agent_for_use", side_effect=model):
            stream = self.stream(question="你好")
            seen, first_delta = [], False
            try:
                for event in stream:
                    seen.append(event)
                    if "delta" in event and not first_delta:
                        first_delta = True
                        self.assertTrue(waiting.is_set())
                        self.assertFalse(release.is_set())
                        self.assertNotIn("result", event)
                        release.set()
                self.assertTrue(first_delta)
                self.assertEqual(seen[-1]["result"]["answer"], text)
                self.assertEqual("".join(event.get("delta", "") for event in seen), text)
            finally:
                release.set()
                stream.close()

    def test_split_private_reasoning_never_reaches_user_deltas(self):
        def model(*args, **kwargs):
            yield {"delta": "<thi"}
            yield {"delta": "nk>不能泄漏的推理</think>回答"}
            yield complete("<think>不能泄漏的推理</think>回答")

        seen = []
        with patch.object(runtime, "stream_agent_for_use", side_effect=model), self.assertRaises(ProductError) as caught:
            for event in self.stream():
                seen.append(event)
        self.assertEqual(caught.exception.code, "invalid_response")
        self.assertFalse(any("delta" in event for event in seen))
        self.assertNotIn("不能泄漏", json.dumps(seen, ensure_ascii=False))

    def test_unknown_citation_cannot_become_a_completed_answer(self):
        for citation in ("K99", "W99", "S1"):
            with self.subTest(citation=citation):
                seen = []
                with patch.object(runtime, "stream_agent_for_use", side_effect=lambda *args, **kwargs: answer(f"未经检索的结论[{citation}]")) as model:
                    with self.assertRaises(ProductError) as caught:
                        for event in self.stream():
                            seen.append(event)
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertEqual(model.call_count, 2, "A repeated invalid citation must stop after one correction")
                self.assertFalse(any("result" in event or "delta" in event for event in seen))

    def test_legacy_citation_is_removed_from_history_and_corrected_without_current_sources(self):
        history = [{"question": "旧知识问答", "answer": "旧项目结论。[S1]",
                    "sources": [{"id": "S1", "content": "旧资料。"}]}]
        rounds = []
        final = "本轮尚未读取资料，无法核验旧项目结论。"

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            self.assertEqual(messages[2]["content"], "旧项目结论。")
            if len(rounds) == 1:
                yield from answer("沿用旧项目结论。[S1]")
            else:
                self.assertIn("本轮可引用编号：无", messages[-1]["content"])
                yield from answer(final)

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.knowledge, "retrieve") as retrieve:
            events = list(self.stream(question="继续总结", history=history))
        self.assertEqual(len(rounds), 2)
        self.assertEqual(events[-1]["result"]["answer"], final)
        self.assertEqual(events[-1]["result"]["sources"], [])
        self.assertNotIn("[S1]", "".join(event.get("delta", "") for event in events))
        self.assertEqual(history[0]["answer"], "旧项目结论。[S1]")
        retrieve.assert_not_called()

    def test_explicit_web_request_cannot_reuse_history_without_executing_search(self):
        rounds = []

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            if len(rounds) == 1:
                self.assertEqual(kwargs["tool_choice"], "required")
                yield from answer("已经找到相关项目。")
            elif len(rounds) == 2:
                self.assertEqual(kwargs["tool_choice"], {"type": "function", "function": {"name": "web_search"}})
                self.assertIn("没有执行web_search", messages[-1]["content"])
                yield complete(calls=[tool_call("web_search", {"query": "榆林市网络安全项目"})])
            else:
                yield from answer("找到一条公开招标公告，尚未核验开工情况。[W1]")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.web, "search_public_query", return_value=[{
                    "title": "榆林市网络安全项目公告", "url": "https://example.test/current",
                    "text": "公开招标公告。"}]) as search:
            events = list(self.stream(question="检索榆林市有关网络安全的项目，并联网检索，", web_search=True))
        search.assert_called_once_with("榆林市 网络安全 项目")
        self.assertEqual(len(rounds), 3)
        self.assertNotIn("已经找到", "".join(event.get("delta", "") for event in events))
        self.assertEqual(events[-1]["result"]["sources"][0]["id"], "W1")
        self.assertEqual(sum(bool(event.get("reset_answer")) for event in events), 1)

    def test_explicit_no_web_request_does_not_force_search(self):
        with patch.object(runtime, "stream_agent_for_use", side_effect=lambda *args, **kwargs: answer("2")) as model:
            result = list(self.stream(question="不要联网检索，计算1+1", web_search=True))[-1]["result"]
        self.assertEqual(result["answer"], "2")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.kwargs["tool_choice"], "auto")

    def test_historical_citation_recovers_using_only_current_authorized_sources(self):
        rounds = []
        history = [{"question": "之前有哪些项目？", "answer": "历史项目线索。[W18]",
                    "sources": [{"id": "W18", "type": "web", "title": "历史公告",
                                 "url": "https://example.test/old", "content": "历史项目。"}]}]
        internal = {"dataset_id": "dataset-1", "document_id": "document-1",
                    "title": "项目清单", "content": "已授权项目清单未确认榆林市网络安全项目。"}
        public = {"title": "榆林市网络安全项目招标公告", "url": "https://example.test/current",
                  "text": "榆林市网络安全项目发布招标公告；开工情况未披露。"}
        final = "企业资料尚未确认该项目。[K1]公开公告为招标阶段，开工情况未披露。[W2]"

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(messages)
            self.assertEqual(messages[2]["content"], "历史项目线索。")
            if len(rounds) == 1:
                yield complete(calls=[
                    tool_call("knowledge_search", {"query": "榆林市网络安全项目"}, "internal"),
                    tool_call("web_search", {"query": "榆林市 网络安全 项目"}, "public")])
            elif len(rounds) == 2:
                self.assertIn("K1", json.dumps(messages, ensure_ascii=False))
                self.assertIn("W2", messages[-1]["content"])
                yield from answer("可先说明检索范围。" * 20 + "错误沿用了历史公告。[W18]后续内容。")
            else:
                self.assertEqual(len(rounds), 3, "Only one citation correction is permitted")
                self.assertIn("K1", messages[-1]["content"])
                self.assertIn("W2", messages[-1]["content"])
                yield from answer(final)

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.knowledge, "retrieve", return_value=[internal]) as retrieve, patch.object(
                tool_module.web, "search_public_query", return_value=[public]) as search:
            events = list(self.stream(question="检索榆林市有关网络安全的项目，并联网检索，",
                                      history=history, web_search=True))
        retrieve.assert_called_once_with("榆林市网络安全项目", [], SCOPE, CONFIG)
        search.assert_called_once()
        self.assertEqual(len(rounds), 3)
        result = events[-1]["result"]
        self.assertEqual(result["answer"], final)
        self.assertEqual([(source["id"], source["content"]) for source in result["sources"]],
                         [("K1", internal["content"]), ("W2", public["text"])])
        self.assertNotIn("[W18]", "".join(event.get("delta", "") for event in events))
        resets = [index for index, event in enumerate(events) if event.get("reset_answer")]
        self.assertEqual(len(resets), 1)
        visible = ""
        for event in events:
            if event.get("reset_answer"):
                visible = ""
            visible += event.get("delta", "")
        self.assertEqual(visible.strip(), final)

    def test_unknown_citation_in_long_native_delta_is_rejected_before_publication(self):
        for citation in ("K99", "W99"):
            with self.subTest(citation=citation):
                text, seen = f"未经检索的结论[{citation}]" + "后续公开说明。" * 20, []
                with patch.object(runtime, "stream_agent_for_use", side_effect=lambda *args, **kwargs: answer(text)):
                    with self.assertRaises(ProductError) as caught:
                        for event in self.stream():
                            seen.append(event)
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertFalse(any("delta" in event or "result" in event for event in seen))

    def test_split_unknown_citation_is_rejected_before_the_closed_tag_is_published(self):
        for citation in ("K99", "W99"):
            with self.subTest(citation=citation):
                prefix = "可以公开的说明。" * 20 + f"[{citation[:-1]}"
                suffix = citation[-1] + "]" + "后续说明。" * 20
                seen = []

                def model(*args, **kwargs):
                    yield {"delta": prefix}
                    yield {"delta": suffix}
                    yield complete(prefix + suffix)

                with patch.object(runtime, "stream_agent_for_use", side_effect=model):
                    with self.assertRaises(ProductError) as caught:
                        for event in self.stream():
                            seen.append(event)
                self.assertEqual(caught.exception.code, "invalid_response")
                published = "".join(event.get("delta", "") for event in seen)
                # A fast completion can withhold the entire invalid attempt before its deltas are read.
                self.assertNotIn("[", published)
                self.assertFalse(any("result" in event for event in seen))

    def test_cancel_kills_kernel_closes_model_and_releases_concurrency_slot(self):
        entered, finished, closed = threading.Event(), threading.Event(), threading.Event()
        errors, observed = [], []
        run_id = "test-" + uuid.uuid4().hex

        def model(*args, cancelled, **kwargs):
            try:
                entered.set()
                self.assertTrue(cancelled.wait(5), "Cancellation must reach the model transport")
                if False:
                    yield {}
            finally:
                closed.set()

        def consume():
            try:
                observed.extend(self.stream(run_id=run_id))
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()

        with patch.object(runtime, "stream_agent_for_use", side_effect=model) as transport:
            worker = threading.Thread(target=consume, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                with runtime._active_lock:
                    process = runtime._active[run_id][0]
                runtime.cancel_run(run_id)
                self.assertTrue(finished.wait(3), "Cancellation must not wait for another model token")
                worker.join(1)
                self.assertIsNotNone(process.poll())
                self.assertTrue(closed.wait(1))
                self.assertEqual(transport.call_count, 1)
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], ProductError)
                self.assertEqual(errors[0].code, "cancelled")
                self.assertNotIn(run_id, runtime._active)
                self.assertFalse(any("result" in event for event in observed))
                acquired = 0
                try:
                    for _ in range(4):
                        self.assertTrue(runtime._slots.acquire(blocking=False))
                        acquired += 1
                    self.assertFalse(runtime._slots.acquire(blocking=False))
                finally:
                    for _ in range(acquired):
                        runtime._slots.release()
            finally:
                runtime.cancel_run(run_id)
                worker.join(3)

    def test_kernel_gets_minimal_environment_and_only_authorized_native_tools(self):
        launches = []
        original = runtime.subprocess.Popen

        def launch(*args, **kwargs):
            process = original(*args, **kwargs)
            launches.append((process, kwargs))
            return process

        def model(user, purpose, messages, tools, **kwargs):
            self.assertEqual({item["function"]["name"] for item in tools},
                             {"knowledge_search", "knowledge_list", "knowledge_read", "calculate", "plan"})
            self.assertNotIn("sensitive-test-value", json.dumps(messages))
            yield from answer("你好。")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sensitive-test-value", "DEEPSEEK_API_KEY": "sensitive-test-value",
                "NODE_OPTIONS": "--import=forbidden-host-plugin", "DSH_HOME": "forbidden-ambient-profile"}), patch.object(
                runtime.subprocess, "Popen", side_effect=launch), patch.object(runtime, "stream_agent_for_use", side_effect=model):
            result = list(self.stream(question="你好"))[-1]["result"]
        self.assertEqual(result["answer"], "你好。")
        self.assertEqual(len(launches), 1)
        process, options = launches[0]
        self.assertEqual(set(options["env"]) - {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"},
                         {"HOME", "USERPROFILE", "DSH_HOME", "NO_COLOR"})
        self.assertEqual(options["env"]["DSH_HOME"], options["cwd"])
        self.assertNotIn("sensitive-test-value", str(options["env"]))
        self.assertFalse(os.path.exists(options["cwd"]), "The per-turn workspace must be removed")
        self.assertIsNotNone(process.poll())

    def test_budget_reserves_a_final_answer_without_removing_historical_tool_schemas(self):
        for limit, count, expected_rounds in (("model", 1, 7), ("tools", 2, 7)):
            with self.subTest(limit=limit):
                rounds = []

                def model(user, purpose, messages, tools, **kwargs):
                    rounds.append(True)
                    self.assertIn("calculate", {item["function"]["name"] for item in tools})
                    if len(rounds) == expected_rounds:
                        self.assertEqual(kwargs["tool_choice"], "none")
                        self.assertIn("检索预算已用尽，停止工具调用", messages[0]["content"])
                        self.assertIn("资料缺口或待核验", messages[0]["content"])
                        yield from answer("已有计算结果为2；其余信息待核验。")
                    else:
                        self.assertEqual(kwargs["tool_choice"], "auto")
                        yield complete(calls=[tool_call("calculate", {"expression": "1 + 1"},
                            f"round-{len(rounds)}-{index}") for index in range(count)])

                with patch.object(runtime, "stream_agent_for_use", side_effect=model):
                    result = list(self.stream())[-1]["result"]
                self.assertEqual(len(rounds), expected_rounds)
                self.assertEqual(result["answer"], "已有计算结果为2；其余信息待核验。")
                self.assertEqual(len([item for item in result["activities"] if item["tool"] == "calculate"]),
                                 (expected_rounds - 1) * count)

    def test_tool_batch_crossing_budget_skips_extra_execution_and_still_answers(self):
        rounds = []

        def model(user, purpose, messages, tools, **kwargs):
            rounds.append(True)
            if len(rounds) <= 2:
                yield complete(calls=[tool_call("calculate", {"expression": "1 + 1"},
                    f"batch-{len(rounds)}-{index}") for index in range(11 if len(rounds) == 1 else 2)])
            else:
                self.assertEqual(kwargs["tool_choice"], "none")
                self.assertIn("tool_budget_exhausted", messages[-1]["content"])
                self.assertIn("未执行", messages[-1]["content"])
                yield from answer("现有计算结果为2；超出预算的工具未执行。")

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                tool_module.AssistantTools, "execute", autospec=True,
                side_effect=tool_module.AssistantTools.execute) as execute:
            result = list(self.stream())[-1]["result"]
        self.assertEqual(execute.call_count, 12)
        self.assertEqual(len(rounds), 3)
        self.assertEqual(result["answer"], "现有计算结果为2；超出预算的工具未执行。")

    def test_source_budget_reserves_next_model_round_for_final_answer(self):
        for batches in ((24,), (23, 2)):
            with self.subTest(batches=batches):
                rounds = []
                sources = [[{"dataset_id": "dataset-1", "document_id": "document-1", "title": "设备资料",
                             "content": f"资料{batch}-{index}"} for index in range(count)]
                           for batch, count in enumerate(batches)]

                def model(user, purpose, messages, tools, **kwargs):
                    rounds.append(True)
                    if len(rounds) == 1:
                        yield complete(calls=[tool_call("knowledge_search", {"query": f"设备{index}"}, f"sources-{index}")
                                              for index in range(len(batches))])
                    else:
                        self.assertEqual(kwargs["tool_choice"], "none")
                        if len(batches) == 2:
                            self.assertIn("source_budget", messages[-1]["content"])
                        yield from answer("已有设备资料可供参考。[K1] 其余资料尚待核验。")

                with patch.object(runtime, "stream_agent_for_use", side_effect=model), patch.object(
                        tool_module.knowledge, "retrieve", side_effect=sources) as retrieve:
                    result = list(self.stream())[-1]["result"]
                self.assertEqual(len(rounds), 2)
                self.assertEqual(retrieve.call_count, len(batches))
                self.assertEqual(len(result["sources"]), batches[0])
                self.assertIn("待核验", result["answer"])

    def test_eight_model_call_budget_ends_real_native_tool_loop(self):
        rounds = []

        def model(*args, **kwargs):
            rounds.append(True)
            self.assertEqual(kwargs["tool_choice"], "none" if len(rounds) >= 7 else "auto")
            yield complete(calls=[tool_call("calculate", {"expression": "1 + 1"}, "loop-" + str(len(rounds)))])

        with patch.object(runtime, "stream_agent_for_use", side_effect=model), self.assertRaises(ProductError) as caught:
            list(self.stream())
        self.assertEqual(caught.exception.code, "assistant_budget")
        self.assertEqual(len(rounds), 8)


class AssistantToolBoundaryTests(SimpleTestCase):
    def setUp(self):
        patcher = patch.object(tool_module.knowledge, "configuration", return_value=CONFIG)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tools(self, *, web=False, question="Python官方文档"):
        return tool_module.AssistantTools(question, SCOPE, CONFIG, web_search=web, recheck=lambda: None)

    def test_model_cannot_expand_knowledge_scope_or_add_unregistered_tools(self):
        tools = self.tools()
        with patch.object(tool_module.knowledge, "retrieve") as retrieve, patch.object(
                tool_module.knowledge, "list_chunks") as read, patch.object(
                tool_module.knowledge, "list_documents") as listing:
            for name, args in (("knowledge_list", {"dataset_id": "other"}),
                               ("knowledge_read", {"dataset_id": "other", "document_id": "document-1"}),
                               ("knowledge_read", {"dataset_id": "dataset-1", "document_id": "other"})):
                with self.subTest(tool=name, arguments=args):
                    result = tools.execute(name, args)
                    self.assertEqual(result["error"], "invalid_tool_arguments")
            for name, args in (("knowledge_search", {"query": "设备", "dataset_id": "other"}),
                               ("shell", {"command": "whoami"})):
                with self.subTest(tool=name), self.assertRaises(ProductError):
                    tools.execute(name, args)
            retrieve.assert_not_called()
            read.assert_not_called()
            listing.assert_not_called()

    def test_real_authorization_errors_terminate_even_after_invalid_reference(self):
        for status in (401, 403):
            for origin in ("recheck", "configuration", "list_chunks"):
                with self.subTest(status=status, origin=origin):
                    tools = self.tools()
                    error = ProductError("scope_revoked", "授权已撤销", status)
                    arguments = {"dataset_id": "dataset-1", "document_id": "document-1"}
                    if origin == "recheck":
                        arguments["document_id"] = "other"
                        tools.recheck = Mock(side_effect=[None, error])
                    with patch.object(tool_module.knowledge, "configuration",
                                      side_effect=error if origin == "configuration" else None,
                                      return_value=CONFIG), patch.object(
                            tool_module.knowledge, "list_chunks", side_effect=error) as read:
                        with self.assertRaises(ProductError) as caught:
                            tools.execute("knowledge_read", arguments)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(tools.sources, [])
                    if origin != "list_chunks":
                        read.assert_not_called()

    def test_public_query_and_fetch_never_send_history_or_unapproved_urls(self):
        tools = self.tools(web=True)
        with patch.object(tool_module.web, "search_public_query") as search, patch.object(
                tool_module, "fetch_public_page") as fetch:
            result = tools.execute("web_search", {"query": "秘密客户预算"})
            self.assertEqual(result["error"], "public_query_only")
            result = tools.execute("web_fetch", {"url": "https://private.example.test/secret"})
            self.assertEqual(result["error"], "invalid_tool_arguments")
            search.assert_not_called()
            fetch.assert_not_called()
        with self.assertRaises(ProductError):
            self.tools().execute("web_search", {})

    def test_tool_budget_and_original_schema_bounds_remain_enforced_by_python(self):
        tools = self.tools()
        for _ in range(12):
            self.assertEqual(tools.execute("calculate", {"expression": "0.1 + 0.2"})["value"], "0.3")
        with self.assertRaises(ProductError) as caught:
            tools.execute("calculate", {"expression": "1 + 1"})
        self.assertEqual(caught.exception.code, "assistant_budget")
        for args in ({"query": ""}, {"query": "x" * 2001}):
            with self.subTest(arguments=len(args["query"])), self.assertRaises(ProductError):
                self.tools().execute("knowledge_search", args)
        result = self.tools().execute("calculate", {"expression": "__import__('os').system('whoami')"})
        self.assertEqual(result["error"], "invalid_tool_arguments")
