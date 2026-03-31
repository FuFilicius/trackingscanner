from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scanner import scan_websites


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run website scans with Playwright.")
    parser.add_argument(
        "urls",
        nargs="+",
        help="One or more target URLs to scan, e.g. https://example.com",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chromium with a visible window (headless disabled).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30000,
        help="Navigation timeout in milliseconds (default: 30000).",
    )
    parser.add_argument(
        "--wait-until",
        default="domcontentloaded",
        choices=["load", "domcontentloaded", "networkidle", "commit"],
        help="Playwright wait condition for page.goto().",
    )
    parser.add_argument(
        "--strict-https",
        action="store_true",
        help="Do not ignore HTTPS certificate errors.",
    )
    parser.add_argument(
        "--disable-js",
        action="store_true",
        help="Disable JavaScript in the browser context.",
    )
    return parser.parse_args()


def format_overview(result: dict) -> str:
    final_response = result.get("final_response") or {}
    local_storage = result.get("local_storage") or {}
    requests_value = result.get("requests")
    if isinstance(requests_value, dict):
        request_count = requests_value.get("total", 0)
        set_cookie_count = requests_value.get("set_cookie", 0)
    else:
        request_count = len(requests_value or [])
        set_cookie_count = 0

    cookies_value = result.get("cookies")
    if isinstance(cookies_value, dict):
        cookie_count = cookies_value.get("total", 0)
        session_cookie_count = cookies_value.get("session", 0)
        persistent_cookie_count = cookies_value.get("persistent", 0)
    else:
        cookie_count = len(cookies_value or [])
        session_cookie_count = 0
        persistent_cookie_count = 0

    lines = [
        "Scan overview",
        f"- Site URL: {result.get('site_url', '-')}",
        f"- Final URL: {result.get('final_url', '-')}",
        f"- Reachable: {result.get('reachable', False)}",
        f"- Network idle max wait exceeded: {result.get('network_idle_max_wait_exceeded', False)}",
        f"- Status: {final_response.get('status', '-')}",
        f"- Requests: {request_count}",
        f"- Requests setting cookies: {set_cookie_count}",
        f"- Failed requests: {len(result.get('failed_requests', []))}",
        f"- Cookies: {cookie_count}",
        f"- Session cookies: {session_cookie_count}",
        f"- Persistent cookies: {persistent_cookie_count}",
        f"- Local storage keys: {len(local_storage)}",
        f"- Started: {result.get('scan_start', '-')}",
        f"- Finished: {result.get('scan_end', '-')}",
    ]

    error = result.get("error")
    if error:
        lines.append(f"- Error: {error}")

    return "\n".join(lines)


def save_results(results: list[dict]) -> Path:
    output_dir = Path("test-results")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"scan_results_{timestamp}.json"
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    args = parse_args()
    options = {
        "headless": not args.headed,
        "timeout": args.timeout,
        "wait_until": args.wait_until,
        "ignore_https_errors": not args.strict_https,
        "java_script_enabled": not args.disable_js,
    }

    results = scan_websites(
        args.urls,
        options=options,
        max_concurrency=min(3, len(args.urls)),
    )

    output_path = save_results(results)
    for result in results:
        print(format_overview(result))
    print(f"Saved {len(results)} result(s) to {output_path}")

if __name__ == "__main__":
    main()


