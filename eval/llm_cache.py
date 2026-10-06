"""On-disk cache for LLM calls made by the evals (eval/cache/, git-ignored).

The key is a SHA-256 of the provider, model, system prompt, user prompt, temperature, JSON schema
and a `vote` number. The answer prompt contains the question and every retrieved chunk's header and
text, so a different question, different retrieved chunks, a changed prompt or another model all
give a new key. `vote` separates the N independent judge calls of a majority vote.

A cached result keeps its original token counts and cost, so reported costs are the cost of the
calls whether or not they were cached; `hits` / `misses` count what was actually sent.
"""
import hashlib
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rag import llm  # noqa: E402

CACHE_DIR = ROOT / "eval" / "cache"


class CachedLLM:
    def __init__(self, kind, enabled=True):
        self.dir = CACHE_DIR / kind
        self.enabled = enabled
        self.hits = self.misses = 0
        self._lock = threading.Lock()

    def generate(self, system, user, model=None, temperature=None, json_schema=None, vote=0, provider=None):
        model = model or llm.MODEL
        provider = provider or llm.PROVIDER
        payload = json.dumps({"provider": provider, "model": model, "system": system, "user": user,
                              "temperature": temperature, "schema": json_schema, "vote": vote},
                             sort_keys=True, ensure_ascii=False)
        path = self.dir / f"{hashlib.sha256(payload.encode('utf-8')).hexdigest()}.json"
        if self.enabled and path.exists():
            with self._lock:
                self.hits += 1
            return {**json.loads(path.read_text(encoding="utf-8")), "cached": True}
        result = llm.generate(system, user, model=model, temperature=temperature, json_schema=json_schema,
                              provider=provider)
        with self._lock:
            self.misses += 1
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        return {**result, "cached": False}
