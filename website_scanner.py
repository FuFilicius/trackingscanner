from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Browser, BrowserContext, Page, Response

from extractors.base import Extractor
from scanner_tools.cmp import CMPInteractor
from scanner_tools.finalize import collect_storage, store_final_response
from scanner_tools.network import NetworkCollector
from scanner_tools.results import ScanPhaseResult, ScanResult, ScanResultPayload
from scanner_tools.extractors import (
    EXTRACTOR_CLASSES,
    SCANNER_INIT_SCRIPT,
    create_extractors,
    register_extractor_javascript,
    run_extractors,
)
from utils import ScanData, utc_now_iso


class WebsiteScanner:
    def __init__(self, options: dict[str, object] | None = None):
        self.options = options or {}
        self.extractor_classes = EXTRACTOR_CLASSES
        self.network_collector = NetworkCollector(self.options)
        self.cmp_interactor = CMPInteractor(self.options)
        self.log_scan_timings = bool(self.options.get("log_scan_timings", False))
        self.screenshots_enabled = bool(self.options.get("screenshots_enabled", False))
        self.screenshot_dir = self._resolve_screenshot_dir(
            self.options.get("screenshot_dir")
        )
        self._logged_screenshot_warning = False

    def launch_browser(self, playwright: Any) -> Browser:
        return playwright.chromium.launch(
            headless=self.options.get("headless", False),
            channel="chrome",
            args=[
                "--disable-features=BlockThirdPartyCookies",
                "--disable-dev-shm-usage",
            ],
        )

    def scan_one_url_with_browser(
        self,
        url: str,
        browser: Browser,
        scan_label: str | None = None,
    ) -> ScanResultPayload:
        result = ScanResult(site_url=url)
        context: BrowserContext | None = None
        page: Page | None = None
        data: ScanData | None = None
        current_scan_label = scan_label or f"url={url}"

        try:
            context = self._create_context(browser)
            page = context.new_page()
            data = ScanData(page=page, context=context)
            script_extractors = create_extractors(
                self.extractor_classes, {}, self.options, data
            )

            self._prepare_page(context, page, data, script_extractors, current_scan_label)
            final_response = self._navigate(page, url, result)
            store_final_response(result, data, final_response, page, url)
            before_accept_result, before_accept_data = self._capture_phase_result(
                context=context,
                data=data,
                base_result=result,
                wait_for_network_idle=True,
                phase="before",
            )

            self._print_time("cmp_try_accept start", url)
            cmp_result = self.cmp_interactor.try_accept(page)
            result.cmp = cmp_result.to_dict()
            self._print_time("cmp_try_accept end", url)

            after_accept_result = None
            after_accept_data = None

            if cmp_result.accept_clicked:
                if cmp_result.wait_after_click_ms > 0:
                    page.wait_for_timeout(cmp_result.wait_after_click_ms)

                after_accept_result, after_accept_data = self._capture_phase_result(
                    context=context,
                    data=data,
                    base_result=result,
                    wait_for_network_idle=True,
                    phase="after",
                )

            self._print_time("extract_before start", url)
            self._run_extractors_for_phase(before_accept_result, before_accept_data)
            result.before_accept = deepcopy(before_accept_result)
            self._print_time("extract_before end", url)

            if cmp_result.accept_clicked and after_accept_result is not None:
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
                data.teardown_started = True
                self.network_collector.detach_page_logging(page, data)
            if context is not None:
                try:
                    context.close()
                except PlaywrightError as exc:
                    if result.error is None:
                        result.error = str(exc)
                    if result.scan_end is None:
                        result.scan_end = utc_now_iso()

        return result.to_dict()

    def failed_result(self, url: str, error: str) -> ScanResultPayload:
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
        scan_label: str,
    ) -> None:
        self.network_collector.register_page_logging(page, data, scan_label)
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
        data: ScanData,
        base_result: ScanResult,
        wait_for_network_idle: bool,
        phase: str | None = None,
    ) -> tuple[ScanPhaseResult, ScanData]:
        phase_result: ScanPhaseResult = {
            "site_url": base_result.site_url,
            "final_url": base_result.final_url,
            "scan_start": base_result.scan_start,
        }

        if wait_for_network_idle:
            max_wait_exceeded = self.network_collector.wait_for_network_idle(data)
        else:
            max_wait_exceeded = False
        phase_result["network_idle_max_wait_exceeded"] = max_wait_exceeded
        if phase:
            self._capture_phase_screenshot(data.page, base_result.site_url, phase)
        collect_storage(context, data)
        phase_data = self._snapshot_scan_data(data)
        return phase_result, phase_data

    def _run_extractors_for_phase(
        self,
        phase_result: ScanPhaseResult,
        phase_data: ScanData,
    ) -> None:
        extractors = create_extractors(self.extractor_classes, phase_result, self.options, phase_data)
        run_extractors(extractors)

    def _print_time(self, step: str, url: str) -> None:
        if not self.log_scan_timings:
            return
        print(f"method {step} ({url}): {utc_now_iso()}")

    @staticmethod
    def _resolve_screenshot_dir(raw_dir: object) -> Path | None:
        if not isinstance(raw_dir, str):
            return None
        cleaned = raw_dir.strip()
        if not cleaned:
            return None
        return Path(cleaned)

    def _capture_phase_screenshot(self, page: Page, url: str, phase: str) -> None:
        if not self.screenshots_enabled:
            return
        if self.screenshot_dir is None:
            if not self._logged_screenshot_warning:
                print(
                    f"[{utc_now_iso()}] screenshots enabled but screenshot_dir is missing",
                    file=sys.stderr,
                )
                self._logged_screenshot_warning = True
            return
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            filename = self._build_screenshot_name(url, phase)
            target_path = self.screenshot_dir / filename
            page.screenshot(path=str(target_path))
        except (OSError, PlaywrightError) as exc:
            print(
                f"[{utc_now_iso()}] screenshot failed ({phase}) for {url}: {exc}",
                file=sys.stderr,
            )

    @staticmethod
    def _build_screenshot_name(url: str, phase: str) -> str:
        parsed = urlparse(url)
        base = f"{parsed.netloc}{parsed.path}"
        base = base or parsed.netloc or "site"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-")
        if not slug:
            slug = "site"
        slug = slug[:80]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return f"{timestamp}_{phase}_{slug}.png"

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
            teardown_started=data.teardown_started,
        )
