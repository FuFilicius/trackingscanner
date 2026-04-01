# Website Scanner

A Playwright-based scanner that visits one or more URLs and writes timestamped JSON scan results.

It captures request/response traffic, failed requests, cookies, local storage, and tracking-related signals through modular extractors.

## How it works

1. `main.py` parses CLI args and calls `scan_websites(...)`.
2. `scan_websites(...)` starts a process pool via `ScanMaster`/`ScanWorker`.
3. Each worker reuses one browser instance and runs `WebsiteScanner.scan_one_url_with_browser(...)` per queued URL.
4. Results are returned in the same order as input URLs and saved to `test-results/scan_results_<timestamp>.json`.

## Project structure

- `main.py` - CLI entrypoint; parses args, runs scans, prints per-site overview, writes JSON output.
- `scanner.py` - high-level orchestration for multi-URL scans; queues jobs and collects worker results.
- `scan_master.py` - manages worker processes and task/result queues.
- `scan_worker.py` - worker loop that consumes jobs and executes scans.
- `scan_job.py` - immutable scan job model (`job_id`, `url`) plus execute helper.
- `website_scanner.py` - core single-URL scan lifecycle (browser context/page setup, navigation, finalize).
- `scanner_tools/network.py` - network event logging and custom network-idle waiting.
- `scanner_tools/extractors.py` - extractor registration and injected JavaScript setup.
- `scanner_tools/finalize.py` - final response/storage collection and result finalization.
- `extractors/` - feature extractors (cookies, trackers, third parties, pixels, session recorders, fingerprinting, failed requests, etc.).
- `utils.py` - shared dataclasses and helpers for URL parsing and result serialization.
- `resources/` - static detection resources (`easylist.txt`, `easyprivacy.txt`, `session_recorders.json`).
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

Example:

```powershell
python main.py https://example.com --timeout 45000 --wait-until networkidle
```

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
- `final_url`, `final_response`
- `requests`, `failed_requests`, `cookies`
- extractor-specific fields (for trackers, third parties, pixels, session recorders, fingerprinting, etc.)
- optional `error` when navigation/scan fails
- optional `network_idle_max_wait_exceeded` when custom idle wait reaches max timeout

The CLI also prints a short per-site overview to stdout.

## Notes

- If you place a Chrome package like `browsers/google-chrome-stable_<version>_amd64.deb` in the repo, the Docker build installs that file first.
- If no local `.deb` exists, the Docker build installs `google-chrome-stable` from apt.
- In Docker, scans run through `xvfb` (`docker-entrypoint.sh`).
- The default compose setup mounts host `./test-results` to container `/app/test-results`, so results persist on your machine.

## Credits

The extractor logic is adapted from work by [The Markup Blacklight](https://themarkup.org/blacklight) and [privacyscanner-master](https://github.com/ronghaopan/privacyscanner-master).
