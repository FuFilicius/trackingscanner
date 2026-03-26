from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import Page, Request, Response

from utils import FailedRequestLogEntry, RequestLogEntry, ResponseLogEntry, ScanData, parsed_url_data, utc_now_iso


def request_id(request: Request) -> str:
    return hex(id(request))


class NetworkCollector:
    def __init__(self, options: dict[str, Any]):
        self.options = options

    def register_page_logging(self, page: Page, data: ScanData) -> None:
        def on_request(request: Request) -> None:
            data.active_request_ids.add(request_id(request))
            self._create_event_task(data, self._log_request(request, data))

        def on_response(response: Response) -> None:
            self._create_event_task(data, self._log_response(response, data))

        def on_request_finished(request: Request) -> None:
            data.active_request_ids.discard(request_id(request))

        def on_request_failed(request: Request) -> None:
            data.active_request_ids.discard(request_id(request))
            self._log_failed_request(request, data)

        data.on_request_handler = on_request
        data.on_response_handler = on_response
        data.on_request_finished_handler = on_request_finished
        data.on_request_failed_handler = on_request_failed

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfinished", on_request_finished)
        page.on("requestfailed", on_request_failed)

    def detach_page_logging(self, page: Page, data: ScanData) -> None:
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

    async def wait_for_network_idle(self, data: ScanData) -> None:
        idle_for_ms = int(self.options.get("network_idle_ms", 2000))
        max_wait_ms = int(self.options.get("network_idle_max_wait_ms", 15000))
        poll_interval_ms = int(self.options.get("network_idle_poll_interval_ms", 200))

        if idle_for_ms <= 0:
            return

        deadline_ms = int(time.monotonic() * 1000) + max_wait_ms
        idle_since_ms: int | None = None

        while int(time.monotonic() * 1000) < deadline_ms:
            await self.wait_for_event_tasks(data)
            now_ms = int(time.monotonic() * 1000)

            if not data.active_request_ids:
                if idle_since_ms is None:
                    idle_since_ms = now_ms
                elif now_ms - idle_since_ms >= idle_for_ms:
                    return
            else:
                idle_since_ms = None

            await asyncio.sleep(poll_interval_ms / 1000)

    async def wait_for_event_tasks(self, data: ScanData) -> None:
        while data.event_tasks:
            pending_tasks = list(data.event_tasks)
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    def _create_event_task(self, data: ScanData, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        data.event_tasks.add(task)
        task.add_done_callback(data.event_tasks.discard)

    async def _log_request(self, request: Request, data: ScanData) -> None:
        event_request_id = request_id(request)
        headers = await request.all_headers()
        body, body_json = self._extract_post_body(request)

        request_entry = RequestLogEntry(
            timestamp=utc_now_iso(),
            request_id=event_request_id,
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

    async def _log_response(self, response: Response, data: ScanData) -> None:
        event_request_id = request_id(response.request)
        headers = await response.all_headers()
        try:
            security_details = await response.security_details()
        except Exception:
            security_details = None

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
            frame_url=response.frame.url if response.frame else None,
            security_details=security_details,
            from_service_worker=response.from_service_worker,
        )

        data.response_log[event_request_id] = response_entry

    def _log_failed_request(self, request: Request, data: ScanData) -> None:
        event_request_id = request_id(request)
        failure = request.failure
        data.failed_request_log[event_request_id] = FailedRequestLogEntry(
            timestamp=utc_now_iso(),
            request_id=event_request_id,
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
            frame_url=request.frame.url if request.frame else None,
            error_text=failure if failure else None,
            parsed_url=parsed_url_data(request.url),
        )

