"""Generation-only delivery; never represents a content review or approval."""

from django.conf import settings

POLICY = "generation-only-v1"
ACTIONS = {"generate_outputs", "three_drafts", "presentation"}


def generation_only(task):
    return (task.pending_action in ACTIONS
            and not getattr(settings, "PRODUCT_CONTENT_VERIFICATION_ENABLED", False))


def unchecked_review(input_revision, blueprint, chapters):
    return {"generation_policy": POLICY, "passed": False, "issues": [],
            "program_checks_complete": False, "content_checks": "not_run",
            "model_review": {"status": "not_run", "scope": "not_run"},
            "input_sha256": input_revision.sha256, "blueprint_sha256": blueprint.sha256,
            "chapter_hashes": {chapter.payload["chapter_id"]: chapter.sha256 for chapter in chapters}}


def document_generation_only(document):
    return any(item.get("id") == "RGENERATIONPOLICY" and item.get("text") == POLICY
               for item in document.get("requirements", []))
