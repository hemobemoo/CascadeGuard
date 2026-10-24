"""Record/replay cache for LLM decisions (AGENTS.md "Determinism and replay").

Key = sha256 of the canonical JSON of (role, boundary-filtered view, prompt version, model id,
response schema). A decision depends only on these inputs, so a replay step whose view the
repair did not change gets the cached decision back and makes no call. One JSON file per key,
by default under data/llm_cache/ (git-ignored). Entries hold the validated decision or a
closed no-decision reason, and the call's usage; never request headers or keys.
"""

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.decisions import AgentDecision, NoDecisionReason
from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.simulation.boundaries import RoleView

DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "llm_cache"


class Usage(DomainModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None  # credits, from OpenRouter's usage data
    latency_seconds: float = 0.0
    calls: int = Field(default=0, ge=0)  # API calls made for this entry (a retry counts)


class CacheEntry(DomainModel):
    key: str
    role_id: str
    model_sha256: str  # a hash, not the model id: .env values are never written out
    prompt_version: str
    outcome: Literal["decision", "no_decision"]
    decision: AgentDecision | None = None
    no_decision: NoDecisionReason | None = None
    usage: Usage = Usage()


def _plain(value: Any) -> Any:
    """Canonical plain data for hashing: dataclasses and models as sorted dicts, tuples as lists,
    datetimes as ISO strings."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, DomainModel):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def canonical_view(view: RoleView) -> Any:
    return _plain(view)


def model_digest(model: str) -> str:
    return hashlib.sha256(model.encode("utf-8")).hexdigest()


def cache_key(
    role_id: str, view: RoleView, prompt_version: str, model: str, schema: dict[str, Any]
) -> str:
    payload = {
        "role": role_id,
        "view": canonical_view(view),
        "prompt_version": prompt_version,
        "model": model,
        "schema": schema,
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    keys_hit: list[str] = field(default_factory=list[str])
    keys_missed: list[str] = field(default_factory=list[str])
    untrusted: int = 0  # unreadable or mismatched cache files, treated as misses


class DecisionCache:
    def __init__(self, directory: Path = DEFAULT_CACHE_DIR) -> None:
        self.directory = directory
        self.stats = CacheStats()
        # Every outcome seen through this cache object, including request failures (which are
        # never written to disk): a baseline and its replays share one cache, so a step with an
        # unchanged view gets the same outcome in every run of the family, never a fresh call.
        self._memo: dict[str, CacheEntry] = {}

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> CacheEntry | None:
        entry = self._memo.get(key) or self._read(key)
        if entry is None:
            self.stats.misses += 1
            self.stats.keys_missed.append(key)
            return None
        self._memo[key] = entry
        self.stats.hits += 1
        self.stats.keys_hit.append(key)
        return entry

    def _read(self, key: str) -> CacheEntry | None:
        """The stored entry, or None. An unreadable file, or one holding another key (renamed or
        copied), is not trusted: it counts as a miss and is overwritten by the next result."""
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            entry = CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.stats.untrusted += 1
            return None
        if entry.key != key:
            self.stats.untrusted += 1
            return None
        return entry

    def remember(self, entry: CacheEntry) -> None:
        """Keep an outcome for this cache object only (request failures: not on disk)."""
        self._memo[entry.key] = entry

    def put(self, entry: CacheEntry) -> None:
        self._memo[entry.key] = entry
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(entry.key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
