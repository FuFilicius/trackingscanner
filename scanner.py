from __future__ import annotations

from typing import Any

from scan_job import ScanJob
from scan_master import ScanMaster
from scan_worker import ScanWorker
from website_scanner import WebsiteScanner


def scan(
    urls: list[str],
    options: dict[str, Any] | None = None,
    max_concurrency: int = 1,
) -> list[dict[str, Any]]:
    if not isinstance(urls, list):
        raise TypeError("urls must be a list[str]")
    if not urls:
        return []

    worker_count = min(max(1, int(max_concurrency)), len(urls))
    master = ScanMaster(options=options or {}, worker_count=worker_count)
    scanner = WebsiteScanner(options=options or {})

    results_by_index: dict[int, dict[str, Any]] = {}
    interrupted = False

    try:
        master.start()
        for index, url in enumerate(urls):
            master.queue_url(url, job_id=index)

        while len(results_by_index) < len(urls):
            result_item = master.get_result(timeout=0.5)
            if result_item is None:
                if not master.has_alive_workers() and master.pending_results() == 0:
                    break
                continue

            index, result = result_item
            results_by_index[index] = result
    except KeyboardInterrupt:
        interrupted = True
        master.request_stop()
    finally:
        master.end()

    final_results: list[dict[str, Any]] = []
    for index, url in enumerate(urls):
        if index in results_by_index:
            final_results.append(results_by_index[index])
        elif interrupted:
            final_results.append(scanner.failed_result(url, "scan interrupted"))
        else:
            final_results.append(scanner.failed_result(url, "scan did not complete"))

    return final_results


def create_scan_master(
    options: dict[str, Any] | None = None,
    worker_count: int = 1,
) -> ScanMaster:
    return ScanMaster(options=options or {}, worker_count=worker_count)


__all__ = [
    "ScanJob",
    "ScanMaster",
    "ScanWorker",
    "WebsiteScanner",
    "create_scan_master",
    "scan",
]
