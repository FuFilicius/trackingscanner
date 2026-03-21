from __future__ import annotations

import json
from typing import Any

from extractors.base import Extractor


INSTRUMENTATION_JS = """
(() => {
    function safeSerialize(value) {
        try {
            return JSON.parse(JSON.stringify(value));
        } catch (error) {
            try {
                return String(value);
            } catch (stringError) {
                return null;
            }
        }
    }

    function storeLog(logType, payload) {
        if (!window.__websiteScanner || typeof window.__websiteScanner.append !== "function") {
            return;
        }

        window.__websiteScanner.append("fingerprinting_logs", {
            log_type: logType,
            payload: safeSerialize(payload),
            ts: Date.now()
        });
    }

    function instrumentFunction(func, name, logType) {
        return function() {
            const retval = func.apply(this, arguments);

            storeLog(logType, {
                type: "function",
                name: name,
                arguments: Array.prototype.slice.call(arguments).map(safeSerialize),
                retval: safeSerialize(retval)
            });

            return retval;
        };
    }

    function instrumentProperty(obj, prop, name, logType) {
        let prototype = obj;
        let descriptor;

        do {
            descriptor = Object.getOwnPropertyDescriptor(prototype, prop);
            if (typeof descriptor !== "undefined") {
                break;
            }
            prototype = Object.getPrototypeOf(prototype);
        } while (prototype !== null);

        if (typeof descriptor === "undefined") {
            return;
        }

        const origGetter = descriptor.get;
        const origSetter = descriptor.set;

        Object.defineProperty(obj, prop, {
            configurable: true,
            enumerable: descriptor.enumerable,

            get: function() {
                const value = origGetter ? origGetter.apply(this, arguments) : undefined;

                storeLog(logType, {
                    type: "property",
                    name: name,
                    value: safeSerialize(value),
                    access: "get"
                });

                return value;
            },

            set: function() {
                const newValue = arguments[0];

                storeLog(logType, {
                    type: "property",
                    name: name,
                    value: safeSerialize(newValue),
                    access: "set"
                });

                if (origSetter) {
                    return origSetter.apply(this, arguments);
                }
            }
        });
    }

    function instrumentObject(obj, name, properties, logType) {
        if (!obj) {
            return;
        }

        for (let i = 0; i < properties.length; i++) {
            const prop = properties[i];

            if (typeof obj[prop] === "function") {
                obj[prop] = instrumentFunction(obj[prop], name + "." + prop, logType);
            } else {
                instrumentProperty(obj, prop, name + "." + prop, logType);
            }
        }
    }

    if (window.__websiteScanner && typeof window.__websiteScanner.set === "function") {
        window.__websiteScanner.set("fingerprinting_logs", []);
    }

    instrumentObject(
        window.HTMLCanvasElement && window.HTMLCanvasElement.prototype,
        "HTMLCanvasElement",
        ["toDataURL"],
        "fingerprinting:canvas"
    );

    instrumentObject(
        window.CanvasRenderingContext2D && window.CanvasRenderingContext2D.prototype,
        "CanvasRenderingContext2D",
        ["fillText", "strokeText", "getImageData"],
        "fingerprinting:canvas"
    );

    instrumentObject(
        window.WebGLRenderingContext && window.WebGLRenderingContext.prototype,
        "WebGLRenderingContext",
        ["drawArrays", "getSupportedExtensions", "getExtension"],
        "fingerprinting:webGL"
    );

    instrumentObject(
        window.RTCPeerConnection && window.RTCPeerConnection.prototype,
        "RTCPeerConnection",
        ["createDataChannel", "createOffer", "onicecandidate"],
        "fingerprinting:webRTC"
    );
})();
"""


class FingerprintingExtractor(Extractor):
    def register_javascript(self):
        return INSTRUMENTATION_JS

    def extract_information(self):
        logs = self._read_logs_from_local_storage()

        canvas = {"calls": [], "is_fingerprinting": False}
        webgl = {"calls": [], "have_webGL": False}
        webrtc = {"calls": [], "have_webRTC": False}
        font = {"calls": [], "have_font_fingerprinting": False}

        canvas_text_methods = {
            "CanvasRenderingContext2D.fillText",
            "CanvasRenderingContext2D.strokeText",
            "CanvasRenderingContext2D.getImageData",
        }
        webgl_methods = {
            "WebGLRenderingContext.drawArrays",
            "WebGLRenderingContext.getSupportedExtensions",
            "WebGLRenderingContext.getExtension",
        }
        webrtc_methods = {
            "RTCPeerConnection.createDataChannel",
            "RTCPeerConnection.createOffer",
            "RTCPeerConnection.onicecandidate",
        }

        saw_canvas_text_or_pixels = False
        saw_canvas_to_data_url = False

        for entry in logs:
            log_type = entry.get("log_type")
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue

            method_name = payload.get("name")
            if not isinstance(method_name, str):
                continue

            call = {
                "method": method_name,
                "type": payload.get("type"),
                "arguments": payload.get("arguments") if isinstance(payload.get("arguments"), list) else [],
                "timestamp": entry.get("ts"),
            }

            if log_type == "fingerprinting:canvas":
                canvas["calls"].append(call)
                if method_name in canvas_text_methods:
                    saw_canvas_text_or_pixels = True
                if method_name == "HTMLCanvasElement.toDataURL":
                    saw_canvas_to_data_url = True
            elif log_type == "fingerprinting:webGL":
                webgl["calls"].append(call)
                if method_name in webgl_methods:
                    webgl["have_webGL"] = True
            elif log_type == "fingerprinting:webRTC":
                webrtc["calls"].append(call)
                if method_name in webrtc_methods:
                    webrtc["have_webRTC"] = True

        canvas["is_fingerprinting"] = saw_canvas_text_or_pixels and saw_canvas_to_data_url

        self.result["fingerprinting"] = {
            "canvas": canvas,
            "webGL": webgl,
            "webRTC": webrtc
        }

    def _read_logs_from_local_storage(self) -> list[dict[str, Any]]:
        merged_logs: list[dict[str, Any]] = []

        for origin_entry in self.data.local_storage_by_origin:
            if not isinstance(origin_entry, dict):
                continue
            local_storage = origin_entry.get("local_storage")
            merged_logs.extend(self._extract_logs_from_storage(local_storage))

        return merged_logs


    @staticmethod
    def _extract_logs_from_storage(local_storage: Any) -> list[dict[str, Any]]:
        if not isinstance(local_storage, dict):
            return []

        scanner_payload = local_storage.get("__scanner__")
        if not scanner_payload:
            return []

        if isinstance(scanner_payload, str):
            try:
                scanner_payload = json.loads(scanner_payload)
            except json.JSONDecodeError:
                return []

        if not isinstance(scanner_payload, dict):
            return []

        logs = scanner_payload.get("fingerprinting_logs")
        if not isinstance(logs, list):
            return []

        return [entry for entry in logs if isinstance(entry, dict)]


