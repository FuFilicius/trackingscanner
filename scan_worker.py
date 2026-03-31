from __future__ import annotations

import queue
from typing import Any

from playwright.sync_api import sync_playwright

from scan_job import ScanJob
from website_scanner import WebsiteScanner


class ScanWorker:
    @staticmethod
    def run_loop(
        task_queue: Any,
        result_queue: Any,
        stop_event: Any,
        options: dict[str, Any],
    ) -> None:
        scanner = WebsiteScanner(options=options)
        with sync_playwright() as playwright:
            browser = scanner.launch_browser(playwright)
            try:
                while not stop_event.is_set():
                    try:
                        payload = task_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    if payload is None:
                        break

                    job_id, url = payload
                    job = ScanJob(job_id=job_id, url=url)
                    result_queue.put((job.job_id, job.run(scanner, browser)))
            finally:
                browser.close()

