"""Opt-in browser smoke test. Requires Playwright and its Chromium headless shell."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect


class Lab(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "session=BROWSER-TEST-SECRET; Path=/")
        self.end_headers()
        self.wfile.write(b"<html><title>Moth browser lab</title><h1>Lab</h1></html>")

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Lab)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8765")
        expect(page.locator("h1:visible")).to_have_text("Understand your website’s security.")
        page.locator("#language").select_option("ro")
        expect(page.locator("h1:visible")).to_have_text("Înțelege securitatea site-ului tău.")
        page.reload()
        expect(page.locator("#language")).to_have_value("ro")
        page.locator("#language").select_option("ru")
        expect(page.locator("h1:visible")).to_have_text("Разберитесь в безопасности сайта.")
        page.locator('[data-page="tools"]').click()
        expect(page.locator(".tool-card")).to_have_count(10)
        expect(page.locator('[data-install="httpx"]')).to_be_disabled()
        page.screenshot(path="/tmp/moth-tools-ru.png", full_page=True)
        page.locator("#language").select_option("en")
        page.locator('[data-page="scan"]').click()
        page.locator("#target").fill(f"http://127.0.0.1:{server.server_port}")
        page.locator("#authorized").check()
        page.locator("#lab").check()
        page.locator(".module-picker summary").click()
        page.locator('#scan-tools input[value="httpx"]').check()
        page.locator("#start-button").click()
        expect(page.locator("#progress-title")).to_have_text("Assessment finished", timeout=60000)
        assert page.locator(".finding").count() >= 5
        assert "BROWSER-TEST-SECRET" not in page.locator("#findings").inner_text()
        page.locator(".finding details summary").first.click()
        expect(page.locator(".finding pre").first).to_be_visible()
        with page.expect_download() as download:
            page.locator("#export-html").click()
        report = download.value
        assert report.suggested_filename.endswith(".html")
        report.save_as("/tmp/moth-browser-report.html")
        page.screenshot(path="/tmp/moth-results.png", full_page=True)
        page.locator('[data-page="history"]').click()
        expect(page.locator(".history-item").first).to_be_visible()
        page.locator(".history-item").first.click()
        expect(page.locator("#result-area")).to_be_visible()
        page.set_viewport_size({"width":390,"height":844})
        page.locator("#language").select_option("ro")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path="/tmp/moth-mobile-ro.png",full_page=True)
        assert not errors, errors
        browser.close()
        print("PASS: language selection/persistence, ten tools, real scan, technical details, HTML export, history and mobile layout; no JavaScript errors")
finally:
    server.shutdown()
    server.server_close()
