FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY browsers/ /tmp/browsers/

# Install Chrome and runtime libraries required by Playwright/Chromium.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gnupg wget xvfb xauth \
    && wget -qO- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-linux.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && if ls /tmp/browsers/google-chrome-stable_*_amd64.deb >/dev/null 2>&1; then \
        apt-get install -y --no-install-recommends /tmp/browsers/google-chrome-stable_*_amd64.deb; \
    else \
        apt-get install -y --no-install-recommends google-chrome-stable; \
    fi \
    && rm -rf /var/lib/apt/lists/* /tmp/browsers

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x /app/docker-entrypoint.sh \
    && useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/test-results \
    && chown -R appuser:appuser /app

# prepare X11 socket dir for Xvfb
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

USER appuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]


