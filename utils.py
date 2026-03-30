from __future__ import annotations

from dataclasses import asdict, field, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page
from tldextract import TLDExtract


@dataclass
class ParsedUrl:
    scheme: str
    netloc: str
    path: str
    params: str
    query: str
    fragment: str
    hostname: str | None
    port: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RequestLogEntry:
    timestamp: str
    request_id: str
    url: str
    method: str
    headers: dict[str, str]
    resource_type: str
    frame_url: str | None
    is_navigation_request: bool
    parsed_url: ParsedUrl
    body: str | None = None
    body_json: Any | None = None
    is_thirdparty: bool = False
    is_tracker: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["parsed_url"] = self.parsed_url.to_dict()
        return payload


@dataclass
class ResponseLogEntry:
    timestamp: str
    request_id: str
    url: str
    status: int
    status_text: str
    headers: dict[str, str]
    headers_lower: dict[str, str]
    resource_type: str
    request_method: str
    frame_url: str | None
    security_details: Any
    from_service_worker: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailedRequestLogEntry:
    timestamp: str
    request_id: str
    url: str
    method: str
    resource_type: str
    frame_url: str | None
    error_text: Any | None
    parsed_url: ParsedUrl

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["parsed_url"] = self.parsed_url.to_dict()
        return payload


@dataclass
class CookieEntry:
    name: str
    value: str
    domain: str
    path: str
    expires: float
    http_only: bool
    secure: bool
    same_site: str | None
    is_thirdparty: bool = False
    is_tracker: bool = False
    lifetime: int = -1

    @classmethod
    def from_playwright_cookie(cls, cookie: dict[str, Any]) -> "CookieEntry":
        return cls(
            name=str(cookie.get("name", "")),
            value=str(cookie.get("value", "")),
            domain=str(cookie.get("domain", "")),
            path=str(cookie.get("path", "/")),
            expires=float(cookie.get("expires", -1)),
            http_only=bool(cookie.get("httpOnly", False)),
            secure=bool(cookie.get("secure", False)),
            same_site=(
                str(cookie.get("sameSite"))
                if cookie.get("sameSite") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
            "httpOnly": self.http_only,
            "secure": self.secure,
            "sameSite": self.same_site,
            "is_thirdparty": self.is_thirdparty,
            "is_tracker": self.is_tracker,
            "lifetime": self.lifetime,
        }


@dataclass
class ScanData:
    page: Page
    context: BrowserContext
    request_log: dict[str, RequestLogEntry] = field(default_factory=dict)
    response_log: dict[str, ResponseLogEntry] = field(default_factory=dict)
    failed_request_log: dict[str, FailedRequestLogEntry] = field(default_factory=dict)
    cookies: list[CookieEntry] = field(default_factory=list)
    final_response: ResponseLogEntry | None = None
    local_storage: dict[str, Any] = field(default_factory=dict)
    local_storage_by_origin: list[dict[str, Any]] = field(default_factory=list)
    event_tasks: set[Any] = field(default_factory=set)
    on_request_handler: Any | None = None
    on_response_handler: Any | None = None
    on_request_finished_handler: Any | None = None
    on_request_failed_handler: Any | None = None
    active_request_ids: set[str] = field(default_factory=set)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parsed_url_data(url: str) -> ParsedUrl:
    parsed = urlparse(url)
    return ParsedUrl(
        scheme=parsed.scheme,
        netloc=parsed.netloc,
        path=parsed.path,
        params=parsed.params,
        query=parsed.query,
        fragment=parsed.fragment,
        hostname=parsed.hostname,
        port=parsed.port,
    )


def origin_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return None
    return f"{parsed.scheme}://{parsed.hostname}"


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
) -> ResponseLogEntry | None:
    return data.response_log.get(request_id)

parse_domain = TLDExtract()
