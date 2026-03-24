from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import BrowserContext, Page, Request, Response, async_playwright

from extractors.base import Extractor
from extractors import CookiesExtractor, RequestsExtractor, ThirdPartyExtractor, LocalStorageExtractor, \
    FacebookPixelExtractor, TwitterPixelExtractor, TiktokPixelExtractor, FailedRequestsExtractor, SessionRecordersExtractor, \
    FingerprintingExtractor, TrackerExtractor
from utils import (
    CookieEntry,
    FailedRequestLogEntry,
    RequestLogEntry,
    ResponseLogEntry,
    ScanData,
    maybe_await,
    parsed_url_data,
    utc_now_iso,
)

# Import the extractor classes you want to use here and add them to EXTRACTOR_CLASSES.
EXTRACTOR_CLASSES: list[type[Extractor]] = [
    ThirdPartyExtractor,
    TrackerExtractor,
    CookiesExtractor,
    LocalStorageExtractor,
    RequestsExtractor,
    FailedRequestsExtractor,
    FacebookPixelExtractor,
    TwitterPixelExtractor,
    TiktokPixelExtractor,
    SessionRecordersExtractor,
    FingerprintingExtractor,
]


SCANNER_INIT_SCRIPT = """
(() => {
    const rootKey = "__scanner__";

    function readRoot() {
        try {
            const raw = window.localStorage.getItem(rootKey);
            return raw ? JSON.parse(raw) : {};
        } catch (error) {
            return {};
        }
    }

    function writeRoot(payload) {
        try {
            window.localStorage.setItem(rootKey, JSON.stringify(payload));
            return true;
        } catch (error) {
            return false;
        }
    }

    window.__websiteScanner = {
        set(key, value) {
            const payload = readRoot();
            payload[key] = value;
            return writeRoot(payload);
        },
        append(key, value) {
            const payload = readRoot();
            const current = Array.isArray(payload[key]) ? payload[key] : [];
            current.push(value);
            payload[key] = current;
            return writeRoot(payload);
        },
        get(key) {
            return readRoot()[key];
        }
    };
})();
"""


class WebsiteScanner:
    def __init__(self, options: dict[str, Any] | None = None):
        self.options = options or {}
        self.extractor_classes = EXTRACTOR_CLASSES

    def scan(self, url: str) -> dict[str, Any]:
        return asyncio.run(self.scan_async(url))

    async def scan_async(self, url: str) -> dict[str, Any]:
        result = self._initial_result(url)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.options.get("headless", True),
                channel="chrome",
                args=["--disable-features=BlockThirdPartyCookies"]
            )
            try:
                context = await self._create_context(browser)
                page = await context.new_page()
                data = ScanData(page=page, context=context)
                extractor_instances = self._create_extractors(result, data)

                await self._prepare_page(context, page, data, extractor_instances)
                final_response = await self._navigate(page, url, result)
                await self._finalize_scan(
                    context=context,
                    page=page,
                    data=data,
                    result=result,
                    extractors=extractor_instances,
                    final_response=final_response,
                    fallback_url=url,
                )
            finally:
                await browser.close()

        return result

    def _initial_result(self, url: str) -> dict[str, Any]:
        return {
            "site_url": url,
            "scan_start": utc_now_iso(),
            "reachable": False,
        }

    async def _create_context(self, browser: Any) -> BrowserContext:
        return await browser.new_context(
            ignore_https_errors=self.options.get("ignore_https_errors", True),
            java_script_enabled=self.options.get("java_script_enabled", True),
            viewport=self.options.get("viewport", {"width": 1920, "height": 1080}),
            user_agent=self.options.get("user_agent"),
        )

    def _create_extractors(
        self, result: dict[str, Any], data: ScanData
    ) -> list[Extractor]:
        return [
            extractor_class(result=result, options=self.options, data=data)
            for extractor_class in self.extractor_classes
        ]

    async def _prepare_page(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        extractors: list[Extractor],
    ) -> None:
        self._register_page_logging(page, data)
        await self._register_extractor_javascript(context, extractors)

    async def _navigate(
        self, page: Page, url: str, result: dict[str, Any]
    ) -> Response | None:
        try:
            response = await page.goto(
                url,
                wait_until=self.options.get("wait_until", "domcontentloaded"),
                timeout=self.options.get("timeout", 30000),
            )
            result["reachable"] = True
            return response
        except Exception as exc:
            result["error"] = str(exc)
            return None

    async def _finalize_scan(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        result: dict[str, Any],
        extractors: list[Extractor],
        final_response: Response | None,
        fallback_url: str,
    ) -> None:
        await asyncio.sleep(5)
        await self._wait_for_network_idle(data)
        self._detach_page_logging(page, data)
        await self._wait_for_event_tasks(data)
        await self._collect_storage(context, data)
        await self._store_final_response(result, data, final_response, page, fallback_url)

        await self._run_extractors(extractors)
        result["scan_end"] = utc_now_iso()

    async def _store_final_response(
        self,
        result: dict[str, Any],
        data: ScanData,
        final_response: Response | None,
        page: Page,
        fallback_url: str,
    ) -> None:
        if final_response is not None:
            data.final_response = await self._serialize_response(final_response)
            result["final_response"] = data.final_response.to_dict()
            result["final_url"] = final_response.url
            return

        result["final_response"] = None
        result["final_url"] = page.url or fallback_url

    def _register_page_logging(self, page: Page, data: ScanData) -> None:
        def on_request(request: Request) -> None:
            data.active_request_ids.add(self._request_id(request))
            self._create_event_task(data, self._log_request(request, data))

        def on_response(response: Response) -> None:
            self._create_event_task(data, self._log_response(response, data))

        def on_request_finished(request: Request) -> None:
            data.active_request_ids.discard(self._request_id(request))

        def on_request_failed(request: Request) -> None:
            data.active_request_ids.discard(self._request_id(request))
            self._log_failed_request(request, data)

        data.on_request_handler = on_request
        data.on_response_handler = on_response
        data.on_request_finished_handler = on_request_finished
        data.on_request_failed_handler = on_request_failed

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfinished", on_request_finished)
        page.on("requestfailed", on_request_failed)

    def _detach_page_logging(self, page: Page, data: ScanData) -> None:
        try:
            if data.on_request_handler is not None:
                page.remove_listener("request", data.on_request_handler)
            if data.on_response_handler is not None:
                page.remove_listener("response", data.on_response_handler)
            if data.on_request_finished_handler is not None:
                page.remove_listener("requestfinished", data.on_request_finished_handler)
            if data.on_request_failed_handler is not None:
                page.remove_listener("requestfailed", data.on_request_failed_handler)
        except Exception:
            pass
        finally:
            data.on_request_handler = None
            data.on_response_handler = None
            data.on_request_finished_handler = None
            data.on_request_failed_handler = None

    async def _register_extractor_javascript(
        self, context: BrowserContext, extractors: list[Extractor]
    ) -> None:
        await context.add_init_script(script=SCANNER_INIT_SCRIPT)

        for extractor in extractors:
            scripts = await maybe_await(extractor.register_javascript())
            if not scripts:
                continue

            if isinstance(scripts, str):
                await context.add_init_script(script=scripts)
                continue

            for script in scripts:
                if script:
                    await context.add_init_script(script=script)

    async def _run_extractors(self, extractors: list[Extractor]) -> None:
        for extractor in extractors:
            await maybe_await(extractor.extract_information())

    async def _wait_for_network_idle(self, data: ScanData) -> None:
        idle_for_ms = int(self.options.get("network_idle_ms", 2000))
        max_wait_ms = int(self.options.get("network_idle_max_wait_ms", 10000))
        poll_interval_ms = int(self.options.get("network_idle_poll_interval_ms", 100))

        if idle_for_ms <= 0:
            return

        deadline_ms = int(time.monotonic() * 1000) + max_wait_ms
        idle_since_ms: int | None = None

        while int(time.monotonic() * 1000) < deadline_ms:
            await self._wait_for_event_tasks(data)
            now_ms = int(time.monotonic() * 1000)

            if not data.active_request_ids:
                if idle_since_ms is None:
                    idle_since_ms = now_ms
                elif now_ms - idle_since_ms >= idle_for_ms:
                    return
            else:
                idle_since_ms = None

            await asyncio.sleep(poll_interval_ms / 1000)

    async def _log_request(self, request: Request, data: ScanData) -> None:
        request_id = self._request_id(request)
        headers = await request.all_headers()
        body, body_json = self._extract_post_body(request)

        request_entry = RequestLogEntry(
            timestamp=utc_now_iso(),
            request_id=request_id,
            url=request.url,
            method=request.method,
            headers=headers,
            resource_type=request.resource_type,
            frame_url=request.frame.url if request.frame else None,
            is_navigation_request=request.is_navigation_request(),
            parsed_url=parsed_url_data(request.url),
            body=body,
            body_json=body_json,
        )
        data.request_log[request_id] = request_entry

    @staticmethod
    def _extract_post_body(
        request: Request,
    ) -> tuple[str | None, Any | None]:
        if request.method.upper() != "POST":
            return None, None

        try:
            body = request.post_data
        except Exception:
            return None, None

        if not body:
            return None, None

        try:
            body_json = request.post_data_json
        except Exception:
            body_json = None

        return body, body_json

    async def _log_response(self, response: Response, data: ScanData) -> None:
        request_id = self._request_id(response.request)
        headers = await response.all_headers()
        try:
            security_details = await response.security_details()
        except Exception:
            security_details = None

        response_entry = ResponseLogEntry(
            timestamp=utc_now_iso(),
            request_id=request_id,
            url=response.url,
            status=response.status,
            status_text=response.status_text,
            headers=headers,
            headers_lower={key.lower(): value for key, value in headers.items()},
            resource_type=response.request.resource_type,
            request_method=response.request.method,
            frame_url=response.frame.url if response.frame else None,
            security_details=security_details,
            from_service_worker=response.from_service_worker,
        )

        data.response_log[request_id] = response_entry

    def _log_failed_request(self, request: Request, data: ScanData) -> None:
        request_id = self._request_id(request)
        failure = request.failure
        data.failed_request_log[request_id] = FailedRequestLogEntry(
            timestamp=utc_now_iso(),
            request_id=request_id,
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
            frame_url=request.frame.url if request.frame else None,
            error_text=failure if failure else None,
            parsed_url=parsed_url_data(request.url),
        )

    async def _collect_storage(
        self,
        context: BrowserContext,
        data: ScanData,
    ) -> None:
        raw_cookies = await context.cookies()
        data.cookies = [CookieEntry.from_playwright_cookie(dict(cookie)) for cookie in raw_cookies]

        storage_state = await context.storage_state()
        origins = storage_state.get("origins", [])
        data.local_storage_by_origin = [
            {
                "origin": origin.get("origin"),
                "local_storage": {
                    item.get("name"): item.get("value")
                    for item in origin.get("localStorage", [])
                },
            }
            for origin in origins
        ]

    async def _wait_for_event_tasks(self, data: ScanData) -> None:
        while data.event_tasks:
            pending_tasks = list(data.event_tasks)
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    async def _serialize_response(
        self, response: Response
    ) -> ResponseLogEntry:
        headers = await response.all_headers()
        try:
            security_details = await response.security_details()
        except Exception:
            security_details = None

        return ResponseLogEntry(
            timestamp=utc_now_iso(),
            request_id=self._request_id(response.request),
            url=response.url,
            status=response.status,
            status_text=response.status_text,
            headers=headers,
            headers_lower={key.lower(): value for key, value in headers.items()},
            resource_type=response.request.resource_type,
            request_method=response.request.method,
            frame_url=response.frame.url if response.frame else None,
            security_details=security_details,
            from_service_worker=response.from_service_worker,
        )

    def _create_event_task(self, data: ScanData, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        data.event_tasks.add(task)
        task.add_done_callback(data.event_tasks.discard)

    @staticmethod
    def _request_id(request: Request) -> str:
        return hex(id(request))



def scan_website(url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return WebsiteScanner(options=options).scan(url)
