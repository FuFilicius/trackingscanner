from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Browser

from website_scanner import WebsiteScanner


@dataclass(frozen=True)
class ScanJob:
    job_id: int
    url: str

    def run(self, scanner: WebsiteScanner, browser: Browser) -> dict[str, Any]:
        return scanner.scan_one_url_with_browser(self.url, browser)

