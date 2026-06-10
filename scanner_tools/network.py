from __future__ import annotations

import sys
import time
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Request, Response

from utils import (
    FailedRequestLogEntry,
    RequestLogEntry,
    ResponseLogEntry,
    ScanData,
    parsed_url_data,
    utc_now_iso,
)


def request_id(request: Request) -> str:
    return hex(id(request))


class NetworkCollector:
    def __init__(self, options: dict[str, Any]):
        self.options = options

    def register_page_logging(self, page: Page, data: ScanData, scan_label: str) -> None:
        def on_request(request: Request) -> None:
            if data.teardown_started:
                return
            event_request_id = request_id(request)
            data.active_request_ids.add(event_request_id)
            try:
                self._log_request(request, data)
            except PlaywrightError as exc:
                data.active_request_ids.discard(event_request_id)
                if data.teardown_started:
                    return
                self._log_playwright_error(scan_label, "request", exc)

        def on_response(response: Response) -> None:
            if data.teardown_started:
                return
            try:
                self._log_response(response, data)
            except PlaywrightError as exc:
                if data.teardown_started:
                    return
                self._log_playwright_error(scan_label, "response", exc)
                return

        def on_request_finished(request: Request) -> None:
            data.active_request_ids.discard(request_id(request))

        def on_request_failed(request: Request) -> None:
            data.active_request_ids.discard(request_id(request))
            if data.teardown_started:
                return
            try:
                self._log_failed_request(request, data)
            except PlaywrightError as exc:
                if data.teardown_started:
                    return
                self._log_playwright_error(scan_label, "requestfailed", exc)
                return

        data.on_request_handler = on_request
        data.on_response_handler = on_response
        data.on_request_finished_handler = on_request_finished
        data.on_request_failed_handler = on_request_failed

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfinished", on_request_finished)
        page.on("requestfailed", on_request_failed)

    def detach_page_logging(self, page: Page, data: ScanData) -> None:
        listeners = (
            ("request", data.on_request_handler),
            ("response", data.on_response_handler),
            ("requestfinished", data.on_request_finished_handler),
            ("requestfailed", data.on_request_failed_handler),
        )
        for event_name, handler in listeners:
            if handler is None:
                continue
            try:
                page.remove_listener(event_name, handler)
            except PlaywrightError:
                continue

        data.on_request_handler = None
        data.on_response_handler = None
        data.on_request_finished_handler = None
        data.on_request_failed_handler = None

    def wait_for_network_idle(self, data: ScanData) -> bool:
        idle_for_ms = int(self.options.get("network_idle_ms", 3000))
        max_wait_ms = int(self.options.get("network_idle_max_wait_ms", 20000))
        poll_interval_ms = int(self.options.get("network_idle_poll_interval_ms", 250))

        if idle_for_ms <= 0:
            return False

        deadline_ms = int(time.monotonic() * 1000) + max_wait_ms
        idle_since_ms: int | None = None

        while int(time.monotonic() * 1000) < deadline_ms:
            now_ms = int(time.monotonic() * 1000)

            if not data.active_request_ids:
                if idle_since_ms is None:
                    idle_since_ms = now_ms
                elif now_ms - idle_since_ms >= idle_for_ms:
                    return False
            else:
                idle_since_ms = None

            data.page.wait_for_timeout(poll_interval_ms)

        return True

    def _log_request(self, request: Request, data: ScanData) -> None:
        event_request_id = request_id(request)
        headers = request.all_headers()
        body, body_json = self._extract_post_body(request)
        frame_url = self._frame_url(request.frame)

        request_entry = RequestLogEntry(
            timestamp=utc_now_iso(),
            request_id=event_request_id,
            url=request.url,
            method=request.method,
            headers=headers,
            resource_type=request.resource_type,
            frame_url=frame_url,
            is_navigation_request=request.is_navigation_request(),
            parsed_url=parsed_url_data(request.url),
            body=body,
            body_json=body_json,
        )
        data.request_log[event_request_id] = request_entry

    @staticmethod
    def _extract_post_body(request: Request) -> tuple[str | None, Any | None]:
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

    def _log_response(self, response: Response, data: ScanData) -> None:
        event_request_id = request_id(response.request)
        headers = response.all_headers()
        try:
            security_details = response.security_details()
        except Exception:
            security_details = None
        frame_url = self._frame_url(response.frame)

        response_entry = ResponseLogEntry(
            timestamp=utc_now_iso(),
            request_id=event_request_id,
            url=response.url,
            status=response.status,
            status_text=response.status_text,
            headers=headers,
            headers_lower={key.lower(): value for key, value in headers.items()},
            resource_type=response.request.resource_type,
            request_method=response.request.method,
            frame_url=frame_url,
            security_details=security_details,
            from_service_worker=response.from_service_worker,
        )

        data.response_log[event_request_id] = response_entry

    def _log_failed_request(self, request: Request, data: ScanData) -> None:
        event_request_id = request_id(request)
        failure = request.failure
        frame_url = self._frame_url(request.frame)
        data.failed_request_log[event_request_id] = FailedRequestLogEntry(
            timestamp=utc_now_iso(),
            request_id=event_request_id,
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
            frame_url=frame_url,
            error_text=failure if failure else None,
            parsed_url=parsed_url_data(request.url),
        )

    @staticmethod
    def _frame_url(frame: Any) -> str | None:
        if frame is None:
            return None
        try:
            return frame.url
        except PlaywrightError:
            return None

    @staticmethod
    def _log_playwright_error(scan_label: str, event_name: str, exc: PlaywrightError) -> None:
        print(
            f"[{utc_now_iso()}] scan={scan_label} event={event_name} playwright_error={exc}",
            file=sys.stderr,
        )

