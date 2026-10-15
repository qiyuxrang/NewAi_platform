"""Per-turn reuse and public-query projection without real outbound requests."""
from datetime import date
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from portal import product_assistant_tools as tools
from portal.product_service import ProductError
from .test_product_knowledge_service import CONFIG, SCOPE


class AssistantToolEfficiencyTests(SimpleTestCase):
    def setUp(self):
        self.configuration = patch.object(tools.knowledge, "configuration", return_value=CONFIG)
        self.config_check = self.configuration.start()
        self.addCleanup(self.configuration.stop)

    def toolbox(self, question="请检索 Python 官方文档 和 C++ C#"):
        return tools.AssistantTools(question, SCOPE, CONFIG, web_search=True, recheck=Mock())

    def test_repeated_success_reuses_sources_and_checks_authority(self):
        toolbox = self.toolbox()
        source = {"dataset_id": "dataset-1", "document_id": "document-1", "title": "文件", "content": "事实"}
        with patch.object(tools.knowledge, "retrieve", return_value=[source]) as retrieve:
            first = toolbox.execute("knowledge_search", {"query": "设备 功率"})
            again = toolbox.execute("knowledge_search", {"query": "设备  功率"})
        retrieve.assert_called_once()
        self.assertEqual(first["sources"], again["sources"])
        self.assertEqual(len(toolbox.sources), 1)
        self.assertTrue(again["tool_status"]["cached"])
        self.assertEqual(first["tool_status"]["new_evidence"], 1)
        self.assertEqual(again["tool_status"]["new_evidence"], 0)
        self.assertEqual(toolbox.recheck.call_count, 4)
        self.assertEqual(self.config_check.call_count, 4)

    def test_repeated_provider_failure_is_cached_but_new_query_can_run(self):
        toolbox = self.toolbox()
        with patch.object(tools.web, "search_public_query", side_effect=ProductError("web_search_unavailable", "暂不可用", 503)) as search:
            first = toolbox.execute("web_search", {"query": "Python 官方文档"})
            again = toolbox.execute("web_search", {"query": "官方文档， Python"})
            toolbox.execute("web_search", {"query": "Python"})
        self.assertEqual(search.call_count, 2)
        self.assertEqual(first["error"], again["error"])
        self.assertTrue(again["tool_status"]["cached"])
        self.assertEqual(again["tool_status"]["consecutive_no_new_evidence"], 2)

    def test_cached_results_never_bypass_cancellation_or_revocation(self):
        for code, status in (("scope_revoked", 403), ("cancelled", 409)):
            for guard_call in (0, 1):
                with self.subTest(code=code, guard_call=guard_call):
                    toolbox = self.toolbox()
                    with patch.object(tools.web, "search_public_query", return_value=[]) as search:
                        toolbox.execute("web_search", {"query": "Python"})
                        toolbox.recheck.side_effect = [None] * guard_call + [ProductError(code, "已停止", status)] * 3
                        with self.assertRaises(ProductError) as caught:
                            toolbox.execute("web_search", {"query": "Python"})
                    self.assertEqual(caught.exception.code, code)
                    search.assert_called_once()

    def test_changed_or_disabled_knowledge_configuration_blocks_cached_content(self):
        toolbox = self.toolbox()
        with patch.object(tools.knowledge, "retrieve", return_value=[]) as retrieve:
            toolbox.execute("knowledge_search", {"query": "设备"})
            self.config_check.return_value = (CONFIG[0], "changed-token", CONFIG[2])
            changed = toolbox.execute("knowledge_search", {"query": "设备"})
            self.config_check.side_effect = ProductError("disabled", "知识已关闭", 503)
            disabled = toolbox.execute("knowledge_search", {"query": "设备"})
        retrieve.assert_called_once()
        self.assertEqual(changed["error"], "knowledge_unavailable")
        self.assertEqual(disabled["error"], "disabled")
        self.assertNotIn("sources", changed)
        self.assertNotIn("sources", disabled)

    def test_public_query_accepts_only_projection_of_current_question_terms(self):
        toolbox = self.toolbox()
        with patch.object(tools.web, "search_public_query", return_value=[]) as search:
            toolbox.execute("web_search", {"query": "官方文档，  Python！"})
            search.assert_called_once_with("Python 官方文档")
            toolbox.execute("web_search", {"query": "Python 官方文档"})
            self.assertEqual(search.call_count, 1)
            for query in ("Python 秘密预算", "官方文档 企业来源", "历史客户 Python", "秘密预算"):
                result = toolbox.execute("web_search", {"query": query})
                self.assertEqual(result["error"], "public_query_only")
            self.assertEqual(search.call_count, 1)

    def test_public_additions_keep_question_topics_and_share_canonical_cache(self):
        toolbox = self.toolbox("检索煤炭、水电、交通相关工程项目")
        with patch.object(tools.timezone, "localdate", return_value=date(2026, 10, 15)), patch.object(
                tools.web, "search_public_query", return_value=[]) as search:
            first = toolbox.execute("web_search", {"query": "煤炭2026年招标公告"})
            again = toolbox.execute("web_search", {"query": "招标公告，2026 煤炭"})
            self.assertTrue(first["summary_only"])
            self.assertTrue(again["tool_status"]["cached"])
            search.assert_called_once_with("煤炭 2026 招标公告")
            toolbox.execute("web_search", {"query": "水电建设进展官网2026年10月"})
            toolbox.execute("web_search", {"query": "交通中标2026年10月15日"})
        self.assertEqual([call.args[0] for call in search.call_args_list],
                         ["煤炭 2026 招标公告", "水电 2026-10 官网 建设进展", "交通 2026-10-15 中标"])

    def test_public_additions_never_allow_private_terms_or_remove_the_topic(self):
        toolbox = self.toolbox("检索煤炭、水电、交通工程项目官网，内部预算八百万仅供理解")
        toolbox.add_source({"dataset_id": "dataset-1", "document_id": "document-1",
                            "title": "企业资料", "content": "秘密客户预算 历史客户造价"})
        with patch.object(tools.timezone, "localdate", return_value=date(2026, 10, 15)), patch.object(
                tools.web, "search_public_query") as search:
            for query in ("煤炭官网秘密客户预算", "水电 招标公告 历史客户造价", "交通 客户名单2026年",
                          "招标公告2026年", "官网2026年", "官网", "工程项目", "煤炭2099招标公告", "煤炭2026-10-14招标公告"):
                with self.subTest(query=query):
                    result = toolbox.execute("web_search", {"query": query})
                    self.assertEqual(result["error"], "public_query_only")
            search.assert_not_called()
        self.assertEqual(len(toolbox.sources), 1)

    def test_configuration_change_during_fetch_rolls_back_sources_and_clears_knowledge_cache(self):
        for disabled in (False, True):
            with self.subTest(disabled=disabled):
                self.config_check.side_effect = None
                self.config_check.return_value = CONFIG
                toolbox = self.toolbox()
                old_source = {"dataset_id": "dataset-1", "document_id": "document-1", "title": "文件", "content": "原证据"}
                with patch.object(tools.knowledge, "retrieve", return_value=[old_source]):
                    first = toolbox.execute("knowledge_search", {"query": "设备"})

                def change_configuration(*args):
                    # Also exercise rollback of changes to an existing source, not just appended rows.
                    toolbox.sources[0]["content"] = "未授权的更长覆盖内容"
                    if disabled:
                        self.config_check.side_effect = ProductError("disabled", "知识已关闭", 503)
                    else:
                        self.config_check.return_value = (CONFIG[0], "changed-token", CONFIG[2])
                    return [{**old_source, "content": "禁止释放的新证据"}]

                with patch.object(tools.knowledge, "retrieve", side_effect=change_configuration) as retrieve:
                    rejected = toolbox.execute("knowledge_search", {"query": "功率"})
                    again = toolbox.execute("knowledge_search", {"query": "设备"})
                retrieve.assert_called_once()
                self.assertIn("error", rejected)
                self.assertIn("error", again)
                self.assertNotIn("sources", rejected)
                self.assertNotIn("sources", again)
                self.assertEqual(toolbox.sources, first["sources"])
                self.assertEqual(toolbox.sources[0]["content"], "原证据")
                self.assertEqual(rejected["tool_status"]["new_evidence"], 0)
                self.assertFalse(any("sources" in result for key, result in toolbox._results.items()
                                     if key[0].startswith("knowledge_")))

    def test_cache_release_checks_configuration_after_global_guard(self):
        toolbox = self.toolbox()
        source = {"dataset_id": "dataset-1", "document_id": "document-1", "title": "文件", "content": "原证据"}
        with patch.object(tools.knowledge, "retrieve", return_value=[source]) as retrieve:
            toolbox.execute("knowledge_search", {"query": "设备"})
            calls = 0

            def disable_after_cache_entry():
                nonlocal calls
                calls += 1
                if calls == 2:
                    self.config_check.side_effect = ProductError("disabled", "知识已关闭", 503)

            toolbox.recheck.side_effect = disable_after_cache_entry
            rejected = toolbox.execute("knowledge_search", {"query": "设备"})
        retrieve.assert_called_once()
        self.assertEqual(rejected["error"], "disabled")
        self.assertNotIn("sources", rejected)
        self.assertFalse(any("sources" in result for key, result in toolbox._results.items()
                             if key[0].startswith("knowledge_")))

    def test_unsafe_rewrite_never_falls_back_to_whole_private_question(self):
        toolbox = self.toolbox("查 Python，内部预算八百万仅供本次理解")
        with patch.object(tools.web, "search_public_query") as search:
            result = toolbox.execute("web_search", {"query": "Python 客户资料"})
        self.assertEqual(result["error"], "public_query_only")
        search.assert_not_called()

    def test_meaningful_search_symbols_and_independent_runs_are_not_collapsed(self):
        with patch.object(tools.web, "search_public_query", return_value=[]) as search:
            toolbox = self.toolbox()
            toolbox.execute("web_search", {"query": "C++"})
            toolbox.execute("web_search", {"query": "C#"})
            self.toolbox().execute("web_search", {"query": "C++"})
        self.assertEqual([call.args[0] for call in search.call_args_list], ["C++", "C#", "C++"])

    def test_empty_queries_do_not_stop_distinct_queries_or_claim_sufficiency(self):
        toolbox = self.toolbox()
        with patch.object(tools.web, "search_public_query", return_value=[]) as search:
            first = toolbox.execute("web_search", {"query": "Python"})
            second = toolbox.execute("web_search", {"query": "官方文档"})
        self.assertEqual(search.call_count, 2)
        self.assertEqual(first["tool_status"]["consecutive_no_new_evidence"], 1)
        self.assertEqual(second["tool_status"]["consecutive_no_new_evidence"], 2)
        self.assertIn("未证实", second["tool_status"]["guidance"])

    def test_fetch_success_and_failure_are_cached_without_expanding_urls(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                toolbox = self.toolbox("读取 https://example.com/manual")
                with patch.object(tools, "fetch_public_page", side_effect=OSError if failure else None,
                                  return_value="公开内容") as fetch:
                    first = toolbox.execute("web_fetch", {"url": "https://example.com/manual"})
                    again = toolbox.execute("web_fetch", {"url": "https://example.com/manual"})
                    rejected = toolbox.execute("web_fetch", {"url": "https://example.com/manual?secret=1"})
                fetch.assert_called_once()
                self.assertEqual("error" in first, failure)
                self.assertTrue(again["tool_status"]["cached"])
                self.assertEqual(rejected["error"], "invalid_tool_arguments")
                if failure:
                    self.assertFalse(first["page_read"])
                    self.assertFalse(first["summary_available"])
                    self.assertIn("不要重试同一网址", first["detail"])
                    self.assertEqual(toolbox.sources, [])
                else:
                    self.assertTrue(first["page_read"])

    def test_failed_page_read_keeps_existing_summary_without_claiming_full_text(self):
        toolbox = self.toolbox("Python")
        found = [{"title": "Python资料", "url": "https://example.com/manual", "text": "仅搜索摘要"}]
        with patch.object(tools.web, "search_public_query", return_value=found):
            summary = toolbox.execute("web_search", {"query": "Python"})
        with patch.object(tools, "fetch_public_page", side_effect=ValueError("redirected")) as fetch:
            failed = toolbox.execute("web_fetch", {"url": found[0]["url"]})
            again = toolbox.execute("web_fetch", {"url": found[0]["url"]})
        fetch.assert_called_once()
        self.assertFalse(failed["page_read"])
        self.assertTrue(failed["summary_available"])
        self.assertIn("不能声称已核验全文", failed["detail"])
        self.assertNotIn("sources", failed)
        self.assertEqual(toolbox.sources, summary["sources"])
        self.assertTrue(again["tool_status"]["cached"])

    def test_knowledge_tools_are_absent_and_direct_execution_fails_closed(self):
        for scope, config in ((SCOPE, None), ({"datasets": {}}, CONFIG)):
            with self.subTest(scope=scope, config=config):
                toolbox = tools.AssistantTools("你好", scope, config, web_search=False, recheck=Mock())
                self.assertEqual({item["function"]["name"] for item in toolbox.schemas}, {"calculate", "plan"})
                with patch.object(tools.knowledge, "retrieve") as retrieve:
                    with self.assertRaises(ProductError):
                        toolbox.execute("knowledge_search", {"query": "设备"})
                    with self.assertRaises(ProductError):
                        toolbox._execute("knowledge_search", {"query": "设备"})
                retrieve.assert_not_called()

    def test_cache_hits_still_consume_real_tool_budget(self):
        toolbox = self.toolbox()
        with patch.object(tools.web, "search_public_query", return_value=[]) as search:
            for _ in range(12):
                toolbox.execute("web_search", {"query": "Python"})
            with self.assertRaises(ProductError) as caught:
                toolbox.execute("web_search", {"query": "Python"})
        self.assertEqual(caught.exception.code, "assistant_budget")
        search.assert_called_once()

    def test_source_budget_is_terminal_feedback_and_rolls_back_partial_web_sources(self):
        toolbox = self.toolbox()
        for index in range(23):
            toolbox.add_source({"dataset_id": "dataset-1", "document_id": "document-1",
                                "title": "文件", "content": f"原证据{index}"})
        found = [{"title": f"网页{index}", "url": f"https://example.com/{index}", "text": "公开资料"}
                 for index in range(2)]
        with patch.object(tools.web, "search_public_query", return_value=found) as search:
            result = toolbox.execute("web_search", {"query": "Python"})
            again = toolbox.execute("web_search", {"query": "Python"})
        search.assert_called_once()
        self.assertEqual(result["error"], "source_budget")
        self.assertIn("停止新增检索", result["detail"])
        self.assertEqual(result["tool_status"]["new_evidence"], 0)
        self.assertEqual(len(toolbox.sources), 23)
        self.assertFalse(any(item["type"] == "web" for item in toolbox.sources))
        self.assertEqual(again["error"], "source_budget")
        self.assertTrue(again["tool_status"]["cached"])
