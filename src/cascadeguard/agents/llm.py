"""LLMAgent: one configured model plays a role through OpenRouter (AGENTS.md "LLM configuration").

The agent sees only its frozen `RoleView` and returns an `AgentDecision`; the engine decides
everything. Configuration comes only from `.env` / the environment; there is no default model.
Each step goes through the record/replay cache (`agents/cache.py`) before any call. A reply that
is not valid JSON for the schema is retried once, then the step is "no decision"
(`AgentDecision.no_decision`), which the engine records as a finding. Output is never repaired:
OpenRouter's response-healing plugin is explicitly disabled on every request.
"""

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from dotenv import dotenv_values
from pydantic import Field, ValidationError

from cascadeguard.agents.cache import CacheEntry, DecisionCache, Usage, cache_key, model_digest
from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.decisions import (
    GAP_QUALIFICATION,
    AgentDecision,
    Citation,
    GapClaim,
    NoDecisionReason,
    ProposedAction,
)
from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.knowledge.retrieval import CONTEXT_LABEL, search_extracted
from cascadeguard.simulation.boundaries import RoleView

ENV_FILE = PROJECT_ROOT / ".env"
ENV_VARIABLES = ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "CASCADEGUARD_MODEL")
PROMPT_VERSION = "phase5-v1"
SCHEMA_NAME = "agent_decision"
REQUEST_TIMEOUT_SECONDS = 120.0
ATTEMPTS = 2  # the first call and one retry (AGENTS.md)


class LLMConfigError(RuntimeError):
    """A required variable is missing. The message names variables, never values."""


@dataclass(frozen=True, slots=True)
class LLMConfig:
    api_key: str = field(repr=False)
    base_url: str
    model: str

    @staticmethod
    def _values(env_file: Path | None, needed: tuple[str, ...]) -> dict[str, str]:
        """Values from `.env`, overridden by the process environment. No defaults."""
        path = ENV_FILE if env_file is None else env_file  # read at call time, not import time
        values: dict[str, str] = {
            k: v for k, v in dotenv_values(path).items() if v is not None and k in needed
        }
        values |= {k: os.environ[k] for k in needed if os.environ.get(k)}
        missing = [k for k in needed if not values.get(k, "").strip()]
        if missing:
            raise LLMConfigError(
                f"LLM agents need {', '.join(missing)} in .env (see .env.example); "
                "no default model is used"
            )
        return values

    @classmethod
    def model_from_env(cls, env_file: Path | None = None) -> str:
        """Only the model id: enough for offline runs from the cache (no key needed)."""
        return cls._values(env_file, ("CASCADEGUARD_MODEL",))["CASCADEGUARD_MODEL"].strip()

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "LLMConfig":
        values = cls._values(env_file, ENV_VARIABLES)
        return cls(
            values["OPENROUTER_API_KEY"].strip(),
            values["OPENROUTER_BASE_URL"].strip(),
            values["CASCADEGUARD_MODEL"].strip(),
        )


# --- Response schema: AgentDecision without role_id and at (filled from the view) -------------


class Parameter(DomainModel):
    name: str
    value: str


class LLMAction(DomainModel):
    action_type: str
    target: str | None
    # Strict JSON schema needs closed objects, so the parameters dict travels as pairs.
    parameters: tuple[Parameter, ...]


class LLMDecisionPayload(DomainModel):
    """What the model returns: the fields of AgentDecision except role_id, at and no_decision."""

    proposed_actions: tuple[LLMAction, ...]
    rationale: str
    citations: tuple[Citation, ...]
    uncertainty: tuple[str, ...]
    gap_claims: tuple[GapClaim, ...] = Field(default=())


AGENT_FILLED = frozenset({"role_id", "at", "no_decision"})


def _strict(node: Any) -> Any:
    """OpenAI-style strict schema: every object closed with all properties required, no
    defaults or titles, `const` as a one-value enum."""
    if isinstance(node, list):
        return [_strict(v) for v in cast(list[Any], node)]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for k, v in cast(dict[str, Any], node).items():
        if k in ("default", "title"):
            continue
        if k == "const":
            out["enum"] = [v]
            continue
        out[k] = _strict(v)
    if out.get("type") == "object" and "properties" in out:
        out["required"] = sorted(out["properties"])
        out["additionalProperties"] = False
    return out


def response_schema() -> dict[str, Any]:
    return _strict(LLMDecisionPayload.model_json_schema())


def to_decision(payload: LLMDecisionPayload, view: RoleView) -> AgentDecision:
    """The full AgentDecision, validated again from plain data. Duplicate parameter names are
    malformed output (never collapsed): ValueError, so the reply is retried or rejected."""
    for a in payload.proposed_actions:
        names = [p.name for p in a.parameters]
        if len(names) != len(set(names)):
            raise ValueError("duplicate parameter names")
    return AgentDecision.model_validate(
        {
            "role_id": view.role_id,
            "at": view.at,
            "proposed_actions": [
                ProposedAction(
                    action_type=a.action_type,
                    target=a.target,
                    parameters={p.name: p.value for p in a.parameters},
                ).model_dump()
                for a in payload.proposed_actions
            ],
            "rationale": payload.rationale,
            "citations": [c.model_dump() for c in payload.citations],
            "uncertainty": list(payload.uncertainty),
            "gap_claims": [g.model_dump() for g in payload.gap_claims],
        }
    )


# --- Prompt -------------------------------------------------------------------------------

SYSTEM_PROMPT = f"""\
You play one institutional role in a hypothetical, synthetic incident simulation (CascadeGuard).
You only PROPOSE actions; a deterministic engine accepts or rejects them and decides everything.

Rules:
- Use only the information in the role view you are given. Do not invent facts.
- Propose only actions listed in allowed_actions. A target must be a role id from known_roles.
- share_incident_status needs target and parameter "fact" (the id of a fact you know).
- request_information needs target and parameter "data_category".
- Cite only clause ids from role_clauses whose "citable" is true. Never cite any other id.
  Clauses marked not citable are hypothetical repair rules in force for this run.
- An empty proposed_actions list is allowed; "monitor" means you deliberately wait.
- Treat AI alerts as suspected, not proven. State what you do not know in "uncertainty".
- Do not state that a law or policy has a gap in rationale or uncertainty. A suspected gap goes
  only in gap_claims, with citations of the clauses you checked and the qualification
  exactly: "{GAP_QUALIFICATION}".
- Your rationale is recorded as an unverified agent statement, not a finding or legal advice.
Reply with JSON matching the schema only.
"""


def render_view(view: RoleView, known_roles: tuple[str, ...], snippets: bool = False) -> str:
    data: dict[str, Any] = {
        "role_id": view.role_id,
        "role_name": view.role_name,
        "instructions": view.instructions,
        "simulation_time": view.at.isoformat(),
        "minute": view.minute,
        "inject": {"title": view.event_title, "description": view.event_description},
        "decision_points": list(view.decision_points),
        "facts_you_know": [
            {
                "id": f.id,
                "statement": f.statement,
                "data_category": f.data_category,
                "certainty": f.certainty.value,
            }
            for f in view.facts
        ],
        "allowed_actions": list(view.allowed_actions),
        "known_roles": list(known_roles),
        "your_accepted_actions_so_far": list(view.own_history),
        "clauses_shown_with_this_inject": [
            {"id": c.id, "title": c.title, "status": c.status_label} for c in view.clauses
        ],
        "role_clauses": [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status_label,
                "citable": c.citable,
                "text": c.text,
                "engine_reading": c.reading,
            }
            for c in view.role_clauses
        ],
    }
    if snippets:
        query = " ".join((view.event_title, *view.decision_points))
        data["extracted_context"] = {
            "label": CONTEXT_LABEL,
            "snippets": [
                {"source_file": s.source_file, "page": s.page, "text": s.text}
                for s in search_extracted(query, limit=3)
            ],
        }
    return json.dumps(data, ensure_ascii=False, indent=1)


def build_messages(
    view: RoleView, known_roles: tuple[str, ...], snippets: bool = False
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": render_view(view, known_roles, snippets)},
    ]


def build_request(
    model: str, messages: list[dict[str, str]], schema: dict[str, Any]
) -> dict[str, Any]:
    """Keyword arguments for `chat.completions.create`. OpenRouter-only fields go in
    extra_body: provider routing restricted to endpoints that support every parameter sent,
    and response healing switched off (malformed output is never repaired)."""
    return {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema},
        },
        "extra_body": {
            "provider": {"require_parameters": True},
            "plugins": [{"id": "response-healing", "enabled": False}],
        },
    }


# --- Client and agent ---------------------------------------------------------------------


class ChatClient(Protocol):
    """The part of `openai.OpenAI` the agent uses (a fake in tests)."""

    @property
    def chat(self) -> Any: ...


def make_client(config: LLMConfig) -> ChatClient:
    from openai import OpenAI  # imported here: the scripted path never needs the SDK

    # max_retries=0: the agent's own single retry is the only one, so calls (and cost) are known.
    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


class RequestFailed(Exception):
    """The API call failed (network, HTTP error, no routable provider)."""


def _usage(response: Any) -> tuple[int, int, float | None]:
    u = getattr(response, "usage", None)
    if u is None:
        return 0, 0, None
    extra: Mapping[str, Any] = getattr(u, "model_extra", None) or {}
    cost = extra.get("cost", getattr(u, "cost", None))
    return (
        int(getattr(u, "prompt_tokens", 0) or 0),
        int(getattr(u, "completion_tokens", 0) or 0),
        float(cost) if isinstance(cost, int | float) else None,
    )


def _add_cost(total: float | None, cost: float | None) -> float | None:
    return None if total is None and cost is None else (total or 0.0) + (cost or 0.0)


def _content(response: Any) -> str | None:
    choices: Any = getattr(response, "choices", None)
    if not isinstance(choices, list | tuple) or not choices:
        return None
    first: Any = cast(list[Any], choices)[0]
    message = getattr(first, "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else None


class LLMAgent:
    """One role played by the configured model. `client=None` is offline: cache only."""

    def __init__(
        self,
        role_id: str,
        model: str,
        client: ChatClient | None,
        cache: DecisionCache,
        known_roles: tuple[str, ...],
        extracted_context: bool = False,
        attempts: int = ATTEMPTS,
    ) -> None:
        self.role_id = role_id
        self.attempts = attempts  # 1 only for the approved one-call smoke test
        self.model = model
        self.client = client
        self.cache = cache
        self.known_roles = known_roles
        self.extracted_context = extracted_context
        self.prompt_version = PROMPT_VERSION + ("+extracted" if extracted_context else "")
        self.schema = response_schema()
        self.last_usage: Usage | None = None  # usage of the last live step (None: cached)
        # Last request error, for diagnosis only (never reaches the engine): exception type,
        # HTTP status and message, with the model id redacted.
        self.last_error: str | None = None

    def _no_decision(self, view: RoleView, reason: NoDecisionReason) -> AgentDecision:
        return AgentDecision(
            role_id=self.role_id,
            at=view.at,
            proposed_actions=(),
            rationale="",
            citations=(),
            uncertainty=(),
            no_decision=reason,
        )

    def observe(self, view: RoleView) -> AgentDecision:
        self.last_usage = None
        self.last_error = None
        key = cache_key(self.role_id, view, self.prompt_version, self.model, self.schema)
        entry = self.cache.get(key)
        if entry is not None:
            if entry.decision is not None:
                return entry.decision
            assert entry.no_decision is not None
            return self._no_decision(view, entry.no_decision)
        if self.client is None:
            return self._no_decision(view, "not_cached")
        request = build_request(
            self.model,
            build_messages(view, self.known_roles, self.extracted_context),
            self.schema,
        )
        usage = Usage()
        failed_request = False
        decision: AgentDecision | None = None
        for _ in range(self.attempts):
            started = time.perf_counter()
            try:
                response = self._call(request)
            except RequestFailed:
                failed_request = True
                elapsed = usage.latency_seconds + time.perf_counter() - started
                usage = usage.model_copy(
                    update={"calls": usage.calls + 1, "latency_seconds": elapsed}
                )
                continue
            prompt, completion, cost = _usage(response)
            usage = Usage(
                prompt_tokens=usage.prompt_tokens + prompt,
                completion_tokens=usage.completion_tokens + completion,
                cost=_add_cost(usage.cost, cost),
                latency_seconds=usage.latency_seconds + time.perf_counter() - started,
                calls=usage.calls + 1,
            )
            decision = self._parse(_content(response), view)
            if decision is not None:
                break
        self.last_usage = usage
        if decision is not None:
            self.cache.put(self._entry(key, "decision", usage, decision=decision))
            return decision
        if failed_request:  # not on disk (a later session may succeed), but fixed for this one
            self.cache.remember(
                self._entry(key, "no_decision", usage, no_decision="request_failed")
            )
            return self._no_decision(view, "request_failed")
        self.cache.put(self._entry(key, "no_decision", usage, no_decision="invalid_output"))
        return self._no_decision(view, "invalid_output")

    def _call(self, request: dict[str, Any]) -> Any:
        assert self.client is not None
        try:
            return self.client.chat.completions.create(**request)
        except Exception as exc:  # any SDK or transport error; details are not kept
            status = getattr(exc, "status_code", None)
            detail = " ".join(str(exc).split())[:300].replace(self.model, "<model>")
            self.last_error = f"{type(exc).__name__} (HTTP {status}): {detail}"
            raise RequestFailed(type(exc).__name__) from exc

    def _parse(self, content: str | None, view: RoleView) -> AgentDecision | None:
        if content is None:
            return None
        try:
            payload = LLMDecisionPayload.model_validate_json(content)
            return to_decision(payload, view)
        except (ValidationError, ValueError):
            return None

    def _entry(
        self,
        key: str,
        outcome: str,
        usage: Usage,
        decision: AgentDecision | None = None,
        no_decision: NoDecisionReason | None = None,
    ) -> CacheEntry:
        return CacheEntry.model_validate(
            {
                "key": key,
                "role_id": self.role_id,
                "model_sha256": model_digest(self.model),
                "prompt_version": self.prompt_version,
                "outcome": outcome,
                "decision": decision,
                "no_decision": no_decision,
                "usage": usage,
            }
        )


def llm_agents(
    role_ids: tuple[str, ...],
    cache: DecisionCache,
    offline: bool = False,
    config: LLMConfig | None = None,
    client: ChatClient | None = None,
    model: str | None = None,
) -> dict[str, LLMAgent]:
    """One LLMAgent per role, all with the same model. Offline needs only the model id (to find
    cache entries); live needs the full configuration."""
    if config is None and (not offline or model is None):
        config = LLMConfig.from_env()
    model_id = model or (config.model if config else "")
    if not offline and client is None:
        assert config is not None
        client = make_client(config)
    return {
        r: LLMAgent(r, model_id, None if offline else client, cache, role_ids) for r in role_ids
    }
