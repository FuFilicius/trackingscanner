from __future__ import annotations

import multiprocessing as mp
import queue
from collections.abc import Iterable
from typing import Any

from scan_worker import ScanWorker


class ScanMaster:
    def __init__(self, options: dict[str, Any], worker_count: int):
        self.options = options
        self.worker_count = max(1, int(worker_count))
        self.ctx = mp.get_context("spawn")
        self.task_queue = self.ctx.Queue()
        self.result_queue = self.ctx.Queue()
        self.stop_event = self.ctx.Event()
        self.workers: list[mp.Process] = []
        self._started = False
        self._queued_jobs = 0
        self._received_jobs = 0
        self._next_job_id = 0

    @property
    def started(self) -> bool:
        return self._started

    def start(self) -> None:
        if self._started:
            return

        self.workers = [
            self.ctx.Process(
                target=ScanWorker.run_loop,
                args=(self.task_queue, self.result_queue, self.stop_event, self.options),
                daemon=True,
            )
            for _ in range(self.worker_count)
        ]

        for worker in self.workers:
            worker.start()

        self._started = True

    def queue_url(self, url: str, job_id: int | None = None) -> int:
        if not self._started:
            raise RuntimeError("ScanMaster must be started before queueing jobs")

        current_job_id = self._next_job_id if job_id is None else int(job_id)
        self.task_queue.put((current_job_id, url))
        self._queued_jobs += 1
        self._next_job_id = max(self._next_job_id, current_job_id + 1)
        return current_job_id

    def queue_urls(self, urls: Iterable[str]) -> list[int]:
        if isinstance(urls, str):
            raise TypeError("urls must be an iterable of URL strings, not a single string")
        return [self.queue_url(url) for url in urls]

    def get_result(self, timeout: float = 0.5) -> tuple[int, dict[str, Any]] | None:
        if not self._started:
            raise RuntimeError("ScanMaster must be started before reading results")

        try:
            result = self.result_queue.get(timeout=timeout)
            self._received_jobs += 1
            return result
        except queue.Empty:
            return None

    def pending_results(self) -> int:
        return max(0, self._queued_jobs - self._received_jobs)

    def has_alive_workers(self) -> bool:
        return any(worker.is_alive() for worker in self.workers)

    def request_stop(self) -> None:
        self.stop_event.set()

    def stop(self) -> None:
        self.request_stop()
        self.end()

    def close(self) -> None:
        self.stop()

    def end(self) -> None:
        if not self._started:
            return

        for _ in self.workers:
            try:
                self.task_queue.put_nowait(None)
            except Exception:
                break

        for worker in self.workers:
            worker.join(timeout=2)

        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()

        for worker in self.workers:
            worker.join(timeout=2)

        self.task_queue.close()
        self.result_queue.close()
        self._started = False

    def __enter__(self) -> "ScanMaster":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

