from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Response

from extractors.base import Extractor
from scanner_tools.finalize import collect_storage, store_final_response
from scanner_tools.network import NetworkCollector
from scanner_tools.extractors import (
    EXTRACTOR_CLASSES,
    SCANNER_INIT_SCRIPT,
    create_extractors,
    register_extractor_javascript,
    run_extractors,
)
from utils import ScanData, utc_now_iso


class WebsiteScanner:
    def __init__(self, options: dict[str, Any] | None = None):
        self.options = options or {}
        self.extractor_classes = EXTRACTOR_CLASSES
        self.network_collector = NetworkCollector(self.options)

    def launch_browser(self, playwright: Any) -> Browser:
        return playwright.chromium.launch(
            headless=self.options.get("headless", True),
            channel="chrome",
            args=[
                "--disable-features=BlockThirdPartyCookies",
                "--disable-dev-shm-usage",
            ],
        )

    def scan_one_url_with_browser(self, url: str, browser: Browser) -> dict[str, Any]:
        result = self._initial_result(url)
        context: BrowserContext | None = None
        page: Page | None = None
        data: ScanData | None = None

        try:
            context = self._create_context(browser)
            page = context.new_page()
            data = ScanData(page=page, context=context)
            extractor_instances = create_extractors(
                self.extractor_classes, result, self.options, data
            )

            self._prepare_page(context, page, data, extractor_instances)
            final_response = self._navigate(page, url, result)
            self._finalize_scan(
                context=context,
                page=page,
                data=data,
                result=result,
                extractors=extractor_instances,
                final_response=final_response,
                fallback_url=url,
            )
        except Exception as exc:
            result["error"] = str(exc)
            if "scan_end" not in result:
                result["scan_end"] = utc_now_iso()
        finally:
            if page is not None and data is not None:
                self.network_collector.detach_page_logging(page, data)
            if context is not None:
                context.close()

        return result

    def failed_result(self, url: str, error: str) -> dict[str, Any]:
        result = self._initial_result(url)
        result["error"] = error
        result["scan_end"] = utc_now_iso()
        return result

    def _initial_result(self, url: str) -> dict[str, Any]:
        return {
            "site_url": url,
            "scan_start": utc_now_iso(),
            "reachable": False,
        }

    def _create_context(self, browser: Browser) -> BrowserContext:
        return browser.new_context(
            ignore_https_errors=self.options.get("ignore_https_errors", True),
            java_script_enabled=self.options.get("java_script_enabled", True),
            viewport=self.options.get("viewport", {"width": 1920, "height": 1080}),
            user_agent=self.options.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            ),
        )

    def _prepare_page(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        extractors: list[Extractor],
    ) -> None:
        self.network_collector.register_page_logging(page, data)
        register_extractor_javascript(context, extractors, SCANNER_INIT_SCRIPT)

    def _navigate(self, page: Page, url: str, result: dict[str, Any]) -> Response | None:
        try:
            response = page.goto(
                url,
                wait_until=self.options.get("wait_until", "domcontentloaded"),
                timeout=self.options.get("timeout", 30000),
            )
            result["reachable"] = True
            return response
        except Exception as exc:
            result["error"] = str(exc)
            return None

    def _finalize_scan(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        result: dict[str, Any],
        extractors: list[Extractor],
        final_response: Response | None,
        fallback_url: str,
    ) -> None:
        self.network_collector.wait_for_network_idle(data)
        self.network_collector.detach_page_logging(page, data)
        collect_storage(context, data)
        store_final_response(result, data, final_response, page, fallback_url)
        run_extractors(extractors)
        result["scan_end"] = utc_now_iso()

