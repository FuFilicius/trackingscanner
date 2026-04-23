from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from utils import utc_now_iso


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

    def to_dict(self) -> dict[str, Any]:
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
    scan_end: str | None = None
    error: str | None = None
    cmp: dict[str, Any] = field(default_factory=dict)
    before_accept: dict[str, Any] = field(default_factory=dict)
    after_accept: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "site_url": self.site_url,
            "scan_start": self.scan_start,
            "reachable": self.reachable,
            "cmp": deepcopy(self.cmp),
            "before_accept": deepcopy(self.before_accept),
            "after_accept": deepcopy(self.after_accept),
        }

        if self.scan_end is not None:
            payload["scan_end"] = self.scan_end
        if self.error is not None:
            payload["error"] = self.error

        consolidated_view = self.after_accept or self.before_accept
        for key, value in consolidated_view.items():
            payload[key] = deepcopy(value)

        return payload

    @classmethod
    def failed(cls, url: str, error: str) -> dict[str, Any]:
        result = cls(site_url=url, error=error)
        result.scan_end = utc_now_iso()
        return result.to_dict()
