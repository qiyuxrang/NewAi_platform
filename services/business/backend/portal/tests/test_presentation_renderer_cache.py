"""Renderer upgrades invalidate only PPT reuse, retaining historical artifacts."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from portal.product_service import digest
from portal.product_three_drafts import generate_presentation_artifact


class PresentationRendererCacheTests(SimpleTestCase):
    def test_renderer_upgrade_misses_old_cache_while_same_renderer_reuses(self):
        saved = SimpleNamespace(pk="old-artifact", path="fixture.pptx", sha256="a" * 64, render_evidence={})
        task = SimpleNamespace(pk="synthetic", title="Synthetic report", checkpoint={},
            artifacts=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(
                order_by=lambda *args: SimpleNamespace(first=lambda: saved))))
        pair = {"sha256": "pair"}
        planning = {"presentation_style": "auto", "audience": "", "purpose": "", "requirements": ""}
        old_hash = digest({"kind": "presentation", "pair": "pair", "title": task.title, "renderer": "old", "planning": planning})
        revision = SimpleNamespace(payload={})
        class RenderReached(Exception):
            pass
        with patch("portal.product_worker._renew"), patch("portal.product_worker._analysis_progress"), \
                patch("portal.product_three_drafts.pair_snapshot", return_value=pair), \
                patch("portal.product_three_drafts.verified_artifact") as verify, \
                patch("portal.product_three_drafts.DocumentArtifact.objects.filter") as lookup, \
                patch("portal.product_three_drafts._rendered_result_current", return_value=True), \
                patch("portal.product_three_drafts.record_artifact_delivery"), \
                patch("portal.product_three_drafts._presentation_progress"), \
                patch("portal.product_three_drafts.run_step", side_effect=lambda *args, **kwargs: args[4]()), \
                patch("portal.product_presentation.presentation_renderer_hash", return_value="old") as renderer, \
                patch("portal.product_presentation.render_presentation_draft", side_effect=RenderReached) as render:
            lookup.side_effect = lambda **query: SimpleNamespace(first=lambda: saved if query["generation_hash"] == old_hash else None)
            self.assertIs(generate_presentation_artifact(task, 1, "attempt", revision, revision), saved)
            verify.assert_called_once_with(saved)
            render.assert_not_called()
            renderer.return_value = "new"
            with self.assertRaises(RenderReached):
                generate_presentation_artifact(task, 1, "attempt", revision, revision)
            self.assertEqual(render.call_args.args, (task, pair))
            self.assertEqual({key: render.call_args.kwargs[key] for key in planning}, planning)
            self.assertTrue(callable(render.call_args.kwargs["progress"]))
