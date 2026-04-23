from __future__ import annotations

from copy import deepcopy
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Response

from extractors.base import Extractor
from scanner_tools.cmp import CMPInteractor
from scanner_tools.finalize import collect_storage, store_final_response
from scanner_tools.network import NetworkCollector
from scanner_tools.results import ScanResult
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
        self.cmp_interactor = CMPInteractor(self.options)
        self.log_scan_timings = bool(self.options.get("log_scan_timings", False))

    def launch_browser(self, playwright: Any) -> Browser:
        return playwright.chromium.launch(
            headless=self.options.get("headless", False),
            channel="chrome",
            args=[
                "--disable-features=BlockThirdPartyCookies",
                "--disable-dev-shm-usage",
            ],
        )

    def scan_one_url_with_browser(self, url: str, browser: Browser) -> dict[str, Any]:
        result = ScanResult(site_url=url)
        context: BrowserContext | None = None
        page: Page | None = None
        data: ScanData | None = None

        try:
            context = self._create_context(browser)
            page = context.new_page()
            data = ScanData(page=page, context=context)
            script_extractors = create_extractors(
                self.extractor_classes, {}, self.options, data
            )

            self._prepare_page(context, page, data, script_extractors)
            final_response = self._navigate(page, url, result)
            before_accept_result, before_accept_data = self._capture_phase_result(
                context=context,
                page=page,
                data=data,
                final_response=final_response,
                fallback_url=url,
                base_result=result,
                wait_for_network_idle=True,
            )

            self._print_time("cmp_try_accept start", url)
            cmp_result = self.cmp_interactor.try_accept(page)
            result.cmp = cmp_result.to_dict()
            self._print_time("cmp_try_accept end", url)

            self._print_time("extract_before start", url)
            self._run_extractors_for_phase(before_accept_result, before_accept_data)
            result.before_accept = deepcopy(before_accept_result)
            self._print_time("extract_before end", url)

            if cmp_result.accept_clicked:
                if cmp_result.wait_after_click_ms > 0:
                    page.wait_for_timeout(cmp_result.wait_after_click_ms)

                after_final_response = (
                    final_response
                    if final_response is not None and final_response.url == page.url
                    else None
                )
                after_accept_result, after_accept_data = self._capture_phase_result(
                    context=context,
                    page=page,
                    data=data,
                    final_response=after_final_response,
                    fallback_url=url,
                    base_result=result,
                    wait_for_network_idle=True,
                )
                self._print_time("extract_after start", url)
                self._run_extractors_for_phase(after_accept_result, after_accept_data)
                result.after_accept = deepcopy(after_accept_result)
                self._print_time("extract_after end", url)
            else:
                result.after_accept = {}
            result.scan_end = utc_now_iso()
        except Exception as exc:
            result.error = str(exc)
            if result.scan_end is None:
                result.scan_end = utc_now_iso()
        finally:
            if page is not None and data is not None:
                self.network_collector.detach_page_logging(page, data)
            if context is not None:
                context.close()

        return result.to_dict()

    def failed_result(self, url: str, error: str) -> dict[str, Any]:
        return ScanResult.failed(url, error)

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

    def _navigate(self, page: Page, url: str, result: ScanResult) -> Response | None:
        try:
            self._print_time("navigation start", url)
            response = page.goto(
                url,
                wait_until=self.options.get("wait_until", "domcontentloaded"),
                timeout=self.options.get("timeout", 30000),
            )
            self._print_time("navigation end", url)
            result.reachable = True
            return response
        except Exception as exc:
            result.error = str(exc)
            return None

    def _capture_phase_result(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        final_response: Response | None,
        fallback_url: str,
        base_result: ScanResult,
        wait_for_network_idle: bool,
    ) -> tuple[dict[str, Any], ScanData]:
        phase_result: dict[str, Any] = {
            "site_url": base_result.site_url,
            "scan_start": base_result.scan_start,
            "reachable": base_result.reachable,
        }

        if wait_for_network_idle:
            max_wait_exceeded = self.network_collector.wait_for_network_idle(data)
        else:
            max_wait_exceeded = False
        phase_result["network_idle_max_wait_exceeded"] = max_wait_exceeded
        collect_storage(context, data)
        phase_data = self._snapshot_scan_data(data)
        store_final_response(phase_result, phase_data, final_response, page, fallback_url)
        return phase_result, phase_data

    def _run_extractors_for_phase(
        self,
        phase_result: dict[str, Any],
        phase_data: ScanData,
    ) -> None:
        extractors = create_extractors(self.extractor_classes, phase_result, self.options, phase_data)
        run_extractors(extractors)

    def _print_time(self, step: str, url: str) -> None:
        if not self.log_scan_timings:
            return
        print(f"method {step} ({url}): {utc_now_iso()}")

    @staticmethod
    def _snapshot_scan_data(data: ScanData) -> ScanData:
        return ScanData(
            page=data.page,
            context=data.context,
            request_log=deepcopy(data.request_log),
            response_log=deepcopy(data.response_log),
            failed_request_log=deepcopy(data.failed_request_log),
            cookies=deepcopy(data.cookies),
            final_response=deepcopy(data.final_response),
            local_storage=deepcopy(data.local_storage),
            local_storage_by_origin=deepcopy(data.local_storage_by_origin),
            event_tasks=set(),
            on_request_handler=None,
            on_response_handler=None,
            on_request_finished_handler=None,
            on_request_failed_handler=None,
            active_request_ids=set(data.active_request_ids),
        )

