# Website Scanner

A Playwright-based website scanner that visits one or more URLs and writes scan results to JSON files.

The scanner collects network activity, cookies, storage data, and tracking-related signals through modular extractors.

## Project structure

- `main.py` - CLI entrypoint; parses arguments, runs scans, prints per-site overview, saves JSON to `test-results/`.
- `scanner.py` - Core scanner orchestration (`WebsiteScanner`) and Playwright browser/context lifecycle.
- `utils.py` - Shared dataclasses and helpers for request/response/cookie/storage normalization.
- `extractors/` - Feature extractors (cookies, trackers, third parties, pixels, session recorders, fingerprinting, failed requests, etc.).
- `scanner_tools/` - Scanner internals for network logging, extractor wiring, and final result assembly.
- `resources/` - Static detection resources (`easylist.txt`, `easyprivacy.txt`, `session_recorders.json`).
- `test-results/` - Output directory for generated scan result JSON files.
- `Dockerfile` - Container image definition with Google Chrome and runtime dependencies.
- `docker-compose.yml` - Compose service for building/running scanner with `test-results` volume mapping.
- `docker-entrypoint.sh` - Container entrypoint using `xvfb-run` to execute `python main.py`.

## Requirements

- Python 3.12+
- Google Chrome installed locally (the scanner launches Playwright Chromium with `channel="chrome"`)
- Dependencies from `requirements.txt`

## Run without Docker (local)

### 1) Set up environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Run a scan

```powershell
python main.py https://example.com
```

Scan multiple sites:

```powershell
python main.py https://example.com https://example.org
```

Useful options:

- `--headed` - show browser window (headless disabled)
- `--timeout 45000` - navigation timeout in milliseconds
- `--wait-until load|domcontentloaded|networkidle|commit`
- `--strict-https` - do not ignore TLS certificate errors
- `--disable-js` - disable JavaScript in the browser context

Example with options:

```powershell
python main.py https://example.com --timeout 45000 --wait-until networkidle
```

## Run with Docker

### Docker Compose

Build image:

```powershell
docker compose build
```

Run scanner (pass URLs and flags directly; they are forwarded to `main.py`):

```powershell
docker compose run --rm scanner https://example.com
```

Example with multiple URLs and flags:

```powershell
docker compose run --rm scanner https://example.com https://example.org --timeout 45000 --wait-until networkidle
```

## Output

Each run writes a timestamped JSON file to `test-results/`, for example:

- `test-results/scan_results_20260326_212135.json`

The CLI also prints a short per-site overview to stdout.

## Notes

- If you place a Chrome package like `browsers/google-chrome-stable_<version>_amd64.deb` in the repo, the Docker build installs that file first.
- If no local `.deb` exists, the Docker build installs the latest `google-chrome-stable` from apt.
- In Docker, scans run through `xvfb` inside the container (`docker-entrypoint.sh`).
- The default compose setup mounts host `./test-results` to container `/app/test-results`, so results persist on your machine.

