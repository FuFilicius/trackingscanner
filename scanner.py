from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import BrowserContext, Page, Response, async_playwright

from extractors.base import Extractor
from scanner_tools.finalize import collect_storage, store_final_response
from scanner_tools.network import NetworkCollector
from scanner_tools.extractors import (
    EXTRACTOR_CLASSES,
    SCANNER_INIT_SCRIPT,
    create_extractors,
    register_extractor_javascript,
    run_extractors,
)
from utils import ScanData, utc_now_iso


class WebsiteScanner:
    def __init__(self, options: dict[str, Any] | None = None):
        self.options = options or {}
        self.extractor_classes = EXTRACTOR_CLASSES
        self.network_collector = NetworkCollector(self.options)

    def scan(
        self,
        urls: list[str],
        max_concurrency: int = 1,
    ) -> list[dict[str, Any]]:
        return asyncio.run(self.scan_async(urls, max_concurrency=max_concurrency))

    async def scan_async(
        self,
        urls: list[str],
        max_concurrency: int = 1,
    ) -> list[dict[str, Any]]:
        if not isinstance(urls, list):
            raise TypeError("urls must be a list[str]")

        if not urls:
            return []

        concurrency = max(1, int(max_concurrency))
        semaphore = asyncio.Semaphore(concurrency)
        results: list[dict[str, Any] | None] = [None] * len(urls)
        total = len(urls)

        async with async_playwright() as playwright:
            browser = await self._launch_browser(playwright)
            try:
                async def scan_one(index: int, target_url: str) -> None:
                    async with semaphore:
                        results[index] = await self._scan_with_browser(browser, target_url)

                await asyncio.gather(
                    *(scan_one(index, target_url) for index, target_url in enumerate(urls))
                )
            finally:
                await browser.close()

        return [
            result if result is not None else self._failed_result(url, "scan did not complete")
            for url, result in zip(urls, results)
        ]

    async def _launch_browser(self, playwright: Any) -> Any:
        return await playwright.chromium.launch(
            headless=self.options.get("headless", True),
            channel="chrome",
            args=[
                "--disable-features=BlockThirdPartyCookies",
                "--disable-dev-shm-usage",
            ],
        )

    async def _scan_with_browser(self, browser: Any, url: str) -> dict[str, Any]:
        result = self._initial_result(url)
        context: BrowserContext | None = None

        try:
            context = await self._create_context(browser)
            page = await context.new_page()
            data = ScanData(page=page, context=context)
            extractor_instances = create_extractors(self.extractor_classes, result, self.options, data)

            await self._prepare_page(context, page, data, extractor_instances)
            final_response = await self._navigate(page, url, result)
            await self._finalize_scan(
                context=context,
                page=page,
                data=data,
                result=result,
                extractors=extractor_instances,
                final_response=final_response,
                fallback_url=url,
            )
        except Exception as exc:
            result["error"] = str(exc)
            if "scan_end" not in result:
                result["scan_end"] = utc_now_iso()
        finally:
            if context is not None:
                await context.close()

        return result

    def _initial_result(self, url: str) -> dict[str, Any]:
        return {
            "site_url": url,
            "scan_start": utc_now_iso(),
            "reachable": False,
        }

    def _failed_result(self, url: str, error: str) -> dict[str, Any]:
        result = self._initial_result(url)
        result["error"] = error
        result["scan_end"] = utc_now_iso()
        return result

    async def _create_context(self, browser: Any) -> BrowserContext:
        return await browser.new_context(
            ignore_https_errors=self.options.get("ignore_https_errors", True),
            java_script_enabled=self.options.get("java_script_enabled", True),
            viewport=self.options.get("viewport", {"width": 1920, "height": 1080}),
            user_agent=self.options.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"),
        )

    async def _prepare_page(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        extractors: list[Extractor],
    ) -> None:
        self.network_collector.register_page_logging(page, data)
        await register_extractor_javascript(context, extractors, SCANNER_INIT_SCRIPT)

    async def _navigate(
        self, page: Page, url: str, result: dict[str, Any]
    ) -> Response | None:
        try:
            response = await page.goto(
                url,
                wait_until=self.options.get("wait_until", "domcontentloaded"),
                timeout=self.options.get("timeout", 30000),
            )
            result["reachable"] = True
            return response
        except Exception as exc:
            result["error"] = str(exc)
            return None

    async def _finalize_scan(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        result: dict[str, Any],
        extractors: list[Extractor],
        final_response: Response | None,
        fallback_url: str,
    ) -> None:
        await self.network_collector.wait_for_network_idle(data)
        self.network_collector.detach_page_logging(page, data)
        await self.network_collector.wait_for_event_tasks(data)
        await collect_storage(context, data)
        await store_final_response(result, data, final_response, page, fallback_url)
        run_extractors(extractors)
        result["scan_end"] = utc_now_iso()


def scan_websites(
    urls: list[str],
    options: dict[str, Any] | None = None,
    max_concurrency: int = 1,
) -> list[dict[str, Any]]:
    return WebsiteScanner(options=options).scan(urls, max_concurrency=max_concurrency)
