from __future__ import annotations

import asyncio
import inspect
from dataclasses import field, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, Cookie
from tldextract import TLDExtract


@dataclass
class ScanData:
    page: Page
    context: BrowserContext
    request_log: dict[str, dict[str, Any]] = field(default_factory=dict)
    response_log: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_request_log: dict[str, dict[str, Any]] = field(default_factory=dict)
    cookies: list[Cookie] = field(default_factory=list)
    final_response: dict[str, Any] | None = None
    local_storage: dict[str, Any] = field(default_factory=dict)
    local_storage_by_origin: list[dict[str, Any]] = field(default_factory=list)
    event_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    on_request_handler: Any | None = None
    on_response_handler: Any | None = None
    on_request_finished_handler: Any | None = None
    on_request_failed_handler: Any | None = None
    active_request_ids: set[str] = field(default_factory=set)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def parsed_url_dict(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "netloc": parsed.netloc,
        "path": parsed.path,
        "params": parsed.params,
        "query": parsed.query,
        "fragment": parsed.fragment,
        "hostname": parsed.hostname,
        "port": parsed.port,
    }


def origin_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def local_storage_for_page_url(
    page_url: str, local_storage_by_origin: list[dict[str, Any]]
) -> dict[str, Any]:
    if not page_url:
        return {}

    origin = origin_from_url(page_url)
    if not origin:
        return {}

    for entry in local_storage_by_origin:
        if entry.get("origin") == origin:
            return entry.get("local_storage", {})

    return {}

def get_corresponding_response(
        request_id: str, data: ScanData
) -> dict[str, Any] | None:
    return data.response_log.get(request_id)

parse_domain = TLDExtract()