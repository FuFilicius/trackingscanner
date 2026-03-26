from __future__ import annotations

from typing import Any

from playwright.async_api import BrowserContext

from extractors.base import Extractor
from utils import ScanData, maybe_await


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
        scripts = await maybe_await(extractor.register_javascript())
        if not scripts:
            continue

        if isinstance(scripts, str):
            await context.add_init_script(script=scripts)
            continue

        for script in scripts:
            if script:
                await context.add_init_script(script=script)


async def run_extractors(extractors: list[Extractor]) -> None:
    for extractor in extractors:
        await maybe_await(extractor.extract_information())


