"""Exact attachment text/source preservation at the model prompt boundary."""
from copy import deepcopy
import json

from django.test import SimpleTestCase
from portal.baichuan_assistant_worker import _model_context
from portal.product_intake import source_text


class PromptCompactionTests(SimpleTestCase):
    def context(self):
        blocks=[{"id":"b1","text":"硬性：制造商CCRC二级。","location":{"page":1}},
                {"id":"b2","text":"ITSS二级仅优先。","location":{"page":2}}]
        refs=["attachment:synthetic:"+b["id"] for b in blocks]
        return {"revision":1,"query_date":"2026-10-18","text":"按附件执行","text_source_ref":"message:synthetic",
            "documents":[{"name":"synthetic.pdf","id":"synthetic","text":source_text({"blocks":blocks}),
                "source_refs":refs,"blocks":[{"source_ref":ref,"text":b["text"],"location":b["location"]} for b,ref in zip(blocks,refs)]}]}

    def test_all_exact_blocks_and_locations_preserved_with_smaller_payload(self):
        original=self.context(); before=deepcopy(original)
        encoded=_model_context(original);result=json.loads(encoded)
        self.assertEqual(original,before)
        self.assertEqual(result["documents"][0]["blocks"],original["documents"][0]["blocks"])
        self.assertNotIn("text",result["documents"][0]);self.assertNotIn("source_refs",result["documents"][0])
        self.assertLess(len(encoded),len(json.dumps(original,ensure_ascii=False)))
        for key in ("text","text_source_ref","query_date","revision"):self.assertEqual(result[key],original[key])

    def test_old_locator_only_cache_keeps_aggregate_text(self):
        context=self.context()
        for block in context["documents"][0]["blocks"]:block["text"]=""
        self.assertEqual(json.loads(_model_context(context)),context)

    def test_single_block_prompt_preserves_existing_aggregate_contract(self):
        context=self.context();document=context["documents"][0]
        document["blocks"]=document["blocks"][:1];document["source_refs"]=document["source_refs"][:1]
        document["text"]=source_text({"blocks":[{"id":"b1","text":document["blocks"][0]["text"],"location":{"page":1}}]})
        self.assertEqual(json.loads(_model_context(context)),context)

    def test_nonidentical_aggregate_is_never_discarded(self):
        context=self.context();context["documents"][0]["text"]+="\n另有未定位条款，必须保留。"
        self.assertEqual(json.loads(_model_context(context)),context)

    def test_extra_source_ref_is_never_discarded(self):
        context=self.context();context["documents"][0]["source_refs"].append("attachment:synthetic:b3")
        result=json.loads(_model_context(context))
        self.assertEqual(result["documents"][0]["source_refs"],context["documents"][0]["source_refs"])

    def test_pending_context_and_previous_conditions_are_unchanged(self):
        context=self.context();context["previous_conditions"]={"must":{"not":{"field":"qualification"}},"unresolved":["待澄清"]}
        context["pending_user_requests"]=["保留前轮要求"]
        result=json.loads(_model_context(context))
        for key in ("previous_conditions","pending_user_requests"):self.assertEqual(result[key],context[key])
