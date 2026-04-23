from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from scan_master import ScanMaster
from scanner import scan as run_scan


def scan(
    urls: Sequence[str],
    options: dict[str, Any] | None = None,
    max_concurrency: int = 1,
) -> list[dict[str, Any]]:
    return run_scan(list(urls), options=options, max_concurrency=max_concurrency)


class ScanController:
    def __init__(
        self,
        options: dict[str, Any] | None = None,
        worker_count: int = 1,
    ) -> None:
        self._master = ScanMaster(options=options or {}, worker_count=worker_count)

    @property
    def started(self) -> bool:
        return self._master.started

    def start(self) -> "ScanController":
        self._master.start()
        return self

    def queue_url(self, url: str, job_id: int | None = None) -> int:
        return self._master.queue_url(url, job_id=job_id)

    def queue_urls(self, urls: Iterable[str]) -> list[int]:
        return self._master.queue_urls(urls)

    def get_result(self, timeout: float = 0.5) -> tuple[int, dict[str, Any]] | None:
        return self._master.get_result(timeout=timeout)

    def drain_results(self, timeout: float = 0.1) -> list[tuple[int, dict[str, Any]]]:
        collected: list[tuple[int, dict[str, Any]]] = []
        while True:
            item = self.get_result(timeout=timeout)
            if item is None:
                return collected
            collected.append(item)

    def pending_results(self) -> int:
        return self._master.pending_results()

    def has_alive_workers(self) -> bool:
        return self._master.has_alive_workers()

    def request_stop(self) -> None:
        self._master.request_stop()

    def stop(self) -> None:
        self._master.stop()

    def close(self) -> None:
        self.stop()

    def __enter__(self) -> "ScanController":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()
