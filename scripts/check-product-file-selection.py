"""Check native file selection survives focus refresh; never submit a project.

Run with the existing frontend and Playwright runtime:
  python scripts/check-product-file-selection.py --token-file <private-login.json>
"""
import argparse
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    token = json.loads(args.token_file.read_text(encoding="utf-8"))["access_token"]
    with httpx.Client(trust_env=False, timeout=30) as client:
        overview = client.get("http://127.0.0.1:8080/api/enterprise/business/product/workspace/",
                              headers={"Authorization": "Bearer " + token})
        overview.raise_for_status()
    fixtures = root / "services/business/backend/portal/tests/fixtures/three_piece_knowledge_platform"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=str(
            root / ".runtime/browser/chrome-win64/chrome.exe"))
        try:
            page = browser.new_page()
            page.add_init_script('localStorage.setItem("openclaw_access_token", ' + json.dumps(token) + ');')
            reads = []

            def refresh(route):
                reads.append(route.request.url)
                route.fulfill(status=200, content_type="application/json", body=overview.text)

            page.route("**/api/enterprise/business/product/workspace/**", refresh)
            page.goto("http://127.0.0.1:3080/departments/product/documents")
            page.wait_for_load_state("networkidle")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            for selector, name in [("input[aria-label='选择项目资料文件']", "background.txt"),
                                   ("#equipment-source", "equipment.csv")]:
                control = page.locator(selector)
                with page.expect_file_chooser() as chooser:
                    if name == "background.txt":
                        page.get_by_role("button", name="选择项目资料", exact=True).click()
                    else:
                        control.click()
                original = control.element_handle()
                count = len(reads)
                page.evaluate('window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange"));')
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                assert len(reads) == count, "Focus refreshed while file picker was open"
                assert original.evaluate("el => el.isConnected"), "File input was detached before selection"
                with page.expect_response("**/api/enterprise/business/product/workspace/**"):
                    chooser.value.set_files(str(fixtures / name))
                page.wait_for_load_state("networkidle")
                page.get_by_text(name, exact=name == "background.txt").wait_for()
                assert len(reads) > count, "Permissions were not refreshed after selection"

            with page.expect_file_chooser():
                page.get_by_role("button", name="选择项目资料", exact=True).click()
            count = len(reads)
            with page.expect_response("**/api/enterprise/business/product/workspace/**"):
                page.locator("input[aria-label='选择项目资料文件']").evaluate(
                    'el => el.dispatchEvent(new Event("cancel", {bubbles: true}))')
            page.wait_for_load_state("networkidle")
            assert len(reads) > count, "Cancel did not restore permissions refresh"
            count = len(reads)
            with page.expect_response("**/api/enterprise/business/product/workspace/**"):
                page.evaluate('window.dispatchEvent(new Event("focus"))')
            page.wait_for_load_state("networkidle")
            assert len(reads) > count, "Ordinary focus refresh remained paused"
            page.get_by_text("background.txt", exact=True).wait_for()
            page.get_by_text("equipment.csv", exact=False).wait_for()
            assert not errors, errors
            print(json.dumps({"passed": True, "selection_survives_focus": True,
                              "both_upload_inputs": True, "cancel_restores_refresh": True,
                              "ordinary_focus_refresh": True, "project_submitted": False}))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
