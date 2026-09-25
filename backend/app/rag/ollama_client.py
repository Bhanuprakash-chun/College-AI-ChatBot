"""LLM client supporting both local Ollama and hosted Gemini.

The rest of the application continues to use the OllamaClient class name
for backward compatibility.

Provider is selected using:

    LLM_PROVIDER=ollama
or
    LLM_PROVIDER=gemini
"""

import logging
import threading
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# Exceptions
# ============================================================

class OllamaError(Exception):
    """Base class for every LLM failure mode."""


class OllamaUnavailableError(OllamaError):
    """LLM server/API is unreachable or returned an error."""


class OllamaModelMissingError(OllamaError):
    """Configured local Ollama model has not been pulled."""


# ============================================================
# Generation Result
# ============================================================

@dataclass
class Generation:
    text: str
    model: str
    total_duration_ms: int = 0


# ============================================================
# LLM Client
# ============================================================

class OllamaClient:
    """Unified LLM client for Ollama and Gemini."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ):
        # ----------------------------------------------------
        # Provider
        # ----------------------------------------------------

        self.provider = getattr(
            settings,
            "LLM_PROVIDER",
            "ollama",
        ).lower().strip()

        # ----------------------------------------------------
        # Ollama configuration
        # ----------------------------------------------------

        self.base_url = (
            base_url or settings.OLLAMA_BASE_URL
        ).rstrip("/")

        self.model = (
            model
            or settings.OLLAMA_MODEL
        )

        self.timeout_seconds = (
            timeout_seconds
            or settings.OLLAMA_TIMEOUT_SECONDS
        )

        # ----------------------------------------------------
        # HTTP client
        # ----------------------------------------------------

        self._http: httpx.Client | None = None
        self._http_lock = threading.Lock()

        # ----------------------------------------------------
        # Gemini client
        # ----------------------------------------------------

        self._gemini = None
        self._gemini_lock = threading.Lock()

    # ========================================================
    # HTTP Client
    # ========================================================

    @property
    def http(self) -> httpx.Client:
        """Create one pooled HTTP client for Ollama."""

        if self._http is None:
            with self._http_lock:
                if self._http is None:
                    self._http = httpx.Client(
                        base_url=self.base_url,
                        timeout=self.timeout_seconds,
                    )

        return self._http

    # ========================================================
    # Gemini Client
    # ========================================================

    @property
    def gemini(self):
        """Create the Gemini client lazily."""

        if self._gemini is None:
            with self._gemini_lock:

                if self._gemini is None:

                    try:
                        from google import genai

                        api_key = getattr(
                            settings,
                            "GEMINI_API_KEY",
                            "",
                        ).strip()

                        if not api_key:
                            raise OllamaUnavailableError(
                                "GEMINI_API_KEY is not configured."
                            )

                        self._gemini = genai.Client(
                            api_key=api_key
                        )

                    except OllamaUnavailableError:
                        raise

                    except Exception as exc:
                        raise OllamaUnavailableError(
                            f"Could not initialize Gemini client: {exc}"
                        ) from exc

        return self._gemini

    # ========================================================
    # Close
    # ========================================================

    def close(self) -> None:
        """Close the Ollama HTTP client."""

        if self._http is not None:
            self._http.close()
            self._http = None

    # ========================================================
    # Ollama: List Models
    # ========================================================

    def list_models(self) -> list[str]:
        """Return locally installed Ollama models."""

        try:
            response = self.http.get(
                "/api/tags",
                timeout=5.0,
            )

            response.raise_for_status()

            data = response.json()

        except (httpx.HTTPError, ValueError) as exc:

            raise OllamaUnavailableError(
                f"Could not reach Ollama at "
                f"{self.base_url}: {exc}"
            ) from exc

        return [
            model.get("name", "")
            for model in data.get("models", [])
        ]

    # ========================================================
    # Status
    # ========================================================

    def status(self) -> dict:
        """Return the current LLM status.

        This method does not raise errors because it is used by
        the /health endpoint and admin dashboard.
        """

        # ----------------------------------------------------
        # Gemini
        # ----------------------------------------------------

        if self.provider == "gemini":

            api_key = getattr(
                settings,
                "GEMINI_API_KEY",
                "",
            ).strip()

            model = getattr(
                settings,
                "GEMINI_MODEL",
                "gemini-3.8-flash",
            )

            if not api_key:

                return {
                    "available": False,
                    "provider": "gemini",
                    "model": model,
                    "model_pulled": False,
                    "detail": (
                        "GEMINI_API_KEY is not configured."
                    ),
                }

            return {
                "available": True,
                "provider": "gemini",
                "model": model,
                "model_pulled": True,
                "detail": None,
            }

        # ----------------------------------------------------
        # Ollama
        # ----------------------------------------------------

        try:
            models = self.list_models()

        except OllamaUnavailableError as exc:

            return {
                "available": False,
                "provider": "ollama",
                "model": self.model,
                "model_pulled": False,
                "detail": str(exc),
            }

        pulled = any(
            model == self.model
            or model.split(":")[0]
            == self.model.split(":")[0]
            for model in models
        )

        return {
            "available": True,
            "provider": "ollama",
            "model": self.model,
            "model_pulled": pulled,
            "models": models,
            "detail": (
                None
                if pulled
                else (
                    f"Model '{self.model}' is not pulled. "
                    f"Run: ollama pull {self.model}"
                )
            ),
        }

    # ========================================================
    # Is Available
    # ========================================================

    def is_available(self) -> bool:
        """Return whether the configured LLM is available."""

        return self.status().get(
            "available",
            False,
        )

    # ========================================================
    # Warm Up
    # ========================================================

    def warm_up(
        self,
        prompt_prefix: str = "",
    ) -> bool:
        """Warm up the configured LLM.

        Gemini is hosted, so there is no local model-loading step.
        """

        # Gemini does not need local warm-up.
        if self.provider == "gemini":
            return bool(
                getattr(
                    settings,
                    "GEMINI_API_KEY",
                    "",
                ).strip()
            )

        # ----------------------------------------------------
        # Ollama warm-up
        # ----------------------------------------------------

        payload = {
            "model": self.model,
            "prompt": prompt_prefix,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {
                "num_predict": 1,
                "temperature": settings.OLLAMA_TEMPERATURE,
            },
        }

        try:

            response = self.http.post(
                "/api/generate",
                json=payload,
                timeout=max(
                    self.timeout_seconds,
                    300,
                ),
            )

            return response.status_code == 200

        except httpx.HTTPError as exc:

            logger.info(
                "Ollama warm-up skipped: %s",
                exc,
            )

            return False

    # ========================================================
    # Generate
    # ========================================================

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
    ) -> Generation:
        """Generate a response using the configured provider."""

        if self.provider == "gemini":

            return self._generate_gemini(
                prompt=prompt,
                temperature=temperature,
            )

        return self._generate_ollama(
            prompt=prompt,
            temperature=temperature,
        )

    # ========================================================
    # Gemini Generation
    # ========================================================

    def _generate_gemini(
        self,
        prompt: str,
        temperature: float | None = None,
    ) -> Generation:
        """Generate text using Gemini."""

        model = getattr(
            settings,
            "GEMINI_MODEL",
            "gemini-3.6-flash",
        )

        selected_temperature = (
            settings.OLLAMA_TEMPERATURE
            if temperature is None
            else temperature
        )

        try:

            from google.genai import types

            client = self.gemini

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=1024,
                ),
            )

            text = (
                getattr(
                    response,
                    "text",
                    None,
                )
                or ""
            ).strip()

            if not text:

                raise OllamaUnavailableError(
                    "Gemini returned an empty response."
                )

            return Generation(
                text=text,
                model=model,
                total_duration_ms=0,
            )

        except OllamaUnavailableError:
            raise

        except Exception as exc:

            logger.exception(
                "Gemini generation failed."
            )

            raise OllamaUnavailableError(
                f"Gemini generation failed: {exc}"
            ) from exc

    # ========================================================
    # Ollama Generation
    # ========================================================

    def _generate_ollama(
        self,
        prompt: str,
        temperature: float | None = None,
    ) -> Generation:
        """Generate text using local Ollama."""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": (
                    settings.OLLAMA_TEMPERATURE
                    if temperature is None
                    else temperature
                ),
            },
        }

        # ----------------------------------------------------
        # Request
        # ----------------------------------------------------

        try:

            response = self.http.post(
                "/api/generate",
                json=payload,
                timeout=self.timeout_seconds,
            )

        except httpx.TimeoutException as exc:

            raise OllamaUnavailableError(
                f"Ollama timed out after "
                f"{self.timeout_seconds}s generating "
                f"with '{self.model}'."
            ) from exc

        except httpx.HTTPError as exc:

            raise OllamaUnavailableError(
                f"Could not reach Ollama at "
                f"{self.base_url}. "
                f"Is `ollama serve` running? ({exc})"
            ) from exc

        # ----------------------------------------------------
        # HTTP errors
        # ----------------------------------------------------

        if response.status_code == 404:

            raise OllamaModelMissingError(
                f"Ollama has no model named "
                f"'{self.model}'. "
                f"Run: ollama pull {self.model}"
            )

        if response.status_code >= 400:

            raise OllamaUnavailableError(
                f"Ollama returned HTTP "
                f"{response.status_code}: "
                f"{response.text[:200]}"
            )

        # ----------------------------------------------------
        # JSON response
        # ----------------------------------------------------

        try:

            data = response.json()

        except ValueError as exc:

            raise OllamaUnavailableError(
                "Ollama returned a non-JSON response."
            ) from exc

        # ----------------------------------------------------
        # Generation result
        # ----------------------------------------------------

        return Generation(
            text=(
                data.get("response")
                or ""
            ).strip(),

            model=self.model,

            total_duration_ms=int(
                data.get(
                    "total_duration",
                    0,
                )
                / 1_000_000
            ),
        )


# ============================================================
# Global Client
# ============================================================

ollama_client = OllamaClient()