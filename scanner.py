from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, Request, Response, async_playwright

import extractors
from extractors.base import Extractor


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


SCANNER_INIT_SCRIPT = """
(() => {
    const rootKey = "__scanner__";

    function readRoot() {
        try {
            const raw = window.localStorage.getItem(rootKey);
            return raw ? JSON.parse(raw) : {};
        } catch (error) {
            return {};
        }
    }

    function writeRoot(payload) {
        try {
            window.localStorage.setItem(rootKey, JSON.stringify(payload));
            return true;
        } catch (error) {
            return false;
        }
    }

    window.__websiteScanner = {
        set(key, value) {
            const payload = readRoot();
            payload[key] = value;
            return writeRoot(payload);
        },
        append(key, value) {
            const payload = readRoot();
            const current = Array.isArray(payload[key]) ? payload[key] : [];
            current.push(value);
            payload[key] = current;
            return writeRoot(payload);
        },
        get(key) {
            return readRoot()[key];
        }
    };
})();
"""


@dataclass
class ScanData:
    page: Page
    context: BrowserContext
    request_log: list[dict[str, Any]] = field(default_factory=list)
    response_log: list[dict[str, Any]] = field(default_factory=list)
    failed_request_log: list[dict[str, Any]] = field(default_factory=list)
    cookies: list[dict[str, Any]] = field(default_factory=list)
    final_response: dict[str, Any] | None = None
    local_storage: dict[str, Any] = field(default_factory=dict)
    local_storage_by_origin: list[dict[str, Any]] = field(default_factory=list)
    event_tasks: set[asyncio.Task[Any]] = field(default_factory=set)


class WebsiteScanner:
    def __init__(self, options: dict[str, Any] | None = None):
        self.options = options or {}
        self.extractor_classes = self._discover_extractor_classes()

    def scan(self, url: str) -> dict[str, Any]:
        return asyncio.run(self.scan_async(url))

    async def scan_async(self, url: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "site_url": url,
            "scan_start": _utc_now_iso(),
            "reachable": False,
        }

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.options.get("headless", True)
            )
            context = await browser.new_context(
                ignore_https_errors=self.options.get("ignore_https_errors", True),
                java_script_enabled=self.options.get("java_script_enabled", True),
                viewport=self.options.get(
                    "viewport", {"width": 1920, "height": 1080}
                ),
                user_agent=self.options.get("user_agent"),
            )
            page = await context.new_page()
            data = ScanData(page=page, context=context)
            extractor_instances = [
                extractor_class(result=result, options=self.options, data=data)
                for extractor_class in self.extractor_classes
            ]

            self._register_page_logging(page, data)
            await self._register_extractor_javascript(context, extractor_instances)

            final_response = None
            try:
                final_response = await page.goto(
                    url,
                    wait_until=self.options.get("wait_until", "networkidle"),
                    timeout=self.options.get("timeout", 30000),
                )
                result["reachable"] = True
                wait_after_load = self.options.get("wait_after_load", 2000)
                if wait_after_load > 0:
                    await page.wait_for_timeout(wait_after_load)
            except Exception as exc:
                result["error"] = str(exc)
            finally:
                await self._wait_for_event_tasks(data)
                await self._collect_storage(context, page, data, result)

                if final_response is not None:
                    data.final_response = await self._serialize_response(
                        final_response, include_body=True
                    )
                    result["final_response"] = data.final_response
                    result["final_url"] = final_response.url
                else:
                    result["final_response"] = None
                    result["final_url"] = page.url or url

                result["request_log"] = data.request_log
                result["response_log"] = data.response_log
                result["failed_request_log"] = data.failed_request_log

                await self._run_extractors(extractor_instances)
                result["scan_end"] = _utc_now_iso()
                await browser.close()

        return result

    def _register_page_logging(self, page: Page, data: ScanData) -> None:
        def on_request(request: Request) -> None:
            self._create_event_task(data, self._log_request(request, data))

        def on_response(response: Response) -> None:
            self._create_event_task(data, self._log_response(response, data))

        def on_request_failed(request: Request) -> None:
            self._log_failed_request(request, data)

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)

    async def _register_extractor_javascript(
        self, context: BrowserContext, extractors: list[Extractor]
    ) -> None:
        await context.add_init_script(script=SCANNER_INIT_SCRIPT)

        for extractor in extractors:
            scripts = await _maybe_await(extractor.register_javascript())
            if not scripts:
                continue

            if isinstance(scripts, str):
                await context.add_init_script(script=scripts)
                continue

            for script in scripts:
                if script:
                    await context.add_init_script(script=script)

    async def _run_extractors(self, extractors: list[Extractor]) -> None:
        for extractor in extractors:
            await _maybe_await(extractor.extract_information())

    async def _log_request(self, request: Request, data: ScanData) -> None:
        request_entry = {
            "timestamp": _utc_now_iso(),
            "request_id": self._request_id(request),
            "url": request.url,
            "method": request.method,
            "headers": await request.all_headers(),
            "post_data": request.post_data,
            "resource_type": request.resource_type,
            "frame_url": request.frame.url if request.frame else None,
            "is_navigation_request": request.is_navigation_request(),
            "parsed_url": self._parsed_url_dict(request.url),
        }
        data.request_log.append(request_entry)

    async def _log_response(self, response: Response, data: ScanData) -> None:
        data.response_log.append(await self._serialize_response(response))

    def _log_failed_request(self, request: Request, data: ScanData) -> None:
        failure = request.failure
        data.failed_request_log.append(
            {
                "timestamp": _utc_now_iso(),
                "request_id": self._request_id(request),
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "frame_url": request.frame.url if request.frame else None,
                "error_text": failure["errorText"] if failure else None,
                "parsed_url": self._parsed_url_dict(request.url),
            }
        )

    async def _collect_storage(
        self,
        context: BrowserContext,
        page: Page,
        data: ScanData,
        result: dict[str, Any],
    ) -> None:
        data.cookies = await context.cookies()
        result["cookies"] = data.cookies

        storage_state = await context.storage_state()
        origins = storage_state.get("origins", [])
        data.local_storage_by_origin = [
            {
                "origin": origin.get("origin"),
                "local_storage": {
                    item.get("name"): item.get("value")
                    for item in origin.get("localStorage", [])
                },
            }
            for origin in origins
        ]
        result["local_storage_by_origin"] = data.local_storage_by_origin
        data.local_storage = self._local_storage_for_page_url(
            page.url, data.local_storage_by_origin
        )
        result["local_storage"] = data.local_storage

    async def _wait_for_event_tasks(self, data: ScanData) -> None:
        if not data.event_tasks:
            return

        pending_tasks = list(data.event_tasks)
        await asyncio.gather(*pending_tasks, return_exceptions=True)

    async def _serialize_response(
        self, response: Response, include_body: bool = False
    ) -> dict[str, Any]:
        headers = await response.all_headers()
        security_details = None
        try:
            security_details = await response.security_details()
        except Exception:
            security_details = None

        payload = {
            "timestamp": _utc_now_iso(),
            "request_id": self._request_id(response.request),
            "url": response.url,
            "status": response.status,
            "status_text": response.status_text,
            "headers": headers,
            "headers_lower": {key.lower(): value for key, value in headers.items()},
            "resource_type": response.request.resource_type,
            "request_method": response.request.method,
            "frame_url": response.frame.url if response.frame else None,
            "security_details": security_details,
            "from_service_worker": response.from_service_worker,
        }

        if include_body:
            payload.update(await self._extract_response_body(response))

        return payload

    async def _extract_response_body(self, response: Response) -> dict[str, Any]:
        try:
            body = await response.body()
        except Exception as exc:
            return {"body_error": str(exc)}

        encoding = "utf-8"
        text = None
        try:
            text = body.decode(encoding)
        except UnicodeDecodeError:
            encoding = None

        return {
            "body_base64": base64.b64encode(body).decode("ascii"),
            "body_text": text,
            "body_encoding": encoding,
        }

    def _discover_extractor_classes(self) -> list[type[Extractor]]:
        discovered: list[type[Extractor]] = []
        for module in self._iter_extractor_modules():
            for _, member in inspect.getmembers(module, inspect.isclass):
                if member is Extractor:
                    continue
                if issubclass(member, Extractor):
                    discovered.append(member)

        discovered.sort(key=lambda extractor_class: extractor_class.__name__)
        return discovered

    def _iter_extractor_modules(self) -> list[ModuleType]:
        modules: list[ModuleType] = []
        for module_info in pkgutil.iter_modules(extractors.__path__):
            if module_info.name.startswith("_") or module_info.name == "base":
                continue
            module = importlib.import_module(f"{extractors.__name__}.{module_info.name}")
            modules.append(module)
        return modules

    def _create_event_task(self, data: ScanData, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        data.event_tasks.add(task)
        task.add_done_callback(data.event_tasks.discard)

    @staticmethod
    def _request_id(request: Request) -> str:
        return hex(id(request))

    @staticmethod
    def _local_storage_for_page_url(
        page_url: str, local_storage_by_origin: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not page_url:
            return {}

        parsed = urlparse(page_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
        if not origin:
            return {}

        for entry in local_storage_by_origin:
            if entry.get("origin") == origin:
                return entry.get("local_storage", {})
        return {}

    @staticmethod
    def _parsed_url_dict(url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        return {
            "scheme": parsed.scheme,
            "netloc": parsed.netloc,
            "path": parsed.path,
            "params": parsed.params,
            "query": parsed.query,
            "fragment": parsed.fragment,
            "hostname": parsed.hostname,
            "port": parsed.port,
        }


def scan_website(url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return WebsiteScanner(options=options).scan(url)
