"""One entry point for LLM calls: generate(system, user, model=None, provider=None, ...).

Settings come from .env (see .env.example):
    LLM_PROVIDER=openai                      provider for answers
    OPENAI_API_KEY=...
    LLM_MODEL=gpt-5.4-mini-2026-03-17
    LLM_MODEL_CHEAP=gpt-5.4-nano-2026-03-17
    JUDGE_PROVIDER=openai                    provider for the eval judges (eval/judges.py)
    JUDGE_MODEL=gpt-5.4-nano-2026-03-17      (gemini / gemini-3.5-flash also works; free tier is 20/day)
    GEMINI_API_KEY=...
    GEMINI_RPM=15                            free-tier requests per minute (calls are throttled)

The provider is chosen per call (answers on LLM_PROVIDER, judges on JUDGE_PROVIDER). To add a
provider ("anthropic", "ollama"), write a _call_<name>(system, user, model, temperature,
json_schema) function that returns (text, input_tokens, output_tokens, reasoning_tokens) and
register it in PROVIDERS. Nothing outside this file needs to change.

Usage:
    python rag/llm.py --check     # check that the configured models exist for the keys
"""
import os
import random
import re
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
MODEL = os.getenv("LLM_MODEL", "gpt-5.4-mini-2026-03-17")
MODEL_CHEAP = os.getenv("LLM_MODEL_CHEAP", "gpt-5.4-nano-2026-03-17")
# evaluation only: a different model family from the one it grades
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "openai").lower()
MODEL_JUDGE = os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL_JUDGE", "gpt-5.4-nano-2026-03-17")

# USD per million tokens: (input, output). Reasoning / thinking tokens are billed as output.
PRICES = {
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
}
FREE_PROVIDERS = {"gemini"} if os.getenv("GEMINI_FREE_TIER", "1") == "1" else set()  # free tier: $0

MAX_RETRIES = 5


def estimate_cost(model, input_tokens, output_tokens, provider=None):
    """USD estimate, or None when the model has no entry in PRICES."""
    if (provider or PROVIDER) in FREE_PROVIDERS:
        return 0.0
    price = PRICES.get(model) or PRICES.get(re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model))  # dated snapshots
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


MAX_WAIT = 120  # seconds; a longer server-requested wait means a daily quota is used up


class QuotaExhausted(RuntimeError):
    """The provider asked to wait longer than MAX_WAIT (e.g. a free-tier daily quota)."""


def _with_backoff(fn, is_rate_limit, retries=MAX_RETRIES, retry_after=None):
    """Call fn(); on a rate-limit error wait 1, 2, 4, ... s (plus jitter, at most MAX_WAIT), or the
    delay the server asks for (retry_after(e)), and try again. If the server asks for more than
    MAX_WAIT, raise QuotaExhausted instead of sleeping for hours."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            if not is_rate_limit(e) or attempt == retries:
                raise
            asked = retry_after(e) if retry_after else None
            if asked and asked > MAX_WAIT:
                raise QuotaExhausted(f"provider asks to wait {asked:.0f}s (quota used up?): {str(e)[:200]}") from e
            delay = min(asked or 2 ** attempt, MAX_WAIT)
            delay += random.random()
            code = getattr(e, "code", None) or getattr(e, "status_code", None) or type(e).__name__
            print(f"[llm] rate limited / unavailable ({code}), retrying in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)


# ---- OpenAI -------------------------------------------------------------------------------

# Lowest effort first; older models (gpt-5) don't accept "none", non-reasoning models accept none
OPENAI_EFFORTS = ["none", "minimal", "low", None]


@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI
    return OpenAI()  # reads OPENAI_API_KEY from the environment


_openai_effort = {}  # model -> lowest effort that model accepted


def _call_openai(system, user, model, temperature=None, json_schema=None):
    import openai

    client = _openai_client()
    efforts = [_openai_effort[model]] if model in _openai_effort else OPENAI_EFFORTS
    for effort in efforts:
        kwargs = {"model": model, "instructions": system, "input": user}
        if effort is not None:
            kwargs["reasoning"] = {"effort": effort}
        if temperature is not None:
            kwargs["temperature"] = temperature  # GPT-5.x accepts this only with effort "none"
        if json_schema is not None:
            kwargs["text"] = {"format": {"type": "json_schema", "name": "result", "schema": json_schema,
                                         "strict": True}}
        try:
            resp = _with_backoff(lambda: client.responses.create(**kwargs),
                                 lambda e: isinstance(e, openai.RateLimitError))
        except openai.BadRequestError as e:
            if "reasoning" in str(e).lower() and effort != efforts[-1]:
                continue  # effort level not supported by this model, try the next one
            raise
        _openai_effort[model] = effort
        u = resp.usage
        reasoning = getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0
        return resp.output_text, u.input_tokens, u.output_tokens, reasoning


def _models_openai():
    return {m.id for m in _openai_client().models.list()}


# ---- Gemini (Google Gen AI SDK) -----------------------------------------------------------

GEMINI_MIN_INTERVAL = 60 / float(os.getenv("GEMINI_RPM", "15")) + 0.2  # seconds between requests
GEMINI_RETRIES = 8
_gemini_lock = threading.Lock()
_gemini_last = [0.0]


@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _gemini_throttle():
    """Free tier allows ~GEMINI_RPM requests per minute: space requests out across threads."""
    with _gemini_lock:
        wait = _gemini_last[0] + GEMINI_MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _gemini_last[0] = time.monotonic()


def _gemini_rate_limited(e):
    from google.genai import errors
    return isinstance(e, errors.APIError) and (
        getattr(e, "code", None) in (429, 503) or "RESOURCE_EXHAUSTED" in str(e) or "UNAVAILABLE" in str(e))


def _gemini_retry_after(e):
    m = re.search(r"retry(?:Delay| in)['\"]?:?\s*['\"]?(\d+(?:\.\d+)?)s", str(e))
    return float(m.group(1)) if m else None


def _call_gemini(system, user, model, temperature=None, json_schema=None):
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        thinking_config=types.ThinkingConfig(thinking_level="minimal"),  # lowest thinking level
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        **({"response_mime_type": "application/json", "response_json_schema": json_schema} if json_schema else {}),
    )

    def call():
        _gemini_throttle()
        return _gemini_client().models.generate_content(model=model, contents=user, config=config)

    resp = _with_backoff(call, _gemini_rate_limited, retries=GEMINI_RETRIES, retry_after=_gemini_retry_after)
    u = resp.usage_metadata
    thoughts = u.thoughts_token_count or 0
    return resp.text, u.prompt_token_count or 0, (u.candidates_token_count or 0) + thoughts, thoughts


def _models_gemini():
    return {m.name.split("/")[-1] for m in _gemini_client().models.list()}


# ---- registry -----------------------------------------------------------------------------

PROVIDERS = {
    "openai": {"call": _call_openai, "models": _models_openai},
    "gemini": {"call": _call_gemini, "models": _models_gemini},
}


def _provider(name):
    if name not in PROVIDERS:
        raise ValueError(f"provider {name!r} is not implemented; choose from {sorted(PROVIDERS)}")
    return PROVIDERS[name]


def generate(system, user, model=None, temperature=None, json_schema=None, provider=None):
    """Returns {text, model, provider, input_tokens, output_tokens, reasoning_tokens, cost_usd}.
    output_tokens includes reasoning_tokens (that is how they are billed).
    json_schema: a JSON Schema the reply must follow (text is then a JSON string).
    provider: defaults to LLM_PROVIDER (the eval judges pass JUDGE_PROVIDER)."""
    provider = (provider or PROVIDER).lower()
    model = model or MODEL
    start = time.perf_counter()
    text, tin, tout, treason = _provider(provider)["call"](system, user, model, temperature, json_schema)
    return {
        "text": text,
        "model": model,
        "provider": provider,
        "input_tokens": tin,
        "output_tokens": tout,
        "reasoning_tokens": treason,
        "cost_usd": estimate_cost(model, tin, tout, provider),
        "seconds": round(time.perf_counter() - start, 2),
    }


def check_models():
    """Print whether the configured models exist for the keys; list alternatives if not."""
    wanted = [("LLM_MODEL", PROVIDER, MODEL), ("LLM_MODEL_CHEAP", PROVIDER, MODEL_CHEAP),
              ("JUDGE_MODEL", JUDGE_PROVIDER, MODEL_JUDGE)]
    for var, provider, name in wanted:
        try:
            available = _provider(provider)["models"]()
        except Exception as e:  # missing key etc.
            print(f"{var}={name} ({provider}): cannot list models ({type(e).__name__}: {str(e)[:80]})")
            continue
        ok = name in available
        print(f"{var}={name} ({provider}): {'available' if ok else 'NOT available'}")
        if not ok:
            hint = sorted(m for m in available if "flash" in m) if provider == "gemini" else sorted(available)
            print("  available:", ", ".join(hint))


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_models()
    else:
        r = generate("Reply in one short sentence.", " ".join(sys.argv[1:]) or "Say hello.")
        print(r)
