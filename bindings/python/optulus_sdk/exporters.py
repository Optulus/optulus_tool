from __future__ import annotations

import random
import time
from urllib import error, request

from ._telemetry_endpoint import DEFAULT_TELEMETRY_ENDPOINT
from .telemetry import AgentEvent, ExportResult, serialize_event_batch


class HttpTelemetryExporter:
    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_TELEMETRY_ENDPOINT,
        api_key: str | None = None,
        timeout_ms: int = 2_000,
        max_retries: int = 3,
        backoff_base_ms: int = 200,
        sdk_version: str = "0.1.0",
    ) -> None:
        if not endpoint:
            raise ValueError("endpoint is required")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_base_ms <= 0:
            raise ValueError("backoff_base_ms must be positive")

        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout_s = timeout_ms / 1000.0
        self._max_retries = max_retries
        self._backoff_base_ms = backoff_base_ms
        self._sdk_version = sdk_version

    def export(self, events: list[AgentEvent]) -> ExportResult:
        payload = serialize_event_batch(events, sdk_version=self._sdk_version)
        last_error: str | None = None
        status_code: int | None = None
        attempts = 0

        for attempt in range(self._max_retries + 1):
            attempts = attempt + 1
            req = request.Request(
                self._endpoint,
                data=payload,
                method="POST",
                headers=self._headers(),
            )
            try:
                with request.urlopen(req, timeout=self._timeout_s) as response:
                    status_code = getattr(response, "status", None)
                    if status_code is not None and 200 <= status_code < 300:
                        return ExportResult(success=True, attempts=attempts, status_code=status_code)
                    last_error = f"http_status_{status_code}"
            except error.HTTPError as exc:
                status_code = exc.code
                last_error = f"http_error_{exc.code}"
                if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                    return ExportResult(
                        success=False,
                        attempts=attempts,
                        status_code=status_code,
                        error=last_error,
                    )
            except error.URLError as exc:
                last_error = f"url_error_{exc.reason}"
            except TimeoutError:
                last_error = "timeout"

            if attempt < self._max_retries:
                time.sleep(self._backoff_seconds(attempt))

        return ExportResult(
            success=False,
            attempts=attempts,
            status_code=status_code,
            error=last_error or "unknown_error",
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"optulus-sdk/{self._sdk_version}",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _backoff_seconds(self, attempt: int) -> float:
        base = (self._backoff_base_ms / 1000.0) * (2**attempt)
        jitter = random.uniform(0.0, base * 0.1)
        return base + jitter
