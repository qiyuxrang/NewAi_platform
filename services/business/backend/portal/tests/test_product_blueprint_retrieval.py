"""Blueprint retrieval budgets and complete-input cache keys; mocked HTTP/ORM only."""
import copy
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from portal import product_blueprint_knowledge as blueprint
from portal import product_knowledge_service as service
from portal.product_models import DocumentTask
from portal.product_service import ProductError
from portal.product_web_search import evidence_coverage, public_queries, technical_domains

from .test_product_knowledge_service import CONFIG, SCOPE, Response, chunk, wire


class ProductBlueprintRetrievalTests(SimpleTestCase):
    def payload(self):
        return {"project": "项目优先信息", "requirements": "需求优先信息" + "长" * 10000,
                "background": "背景" * 25000, "conditions": ["不得新增设备"],
                "items": [{"name": "工业防火墙", "specification": "双电源千兆接口",
                           "source_section": "网络安全", "quantity": 2, "unit": "台"}],
                "source_materials": [{"source_id": "upload", "extraction_hash": "saved-hash",
                                      "text": "富材料视频监控设计要求" + "文" * 10000}],
                "sources": [{"id": "upload", "sha256": "source-hash"}]}

    def test_query_keeps_upload_list_and_priority_fields_with_a_fixed_bound(self):
        query = blueprint._query(self.payload())
        for value in ("项目优先信息", "需求优先信息", "工业防火墙", "双电源千兆接口",
                      "网络安全", "富材料视频监控设计要求", "不得新增设备"):
            self.assertIn(value, query)
        self.assertLessEqual(len(query), 6000)

    def test_complete_inputs_change_hash_even_when_query_excerpts_do_not(self):
        original = self.payload()
        original["items"][0]["specification"] += "规" * 200
        for field in ("requirements", "background", "source_materials", "items", "sources"):
            changed = copy.deepcopy(original)
            if field == "source_materials":
                changed[field][0]["text"] += "尾部新增视频监控要求"
            elif field == "items":
                changed[field][0]["specification"] += "尾部规格"
            elif field == "sources":
                changed[field][0]["sha256"] = "replaced-source-hash"
            else:
                changed[field] += "尾部新增信息"
            with self.subTest(field=field):
                self.assertEqual(blueprint._query(original), blueprint._query(changed))
                self.assertNotEqual(blueprint._query_hash(original), blueprint._query_hash(changed))

    def test_query_strategy_changes_hash_and_generated_knowledge_does_not(self):
        payload = self.payload()
        original = blueprint._query_hash(payload)
        payload["knowledge_sources"] = [{"text": "公开参考不能参与输入缓存键"}]
        self.assertEqual(blueprint._query_hash(payload), original)
        with patch.object(blueprint, "_query", return_value="新策略问题"):
            self.assertNotEqual(blueprint._query_hash(payload), original)

    def test_uploaded_text_and_specs_classify_locally_without_private_search_terms(self):
        payload = {"project": "保密客户编号", "source_materials": [{"text": "保密场地视频监控规划"}],
                   "items": [{"name": "设备甲", "specification": "UPS双电源",
                              "source_section": "工业控制"}]}
        self.assertEqual(technical_domains(payload), ["视频监控", "供配电", "工业控制"])
        queries = public_queries(evidence_coverage(payload, []))
        self.assertEqual(queries, ["视频监控 供配电 工业控制 技术设计规范 验收要求"])

    @override_settings(PRODUCT_BLUEPRINT_KNOWLEDGE_MODE=blueprint.RAGFLOW_REQUIRED)
    def test_prepare_retrieves_again_after_material_tail_changes(self):
        revision = SimpleNamespace(pk=1, payload=self.payload())
        task = SimpleNamespace(pk=1, owner=Mock(), state=DocumentTask.State.RUNNING,
                               fence=2, checkpoint={}, save=Mock())
        with patch.object(DocumentTask, "objects") as objects, \
                patch("portal.product_service.current_revision", return_value=revision), \
                patch("portal.product_service.append_revision", return_value=SimpleNamespace(version=2)) as append, \
                patch.object(blueprint.transaction, "atomic", side_effect=lambda: nullcontext()), \
                patch.object(service, "authorize", return_value=SCOPE), \
                patch.object(service, "configuration", return_value=CONFIG), \
                patch.object(service, "retrieve", return_value=[{"id": "S1", "chunk_id": "c",
                    "dataset_id": "dataset-1", "document_id": "document-1",
                    "title": "参考资料", "content": "授权参考"}]) as retrieve, \
                patch.object(blueprint, "evidence_coverage", return_value={"sufficient": True}):
            objects.select_related.return_value.get.return_value = task
            objects.select_for_update.return_value.get.return_value = task
            blueprint.prepare_blueprint_knowledge(task.pk, task.fence)
            revision.payload = append.call_args.args[2]
            blueprint.prepare_blueprint_knowledge(task.pk, task.fence)
            self.assertEqual(retrieve.call_count, 1)
            question = retrieve.call_args.args[0]
            revision.payload["source_materials"][0]["text"] += "尾部修订"
            blueprint.prepare_blueprint_knowledge(task.pk, task.fence)
            self.assertEqual(retrieve.call_count, 2)
            self.assertEqual(retrieve.call_args.args[0], question)
            self.assertEqual(retrieve.call_args.kwargs, {"blueprint": True})

    def test_blueprint_retains_multiple_chunks_and_question_answering_keeps_defaults(self):
        scope = {"datasets": {"dataset-1": [f"document-{i}" for i in range(1, 9)]}}
        rows = [chunk(id=f"c{i}", content="x" * 5000) for i in range(5)]
        rows += [chunk(id=f"d{i}", document_id=f"document-{i}", content="x" * 5000)
                 for i in range(2, 9)]
        for mode, expected_count, expected_doc_chunks, expected_length in (
                (False, 6, 1, 1200), (True, 11, 4, 4000)):
            with self.subTest(blueprint=mode), patch.object(service, "_open", return_value=Response(wire(rows))):
                sources = service.retrieve("蓝图参考", [], scope, CONFIG, blueprint=mode)
            self.assertEqual(len(sources), expected_count)
            self.assertEqual(sum(s["document_id"] == "document-1" for s in sources), expected_doc_chunks)
            self.assertTrue(all(len(s["content"]) == expected_length for s in sources))
        with patch.object(service, "_open", return_value=Response(wire(rows))):
            self.assertGreater(len(service.retrieve("有哪些相关项目", [], scope, CONFIG, blueprint=True)), 4)
        scope = {"datasets": {f"dataset-{i}": [f"document-{i}"] for i in range(1, 5)}}
        responses = [Response(wire([chunk(id=f"c{j}", dataset_id=dataset, document_id=documents[0],
                                         content="x" * 5000) for j in range(12)]))
                     for dataset, documents in scope["datasets"].items()]
        with patch.object(service, "_open", side_effect=responses):
            sources = service.retrieve("蓝图参考", [], scope, CONFIG, blueprint=True)
        self.assertEqual(len(sources), 12)
        self.assertEqual([s["dataset_id"] for s in sources[:4]], list(scope["datasets"]))
        self.assertLessEqual(sum(len(s["content"]) for s in sources), 48000)

    def test_blueprint_and_default_retrieval_reject_unauthorized_and_invalid_chunks(self):
        invalid = ([chunk(document_id="private")], [chunk(dataset_id="private")],
                   [chunk(), chunk()], [chunk(content="x" * (service.CHUNK_CONTENT_LIMIT + 1))])
        for mode in (False, True):
            for rows in invalid:
                with self.subTest(blueprint=mode, rows=rows[0]["id"]), \
                        patch.object(service, "_open", return_value=Response(wire(rows))), \
                        self.assertRaises(ProductError) as caught:
                    service.retrieve("蓝图参考", [], SCOPE, CONFIG, blueprint=mode)
                self.assertEqual((caught.exception.code, caught.exception.status), ("invalid_response", 502))
