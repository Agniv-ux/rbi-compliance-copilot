"""One entry point for LLM calls: generate(system, user, model=None).

Settings come from .env (see .env.example):
    LLM_PROVIDER=openai
    OPENAI_API_KEY=...
    LLM_MODEL=gpt-5.4-mini
    LLM_MODEL_CHEAP=gpt-5.4-nano

To add a provider ("gemini", "anthropic", "ollama"), write a _call_<name>(system, user, model)
function(system, user, model, temperature, json_schema) that returns
(text, input_tokens, output_tokens, reasoning_tokens) and register it in
PROVIDERS. Nothing outside this file needs to change.

Usage:
    python rag/llm.py --check     # list which models in PRICES the key can use
"""
import os
import random
import sys
import time
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
MODEL = os.getenv("LLM_MODEL", "gpt-5.4-mini")
MODEL_CHEAP = os.getenv("LLM_MODEL_CHEAP", "gpt-5.4-nano")
MODEL_JUDGE = os.getenv("LLM_MODEL_JUDGE", "gpt-5.4")  # evaluation only: bigger than the models it grades

# USD per million tokens: (input, output). Reasoning tokens are billed as output.
PRICES = {
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
}

MAX_RETRIES = 5


def estimate_cost(model, input_tokens, output_tokens):
    """USD estimate, or None when the model has no entry in PRICES."""
    price = PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


def _with_backoff(fn, is_rate_limit):
    """Call fn(); on a rate-limit error wait 1, 2, 4, ... s (plus jitter) and try again."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if not is_rate_limit(e) or attempt == MAX_RETRIES:
                raise
            delay = 2 ** attempt + random.random()
            print(f"[llm] rate limited, retrying in {delay:.1f}s", file=sys.stderr)
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


# ---- registry -----------------------------------------------------------------------------

PROVIDERS = {
    "openai": {"call": _call_openai, "models": _models_openai},
}


def _provider():
    if PROVIDER not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER={PROVIDER!r} is not implemented; choose from {sorted(PROVIDERS)}")
    return PROVIDERS[PROVIDER]


def generate(system, user, model=None, temperature=None, json_schema=None):
    """Returns {text, model, provider, input_tokens, output_tokens, reasoning_tokens, cost_usd}.
    output_tokens includes reasoning_tokens (that is how they are billed).
    json_schema: a JSON Schema the reply must follow (text is then a JSON string)."""
    model = model or MODEL
    start = time.perf_counter()
    text, tin, tout, treason = _provider()["call"](system, user, model, temperature, json_schema)
    return {
        "text": text,
        "model": model,
        "provider": PROVIDER,
        "input_tokens": tin,
        "output_tokens": tout,
        "reasoning_tokens": treason,
        "cost_usd": estimate_cost(model, tin, tout),
        "seconds": round(time.perf_counter() - start, 2),
    }


def check_models():
    """Print whether LLM_MODEL / LLM_MODEL_CHEAP exist for this key; list alternatives if not."""
    available = _provider()["models"]()
    wanted = {"LLM_MODEL": MODEL, "LLM_MODEL_CHEAP": MODEL_CHEAP}
    missing = False
    for var, name in wanted.items():
        ok = name in available
        missing |= not ok
        print(f"{var}={name}: {'available' if ok else 'NOT available'}")
    if missing:
        print("Available models:", ", ".join(sorted(available)))


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_models()
    else:
        r = generate("Reply in one short sentence.", " ".join(sys.argv[1:]) or "Say hello.")
        print(r)
