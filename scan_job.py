from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Browser

from scanner_tools.results import ScanResultPayload
from website_scanner import WebsiteScanner


@dataclass(frozen=True)
class ScanJob:
    job_id: int
    url: str

    def run(self, scanner: WebsiteScanner, browser: Browser) -> ScanResultPayload:
        return scanner.scan_one_url_with_browser(
            self.url,
            browser,
            scan_label=f"job_id={self.job_id} url={self.url}",
        )

