from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import NotRequired, TypedDict

from utils import utc_now_iso


CountByKey = dict[str, int]


class CMPInteractionResultDict(TypedDict):
    attempted: bool
    accept_clicked: bool
    clicked_word: str | None
    clicked_text: str | None
    clicked_selector: str | None
    frame_url: str | None
    strategy: str | None
    error: str | None
    wait_after_click_ms: int


class ResponsePayload(TypedDict):
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
    security_details: object | None
    from_service_worker: bool


class RequestsSummary(TypedDict):
    total: int
    with_response: int
    set_cookie: int
    methods: CountByKey
    resource_types: CountByKey
    status_classes: CountByKey
    counts_by_fqdn: CountByKey


class FailedRequestsSummary(TypedDict):
    total: int
    by_error: CountByKey
    by_method: CountByKey
    by_resource_type: CountByKey
    counts_by_fqdn: CountByKey


class CookiesSummary(TypedDict):
    total: int
    session: int
    persistent: int
    http_only: int
    secure: int
    thirdparty: int
    tracker: int
    same_site: CountByKey
    counts_by_fqdn: CountByKey


class ThirdPartiesSummary(TypedDict):
    fqdns: list[str]
    request_counts_by_fqdn: CountByKey
    num_http_requests: int
    num_https_requests: int
    num_cookies: int
    cookie_domains: list[str]
    cookie_counts_by_fqdn: CountByKey


class TrackersSummary(TypedDict):
    trackers: list[str]
    num_tracker_requests: int
    tracker_request_counts_by_fqdn: CountByKey
    num_tracker_cookies: int
    tracker_cookie_domains: list[str]
    tracker_cookie_counts_by_fqdn: CountByKey


class PixelEventsSummary(TypedDict):
    events: list[str]


class FacebookPixelSummary(PixelEventsSummary):
    facebook_pixel: bool


class TwitterPixelSummary(PixelEventsSummary):
    twitter_pixel: bool


class TiktokPixelSummary(PixelEventsSummary):
    tiktok_pixel: bool


class GoogleAnalyticsSummary(TypedDict):
    has_tracker: bool
    ids: list[str]


class SessionRecordersSummary(TypedDict):
    session_recording: bool
    services: list[str]


class FingerprintingCall(TypedDict):
    method: str
    type: object | None
    arguments: list[object]
    timestamp: object | None


class FingerprintingCanvasSummary(TypedDict):
    calls: list[FingerprintingCall]
    is_fingerprinting: bool


class FingerprintingWebGLSummary(TypedDict):
    calls: list[FingerprintingCall]
    have_webGL: bool


class FingerprintingWebRTCSummary(TypedDict):
    calls: list[FingerprintingCall]
    have_webRTC: bool


class FingerprintingSummary(TypedDict):
    canvas: FingerprintingCanvasSummary
    webGL: FingerprintingWebGLSummary
    webRTC: FingerprintingWebRTCSummary


class ScanPhaseResult(TypedDict, total=False):
    site_url: str
    final_url: str | None
    scan_start: str
    network_idle_max_wait_exceeded: bool
    requests: RequestsSummary
    failed_requests: FailedRequestsSummary
    cookies: CookiesSummary
    third_parties: ThirdPartiesSummary
    trackers: TrackersSummary
    facebook_pixel: FacebookPixelSummary
    google_analytics: GoogleAnalyticsSummary
    twitter_pixel: TwitterPixelSummary
    tiktok_pixel: TiktokPixelSummary
    session_recorders: SessionRecordersSummary
    fingerprinting: FingerprintingSummary
    local_storage_by_origin: list[dict[str, object]]


class ScanResultPayload(TypedDict):
    site_url: str
    scan_start: str
    reachable: bool
    cmp: CMPInteractionResultDict
    before_accept: ScanPhaseResult
    after_accept: ScanPhaseResult
    requests: NotRequired[RequestsSummary]
    failed_requests: NotRequired[FailedRequestsSummary]
    cookies: NotRequired[CookiesSummary]
    local_storage_by_origin: NotRequired[list[dict[str, object]]]
    final_url: NotRequired[str]
    final_response: NotRequired[ResponsePayload | None]
    network_idle_max_wait_exceeded: NotRequired[bool]
    scan_end: NotRequired[str]
    error: NotRequired[str]


ScanResultsByUrl = dict[str, ScanResultPayload]


@dataclass
class CMPInteractionResult:
    attempted: bool = False
    accept_clicked: bool = False
    clicked_word: str | None = None
    clicked_text: str | None = None
    clicked_selector: str | None = None
    frame_url: str | None = None
    strategy: str | None = None
    error: str | None = None
    wait_after_click_ms: int = 0

    def to_dict(self) -> CMPInteractionResultDict:
        return {
            "attempted": self.attempted,
            "accept_clicked": self.accept_clicked,
            "clicked_word": self.clicked_word,
            "clicked_text": self.clicked_text,
            "clicked_selector": self.clicked_selector,
            "frame_url": self.frame_url,
            "strategy": self.strategy,
            "error": self.error,
            "wait_after_click_ms": self.wait_after_click_ms,
        }


@dataclass
class ScanResult:
    site_url: str
    scan_start: str = field(default_factory=utc_now_iso)
    reachable: bool = False
    final_url: str | None = None
    final_response: ResponsePayload | None = None
    network_idle_max_wait_exceeded: bool | None = None
    scan_end: str | None = None
    error: str | None = None
    cmp: CMPInteractionResultDict = field(default_factory=lambda: CMPInteractionResult().to_dict())
    before_accept: ScanPhaseResult = field(default_factory=dict)
    after_accept: ScanPhaseResult = field(default_factory=dict)

    def to_dict(self) -> ScanResultPayload:
        payload: ScanResultPayload = {
            "site_url": self.site_url,
            "scan_start": self.scan_start,
            "reachable": self.reachable,
            "cmp": deepcopy(self.cmp),
            "before_accept": deepcopy(self.before_accept),
            "after_accept": deepcopy(self.after_accept),
        }

        if self.final_url is not None:
            payload["final_url"] = self.final_url
            payload["final_response"] = deepcopy(self.final_response)
        if self.network_idle_max_wait_exceeded is not None:
            payload["network_idle_max_wait_exceeded"] = self.network_idle_max_wait_exceeded
        if self.scan_end is not None:
            payload["scan_end"] = self.scan_end
        if self.error is not None:
            payload["error"] = self.error

        return payload

    @classmethod
    def failed(cls, url: str, error: str) -> ScanResultPayload:
        result = cls(site_url=url, error=error)
        result.scan_end = utc_now_iso()
        return result.to_dict()
