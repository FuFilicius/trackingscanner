from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame, Locator, Page, TimeoutError as PlaywrightTimeoutError

from scanner_tools.results import CMPInteractionResult

ACCEPT_WORDS_PATH = Path(__file__).resolve().parent.parent / "resources" / "accept_words.txt"

_accept_words_cache: dict[str, str] | None = None

_STRIP_CHARS = " \t\r\n✓›!.,;:|/\\()[]{}<>\"'`~_-"
_READ_TIMEOUT_MS = 150


def _normalize_text(value: str) -> str:
    normalized = " ".join(value.casefold().split())
    return normalized.strip(_STRIP_CHARS)


def load_accept_words() -> dict[str, str]:
    global _accept_words_cache
    if _accept_words_cache is not None:
        return _accept_words_cache

    if not ACCEPT_WORDS_PATH.is_file():
        _accept_words_cache = {}
        return _accept_words_cache

    words_by_normalized: dict[str, str] = {}
    for line in ACCEPT_WORDS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw_word = line.strip()
        if not raw_word or raw_word.startswith("#"):
            continue
        normalized = _normalize_text(raw_word)
        if not normalized:
            continue
        # Keep first occurrence as canonical source word.
        words_by_normalized.setdefault(normalized, raw_word)

    _accept_words_cache = words_by_normalized
    return _accept_words_cache


class CMPInteractor:
    def __init__(self, options: dict[str, Any] | None = None):
        options = options or {}
        self.enabled = bool(options.get("cmp_auto_accept", True))
        self.pre_click_wait_ms = int(options.get("cmp_pre_click_wait_ms", 750))
        self.click_timeout_ms = int(options.get("cmp_click_timeout_ms", 1000))
        self.wait_after_click_ms = int(options.get("cmp_wait_after_click_ms", 1000))
        self.accept_words = load_accept_words()
        self.accept_text_pattern = self._build_accept_text_pattern(
            tuple(self.accept_words.values())
        )

    def try_accept(self, page: Page) -> CMPInteractionResult:
        if not self.enabled:
            return CMPInteractionResult(attempted=False)

        if not self.accept_words:
            return CMPInteractionResult(attempted=True, error="accept_words not available")

        if self.pre_click_wait_ms > 0:
            page.wait_for_timeout(self.pre_click_wait_ms)

        for frame in page.frames:
            result = self._try_click_in_frame(frame)
            if result.accept_clicked:
                result.wait_after_click_ms = self.wait_after_click_ms
                return result

        return CMPInteractionResult(attempted=True, wait_after_click_ms=self.wait_after_click_ms)

    def _try_click_in_frame(self, frame: Frame) -> CMPInteractionResult:
        # Role-first, text fallback.
        strategies: list[tuple[str, Locator]] = [
            ("role:button:exact", frame.get_by_role("button", name=self.accept_text_pattern)),
            ("role:link:exact", frame.get_by_role("link", name=self.accept_text_pattern)),
            ("text:exact", frame.get_by_text(self.accept_text_pattern)),
        ]

        for strategy, locator in strategies:
            match = self._find_and_click_exact_match(locator)
            if match is None:
                continue

            clicked_text, clicked_word, clicked_selector = match

            return CMPInteractionResult(
                attempted=True,
                accept_clicked=True,
                clicked_word=clicked_word,
                clicked_text=clicked_text,
                clicked_selector=clicked_selector,
                frame_url=frame.url,
                strategy=strategy,
                wait_after_click_ms=self.wait_after_click_ms,
            )

        return CMPInteractionResult(attempted=True)

    def _find_and_click_exact_match(
        self,
        locator: Locator,
    ) -> tuple[str | None, str, str | None] | None:
        try:
            count = locator.count()
        except (PlaywrightTimeoutError, PlaywrightError):
            return None

        for index in range(count):
            candidate = locator.nth(index)
            candidate_text = self._best_effort_text(candidate)
            if not candidate_text:
                continue
            normalized = _normalize_text(candidate_text)
            clicked_word = self.accept_words.get(normalized)
            if not clicked_word:
                continue

            clicked, clicked_selector = self._click_candidate(candidate)
            if not clicked:
                continue
            return candidate_text, clicked_word, clicked_selector

        return None

    @staticmethod
    def _build_accept_text_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
        escaped_words = [re.escape(word) for word in words if word]
        if not escaped_words:
            return re.compile(r"$^")
        escaped_words.sort(key=len, reverse=True)
        return re.compile(r"^\s*(?:" + "|".join(escaped_words) + r")\s*$", re.IGNORECASE)

    def _click_candidate(self, candidate: Locator) -> tuple[bool, str | None]:
        clicked_selector = self._best_effort_selector(candidate)
        try:
            candidate.click(timeout=self.click_timeout_ms, trial=True)
            candidate.click(timeout=self.click_timeout_ms)
            return True, clicked_selector
        except (PlaywrightTimeoutError, PlaywrightError):
            return False, clicked_selector

    @staticmethod
    def _best_effort_text(locator: Locator) -> str | None:
        try:
            text = locator.text_content(timeout=_READ_TIMEOUT_MS)
        except (PlaywrightTimeoutError, PlaywrightError):
            text = None
        if text and text.strip():
            return text.strip()

        try:
            value = locator.get_attribute("value", timeout=_READ_TIMEOUT_MS)
        except (PlaywrightTimeoutError, PlaywrightError):
            value = None
        if value and value.strip():
            return value.strip()

        try:
            label = locator.get_attribute("aria-label", timeout=_READ_TIMEOUT_MS)
        except (PlaywrightTimeoutError, PlaywrightError):
            label = None
        if label and label.strip():
            return label.strip()

        try:
            title = locator.get_attribute("title", timeout=_READ_TIMEOUT_MS)
        except (PlaywrightTimeoutError, PlaywrightError):
            title = None
        if title and title.strip():
            return title.strip()

        return None

    @staticmethod
    def _best_effort_selector(locator: Locator) -> str | None:
        try:
            metadata = locator.evaluate(
                """el => {
                    const classes = Array.from(el.classList || []).slice(0, 3);
                    const text = (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
                    return {
                        tag: (el.tagName || '').toLowerCase(),
                        id: el.id || null,
                        role: el.getAttribute('role'),
                        name: el.getAttribute('name'),
                        type: el.getAttribute('type'),
                        ariaLabel: el.getAttribute('aria-label'),
                        classes,
                        text
                    };
                }""",
                timeout=_READ_TIMEOUT_MS,
            )
        except (PlaywrightTimeoutError, PlaywrightError):
            return None

        if not isinstance(metadata, dict):
            return None

        tag = metadata.get("tag") or "element"
        selector = tag

        element_id = metadata.get("id")
        if isinstance(element_id, str) and element_id:
            return f"{tag}#{element_id}"

        classes = metadata.get("classes")
        if isinstance(classes, list):
            for class_name in classes:
                if isinstance(class_name, str) and class_name:
                    selector += f".{class_name}"

        attr_order = (
            ("role", metadata.get("role")),
            ("name", metadata.get("name")),
            ("type", metadata.get("type")),
            ("aria-label", metadata.get("ariaLabel")),
        )
        for key, value in attr_order:
            if isinstance(value, str) and value:
                safe_value = value.replace('"', '\\"')
                selector += f'[{key}="{safe_value}"]'

        text = metadata.get("text")
        if isinstance(text, str) and text:
            selector += f'{{text="{text}"}}'

        return selector
