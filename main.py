from __future__ import annotations

import argparse
import json

from scanner import scan_website


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a website scan with Playwright.")
    parser.add_argument(
        "url",
        help="Target URL to scan, e.g. https://example.com"
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

    lines = [
        "Scan overview",
        f"- Site URL: {result.get('site_url', '-')}",
        f"- Final URL: {result.get('final_url', '-')}",
        f"- Reachable: {result.get('reachable', False)}",
        f"- Status: {final_response.get('status', '-')}",
        f"- Requests: {len(result.get('requests', []))}",
        f"- Failed requests: {len(result.get('failed_requests', []))}",
        f"- Cookies: {len(result.get('cookies', []))}",
        f"- Local storage keys: {len(local_storage)}",
        f"- Started: {result.get('scan_start', '-')}",
        f"- Finished: {result.get('scan_end', '-')}",
    ]

    error = result.get("error")
    if error:
        lines.append(f"- Error: {error}")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    options = {
        "headless": not args.headed,
        "timeout": args.timeout,
        "wait_until": args.wait_until,
        "ignore_https_errors": not args.strict_https,
        "java_script_enabled": not args.disable_js,
    }

    result = scan_website(args.url, options=options)
    print(format_overview(result))
    print(json.dumps(result['facebook_pixel'], indent=2))
    print(json.dumps(result['third_parties'], indent=2))
    # print(json.dumps(result["cookies"], indent=2))
    # print(json.dumps(result["requests"], indent=2))


if __name__ == "__main__":
    main()


