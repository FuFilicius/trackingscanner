# Website Scanner

A Playwright-based scanner that visits one or more URLs and writes timestamped JSON scan results.

It captures request/response traffic, failed requests, cookies, local storage, and tracking-related signals through modular extractors.
The scanner also attempts to accept cookie/CMP banners and stores extraction results from both phases: before and after consent.

## How it works

1. `main.py` parses CLI args and calls `trackingscanner.scan(...)`.
2. `scan(...)` starts a process pool via `ScanMaster`/`ScanWorker`.
3. Each worker reuses one browser instance and runs `WebsiteScanner.scan_one_url_with_browser(...)` per queued URL.
4. For each URL, extractors run once before consent interaction and once after attempting to click an accept action.
5. Results are returned in the same order as input URLs and saved to `test-results/scan_results_<timestamp>.json`.

## Project structure

- `main.py` - CLI entrypoint; parses args, runs scans, prints per-site overview, writes JSON output.
- `scanner.py` - high-level orchestration for multi-URL scans; queues jobs and collects worker results.
- `scan_master.py` - manages worker processes and task/result queues.
- `scan_worker.py` - worker loop that consumes jobs and executes scans.
- `scan_job.py` - immutable scan job model (`job_id`, `url`) plus execute helper.
- `trackingscanner/` - package API for integrating from another Python project.
- `website_scanner.py` - core single-URL scan lifecycle (browser context/page setup, navigation, finalize).
- `scanner_tools/network.py` - network event logging and custom network-idle waiting.
- `scanner_tools/extractors.py` - extractor registration and injected JavaScript setup.
- `scanner_tools/finalize.py` - final response/storage collection and result finalization.
- `extractors/` - feature extractors (cookies, trackers, third parties, pixels, session recorders, fingerprinting, failed requests, etc.).
- `utils.py` - shared dataclasses and helpers for URL parsing and result serialization.
- `resources/` - static detection resources (`easylist.txt`, `easyprivacy.txt`, `session_recorders.json`, `accept_words.txt`).
- `test-results/` - output directory for generated scan result JSON files.
- `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh` - containerized execution.

## Requirements

- Python 3.12+
- Google Chrome installed locally (scanner launches Playwright Chromium with `channel="chrome"`)
- Dependencies from `requirements.txt`

## Run locally (without Docker)

### 1) Set up environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Run scans

Single URL:

```powershell
python main.py https://example.com
```

Multiple URLs:

```powershell
python main.py https://example.com https://example.org
```

CLI options:

- `--headed` - run with visible browser window
- `--timeout <ms>` - navigation timeout in milliseconds (default: `30000`)
- `--wait-until <state>` - one of `load`, `domcontentloaded`, `networkidle`, `commit` (default: `domcontentloaded`)
- `--strict-https` - do not ignore TLS certificate errors
- `--disable-js` - disable JavaScript in the browser context
- `--without-cmp` (alias: `--without-cmp-interaction`) - skip cookie/CMP auto-accept interaction
- `--log-scan-timings` - print timing logs for CMP interaction and extractor steps

Example:

```powershell
python main.py https://example.com --timeout 45000 --wait-until networkidle
```

Disable CMP interaction:

```powershell
python main.py https://example.com --without-cmp
```

Enable step timing logs:

```powershell
python main.py https://example.com --log-scan-timings
```

## Use as a module in another project

Install in editable mode from your other project environment:

```powershell
pip install -e C:\path\to\trackingscanner
```

Run a full batch scan:

```python
from trackingscanner import scan

results = scan(
    ["https://example.com", "https://example.org"],
    options={
        "headless": True,
        "timeout": 30000,
        "wait_until": "domcontentloaded",
        "ignore_https_errors": True,
        "java_script_enabled": True,
    },
    max_concurrency=2,
)
```

Manage workers and queue URLs incrementally:

```python
from trackingscanner import ScanController

with ScanController(worker_count=2, options={"headless": True}) as scanner:
    job_ids = scanner.queue_urls(
        [
            "https://example.com",
            "https://example.org",
        ]
    )

    while scanner.pending_results() > 0:
        item = scanner.get_result(timeout=1.0)
        if item is None:
            continue
        job_id, result = item
        print(job_id, result.get("site_url"), result.get("reachable"))
```

Additional programmatic scan options:

- `cmp_auto_accept` (default: `True`) - enable/disable CMP auto-accept interaction.
- `cmp_pre_click_wait_ms` (default: `750`) - wait after initial load before trying consent interaction.
- `cmp_click_timeout_ms` (default: `1000`) - per-click timeout while trying candidate accept elements.
- `cmp_wait_after_click_ms` (default: `1000`) - wait after a successful click to allow additional tracking activity.
- `log_scan_timings` (default: `False`) - print timing logs for `cmp_try_accept`, `extract_before`, and (if applicable) `extract_after`.
- CMP matching uses normalized exact text matching from `accept_words.txt` (not substring matching).

## Concurrency behavior

- The CLI currently scans with up to 3 worker processes: `min(3, len(urls))`.
- This cap is set in `main.py` (not currently a CLI flag).
- If interrupted (Ctrl+C), unfinished URLs are returned as failed results with error `scan interrupted`.
- If workers stop unexpectedly, unfinished URLs are marked `scan did not complete`.

## Run with Docker

Build image:

```powershell
docker compose build
```

Run scanner (URLs/flags are forwarded to `main.py`):

```powershell
docker compose run --rm scanner https://example.com
```

Example with multiple URLs and flags:

```powershell
docker compose run --rm scanner https://example.com https://example.org --timeout 45000 --wait-until networkidle
```

## Output

Each run writes a timestamped JSON file to `test-results/`, for example:

- `test-results/scan_results_20260331_210400.json`

Top-level result keys include:

- `site_url`, `scan_start`, `scan_end`, `reachable`
- `cmp` (interaction metadata: clicked text/selector/frame/strategy and matched accept word)
- `before_accept` (full extractor output before CMP interaction) and `after_accept` (only populated when an accept click succeeds)
- `final_url`, `final_response`
- `requests`, `failed_requests`, `cookies`
- extractor-specific fields (for trackers, third parties, pixels, session recorders, fingerprinting, etc.)
- optional `error` when navigation/scan fails
- optional `network_idle_max_wait_exceeded` when custom idle wait reaches max timeout

The CLI also prints a short per-site overview to stdout.

## Notes

- If you place a Chrome package like `browsers/google-chrome-stable_<version>_amd64.deb` in the repo, the Docker build installs that file first.
- The Chrome package used for testing is `google-chrome-stable_144.0.7559.132-1_amd64.deb`.
- If no local `.deb` exists, the Docker build installs `google-chrome-stable` from apt.
- In Docker, scans run through `xvfb` (`docker-entrypoint.sh`).
- The default compose setup mounts host `./test-results` to container `/app/test-results`, so results persist on your machine.

## Credits

The extractor logic is adapted from work by [The Markup Blacklight](https://themarkup.org/blacklight) and [privacyscanner-master](https://github.com/ronghaopan/privacyscanner-master).
The consent acceptance word list (`resources/accept_words.txt`) is based on [marty90/priv-accept](https://github.com/marty90/priv-accept).
