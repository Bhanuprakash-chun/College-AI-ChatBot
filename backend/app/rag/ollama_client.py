"""Client for a local Ollama server (default model llama3.2:3b)."""

import logging
import threading
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Base class for every Ollama failure mode."""


class OllamaUnavailableError(OllamaError):
    """Server unreachable, timed out, or returned an error status."""


class OllamaModelMissingError(OllamaError):
    """Server is up but the configured model has not been pulled."""


@dataclass
class Generation:
    text: str
    model: str
    total_duration_ms: int = 0


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout_seconds = timeout_seconds or settings.OLLAMA_TIMEOUT_SECONDS
        self._http: httpx.Client | None = None
        self._http_lock = threading.Lock()

    @property
    def http(self) -> httpx.Client:
        """One pooled, keep-alive client per Ollama client.

        Building an httpx.Client loads the TLS certificate bundle (~300 ms), so
        creating one per request added that cost to every answer. httpx.Client
        is thread-safe; timeouts are set per request below.
        """
        if self._http is None:
            with self._http_lock:
                if self._http is None:
                    self._http = httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds)
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def list_models(self) -> list[str]:
        try:
            response = self.http.get("/api/tags", timeout=5.0)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaUnavailableError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
        return [m.get("name", "") for m in data.get("models", [])]

    def status(self) -> dict:
        """Non-throwing health probe used by /health and the admin dashboard."""
        try:
            models = self.list_models()
        except OllamaUnavailableError as exc:
            return {
                "available": False,
                "model": self.model,
                "model_pulled": False,
                "detail": str(exc),
            }

        # Ollama reports "llama3.2:3b"; accept a bare "llama3.2" config too.
        pulled = any(m == self.model or m.split(":")[0] == self.model.split(":")[0] for m in models)
        return {
            "available": True,
            "model": self.model,
            "model_pulled": pulled,
            "models": models,
            "detail": None if pulled else f"Model '{self.model}' is not pulled. Run: ollama pull {self.model}",
        }

    def warm_up(self, prompt_prefix: str = "") -> bool:
        """Load the model into memory and, given the real instruction prefix,
        let Ollama cache its evaluation. Every answer's prompt starts with the
        same instructions, so the first student question then skips both the
        model load and most of the prompt processing. Generates one token.
        """
        payload = {
            "model": self.model,
            "prompt": prompt_prefix,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {"num_predict": 1, "temperature": settings.OLLAMA_TEMPERATURE},
        }
        try:
            response = self.http.post(
                "/api/generate", json=payload, timeout=max(self.timeout_seconds, 300)
            )
            return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.info("Ollama warm-up skipped: %s", exc)
            return False

    def is_available(self) -> bool:
        return self.status().get("available", False)

    def generate(self, prompt: str, temperature: float | None = None) -> Generation:
        """Generate a completion. Raises OllamaError subclasses on failure."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE if temperature is None else temperature,
            },
        }
        try:
            response = self.http.post("/api/generate", json=payload, timeout=self.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise OllamaUnavailableError(
                f"Ollama timed out after {self.timeout_seconds}s generating with '{self.model}'."
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running? ({exc})"
            ) from exc

        if response.status_code == 404:
            raise OllamaModelMissingError(
                f"Ollama has no model named '{self.model}'. Run: ollama pull {self.model}"
            )
        if response.status_code >= 400:
            raise OllamaUnavailableError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise OllamaUnavailableError("Ollama returned a non-JSON response.") from exc

        return Generation(
            text=(data.get("response") or "").strip(),
            model=self.model,
            total_duration_ms=int(data.get("total_duration", 0) / 1_000_000),
        )


ollama_client = OllamaClient()
