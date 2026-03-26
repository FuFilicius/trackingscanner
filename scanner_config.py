from __future__ import annotations

from extractors import (
    CookiesExtractor,
    FailedRequestsExtractor,
    FacebookPixelExtractor,
    FingerprintingExtractor,
    LocalStorageExtractor,
    RequestsExtractor,
    SessionRecordersExtractor,
    ThirdPartyExtractor,
    TiktokPixelExtractor,
    TrackerExtractor,
    TwitterPixelExtractor,
)
from extractors.base import Extractor

# Import the extractor classes you want to use here and add them to EXTRACTOR_CLASSES.
EXTRACTOR_CLASSES: list[type[Extractor]] = [
    ThirdPartyExtractor,
    TrackerExtractor,
    CookiesExtractor,
    # LocalStorageExtractor,
    RequestsExtractor,
    FailedRequestsExtractor,
    FacebookPixelExtractor,
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

