from __future__ import annotations

from playwright.sync_api import BrowserContext, Page, Response

from scanner_tools.results import ResponsePayload, ScanResult
from scanner_tools.network import request_id
from utils import CookieEntry, ResponseLogEntry, ScanData, utc_now_iso


def collect_storage(context: BrowserContext, data: ScanData) -> None:
    raw_cookies = context.cookies()
    data.cookies = [CookieEntry.from_playwright_cookie(dict(cookie)) for cookie in raw_cookies]

    storage_state = context.storage_state()
    origins = storage_state.get("origins", [])
    data.local_storage_by_origin = [
        {
            "origin": origin.get("origin"),
            "local_storage": {
                item.get("name"): item.get("value") for item in origin.get("localStorage", [])
            },
        }
        for origin in origins
    ]


def serialize_response(response: Response) -> ResponseLogEntry:
    headers = response.all_headers()
    try:
        security_details = response.security_details()
    except Exception:
        security_details = None

    return ResponseLogEntry(
        timestamp=utc_now_iso(),
        request_id=request_id(response.request),
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


def to_response_payload(entry: ResponseLogEntry) -> ResponsePayload:
    return {
        "timestamp": entry.timestamp,
        "request_id": entry.request_id,
        "url": entry.url,
        "status": entry.status,
        "status_text": entry.status_text,
        "headers": entry.headers,
        "headers_lower": entry.headers_lower,
        "resource_type": entry.resource_type,
        "request_method": entry.request_method,
        "frame_url": entry.frame_url,
        "security_details": entry.security_details,
        "from_service_worker": entry.from_service_worker,
    }


def store_final_response(
    result: ScanResult,
    data: ScanData,
    final_response: Response | None,
    page: Page,
    fallback_url: str,
) -> None:
    if final_response is not None:
        data.final_response = serialize_response(final_response)
        result.final_response = to_response_payload(data.final_response)
        result.final_url = final_response.url
        return

    result.final_response = None
    result.final_url = page.url or fallback_url

