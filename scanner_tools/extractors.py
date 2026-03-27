from __future__ import annotations

from typing import Any

from playwright.async_api import BrowserContext

from extractors import (
    CookiesExtractor,
    FailedRequestsExtractor,
    FacebookPixelExtractor,
    FingerprintingExtractor,
    RequestsExtractor,
    SessionRecordersExtractor,
    ThirdPartyExtractor,
    TiktokPixelExtractor,
    TrackerExtractor,
    TwitterPixelExtractor,
)
from extractors.base import Extractor
from extractors.googleanalytics import GoogleAnalyticsExtractor
from utils import ScanData

EXTRACTOR_CLASSES: list[type[Extractor]] = [
    ThirdPartyExtractor,
    TrackerExtractor,
    CookiesExtractor,
    RequestsExtractor,
    FailedRequestsExtractor,
    FacebookPixelExtractor,
    GoogleAnalyticsExtractor,
    TwitterPixelExtractor,
    TiktokPixelExtractor,
    SessionRecordersExtractor,
    FingerprintingExtractor,
]


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


def create_extractors(
    extractor_classes: list[type[Extractor]],
    result: dict[str, Any],
    options: dict[str, Any],
    data: ScanData,
) -> list[Extractor]:
    return [
        extractor_class(result=result, options=options, data=data)
        for extractor_class in extractor_classes
    ]


async def register_extractor_javascript(
    context: BrowserContext,
    extractors: list[Extractor],
    scanner_init_script: str,
) -> None:
    await context.add_init_script(script=scanner_init_script)

    for extractor in extractors:
        scripts = extractor.register_javascript()
        if not scripts:
            continue

        if isinstance(scripts, str):
            await context.add_init_script(script=scripts)
            continue

        for script in scripts:
            if script:
                await context.add_init_script(script=script)


def run_extractors(extractors: list[Extractor]) -> None:
    for extractor in extractors:
        extractor.extract_information()