"""Exercise the localhost demo and capture a screenshot and video for a PR."""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    output = Path("review-evidence")
    output.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1280, "height": 960},
            record_video_dir=output,
            record_video_size={"width": 1280, "height": 960},
        )
        page = context.new_page()
        video = page.video
        try:
            page.goto("http://127.0.0.1:8000")
            page.get_by_label("Title").fill("Review the release")
            page.get_by_label("Details").fill("Check the rollout plan and test coverage.")
            page.get_by_role("button", name="Add to queue").click()
            page.get_by_role("button", name="Generate proposal").click()
            expect(page.get_by_role("button", name="Approve", exact=True)).to_be_visible()
            page.keyboard.press("j")
            expect(page.locator("article.task")).to_be_focused()
            page.screenshot(path=output / "pending-review.png", full_page=True)
            page.locator(".note").fill("Rollout checks are covered.")
            page.get_by_role("button", name="Approve", exact=True).click()
            expect(page.locator("article .approved")).to_have_text("approved")
        finally:
            context.close()
            video.path().replace(output / "review-demo.webm")
            browser.close()


if __name__ == "__main__":
    main()
