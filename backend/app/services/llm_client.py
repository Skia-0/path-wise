import os
import sys
import time
import logging
from typing import Dict, List, Optional, Set, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("pathwise")

# ---------------------------------------------------------------------------
# Provider configuration (set these in backend/.env)
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Tried in order. Models verified working for this key come first.
# GEMINI_MODEL in .env, if set, is tried first.
_custom_gemini_model = os.getenv("GEMINI_MODEL", "").strip()
_default_gemini_models = [
    "gemini-flash-lite-latest",   # verified WORKS
    "gemma-4-31b-it",             # verified WORKS
    "gemma-4-26b-a4b-it",         # verified WORKS
    "gemini-flash-latest",        # 503 busy during test, may recover
    "gemini-pro-latest",          # 429 quota during test, may recover
]
GEMINI_MODELS: List[str] = (
    ([_custom_gemini_model] if _custom_gemini_model else [])
    + [m for m in _default_gemini_models if m != _custom_gemini_model]
)

# Waits (seconds) between retries of the SAME model when Google returns 503 busy.
# 429 (quota) is not retried, because waiting does not help within a short window.
GEMINI_503_RETRY_DELAYS = [2, 5]

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

REQUEST_TIMEOUT = 60.0

_genai_client = None
_dead_gemini_models: Set[str] = set()   # models that returned 404 in this process
_disabled_providers: Set[str] = set()   # providers disabled after auth or import failures


# ---------------------------------------------------------------------------
# Gemini (google-genai SDK)
# ---------------------------------------------------------------------------
def _get_gemini_client():
    """Creates the google-genai client once. Returns None if unavailable."""
    global _genai_client
    if "gemini" in _disabled_providers or not GEMINI_API_KEY:
        return None
    if _genai_client is None:
        try:
            from google import genai
            _genai_client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception as e:
            logger.error(
                f"Gemini SDK failed to load under interpreter {sys.executable}. "
                f"Run 'python -m pip install google-genai' in this venv and restart. Error: {e}"
            )
            _disabled_providers.add("gemini")
            return None
    return _genai_client


def _call_gemini(prompt: str) -> Optional[str]:
    """Tries each Gemini model in order. Retries 503 on the same model. Returns text or None."""
    client = _get_gemini_client()
    if client is None:
        return None

    for model_name in GEMINI_MODELS:
        if model_name in _dead_gemini_models:
            continue

        for attempt in range(len(GEMINI_503_RETRY_DELAYS) + 1):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                text = getattr(response, "text", None)
                if text:
                    logger.info(f"Gemini responded using model: {model_name}")
                    return text
                break  # empty reply: move to next model

            except Exception as e:
                msg = str(e)

                if "NOT_FOUND" in msg or " 404" in msg:
                    _dead_gemini_models.add(model_name)
                    logger.warning(f"Gemini model unavailable for this key, skipping: {model_name}")
                    break

                if "API_KEY_INVALID" in msg or "PERMISSION_DENIED" in msg:
                    _disabled_providers.add("gemini")
                    logger.error("Gemini rejected GEMINI_API_KEY. Fix the key in .env and restart.")
                    return None

                if ("503" in msg or "UNAVAILABLE" in msg) and attempt < len(GEMINI_503_RETRY_DELAYS):
                    delay = GEMINI_503_RETRY_DELAYS[attempt]
                    logger.warning(f"Gemini {model_name} busy (503). Retrying in {delay}s.")
                    time.sleep(delay)
                    continue

                # 429 (quota) and anything else: skip this model for this call
                logger.warning(f"Gemini call failed for {model_name}: {msg[:200]}")
                break

    return None


# ---------------------------------------------------------------------------
# OpenAI-compatible providers (Groq, OpenRouter). Optional. Skipped if no key.
# ---------------------------------------------------------------------------
def _call_openai_compatible(
    provider: str,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Calls an OpenAI-style chat completions endpoint. Returns text or None."""
    if not api_key or provider in _disabled_providers:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        resp = httpx.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (401, 403):
            _disabled_providers.add(provider)
            logger.error(f"{provider} rejected its API key (HTTP {resp.status_code}). Provider disabled until restart.")
            return None
        if resp.status_code == 429:
            logger.warning(f"{provider} rate limit reached.")
            return None

        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        if text:
            logger.info(f"{provider} responded using model: {model}")
            return text
    except Exception as e:
        logger.warning(f"{provider} call failed: {str(e)[:300]}")
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def generate_with_fallback(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Tries Gemini first, then Groq, then OpenRouter.
    Returns (text, provider_name), or (None, None) if every provider fails.
    """
    text = _call_gemini(prompt)
    if text:
        return text, "gemini"

    text = _call_openai_compatible("groq", GROQ_URL, GROQ_API_KEY, GROQ_MODEL, prompt)
    if text:
        return text, "groq"

    text = _call_openai_compatible(
        "openrouter",
        OPENROUTER_URL,
        OPENROUTER_API_KEY,
        OPENROUTER_MODEL,
        prompt,
        extra_headers={"X-Title": "Path-Wise"},
    )
    if text:
        return text, "openrouter"

    logger.warning("All AI providers failed. Using rule-based fallback.")
    return None, None


def provider_status() -> Dict[str, bool]:
    """Reports which providers are configured and not disabled."""
    return {
        "gemini": bool(GEMINI_API_KEY) and "gemini" not in _disabled_providers,
        "groq": bool(GROQ_API_KEY) and "groq" not in _disabled_providers,
        "openrouter": bool(OPENROUTER_API_KEY) and "openrouter" not in _disabled_providers,
    }