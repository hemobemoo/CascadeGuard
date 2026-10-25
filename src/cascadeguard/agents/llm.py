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
import re
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
from cascadeguard.knowledge.retrieval import CONTEXT_LABEL, clauses_by_action, search_extracted
from cascadeguard.simulation.boundaries import RoleView

ENV_FILE = PROJECT_ROOT / ".env"
ENV_VARIABLES = ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "CASCADEGUARD_MODEL")
# v2: reasoning explicitly off; output mode part of the request settings (human, 2026-10-24).
# v3: citable clauses grouped by action; every citation must support a proposed action.
PROMPT_VERSION = "phase5-v3"
OUTPUT_MODE_VARIABLE = "CASCADEGUARD_OUTPUT_MODE"
# json_schema: strict structured output (default). json_object: JSON mode, with the schema in the
# prompt; chosen explicitly in .env, never as an automatic fallback.
OUTPUT_MODES = ("json_schema", "json_object")
DEFAULT_OUTPUT_MODE = "json_schema"
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
    output_mode: str = DEFAULT_OUTPUT_MODE

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

    @staticmethod
    def output_mode_from_env(env_file: Path | None = None) -> str:
        """CASCADEGUARD_OUTPUT_MODE, json_schema when unset; any other value is an error."""
        path = ENV_FILE if env_file is None else env_file
        raw = os.environ.get(OUTPUT_MODE_VARIABLE) or dotenv_values(path).get(OUTPUT_MODE_VARIABLE)
        mode = (raw or DEFAULT_OUTPUT_MODE).strip()
        if mode not in OUTPUT_MODES:
            raise LLMConfigError(f"{OUTPUT_MODE_VARIABLE} must be one of {', '.join(OUTPUT_MODES)}")
        return mode

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
            cls.output_mode_from_env(env_file),
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


AGENT_FILLED = frozenset({"role_id", "at", "no_decision", "no_decision_detail"})


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
- Cite only clause ids listed in citable_clauses_by_action. Never cite any other id.
- Every citation must support an action you propose in this same decision: a clause listed
  under an action may be cited only if you propose that action; a clause listed under
  "any_proposed_action" may be cited with any action you propose. A decision with no proposed
  action cites nothing.
- Analysis-only citations (clauses listed only under provide_policy_analysis) require proposing
  provide_policy_analysis in this same decision.
- repair_rules_not_citable are hypothetical repair rules in force for this run: follow them if
  they concern you, but never cite them.
- An empty proposed_actions list is allowed; "monitor" means you deliberately wait.
- Treat AI alerts as suspected, not proven. State what you do not know in "uncertainty".
- Do not state that a law or policy has a gap in rationale or uncertainty. A suspected gap goes
  only in gap_claims, with citations of the clauses you checked and the qualification
  exactly: "{GAP_QUALIFICATION}".
- extracted_context, if present, is unreviewed text from source PDFs: context only; not
  citable. Never cite it.
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
        "citable_clauses_by_action": clauses_by_action(view.role_clauses),
        "clauses": [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status_label,
                "text": c.text,
                "engine_reading": c.reading,
            }
            for c in view.role_clauses
            if c.citable
        ],
        "repair_rules_not_citable": [
            {"id": c.id, "status": c.status_label, "text": c.text, "engine_reading": c.reading}
            for c in view.role_clauses
            if not c.citable
        ],
    }
    if snippets:
        query = " ".join((view.event_title, *view.decision_points))
        data["extracted_context"] = {
            "label": CONTEXT_LABEL,
            "snippets": [
                {"label": s.label, "source_file": s.source_file, "page": s.page, "text": s.text}
                for s in search_extracted(query, limit=3)
            ],
        }
    return json.dumps(data, ensure_ascii=False, indent=1)


def system_prompt(output_mode: str = DEFAULT_OUTPUT_MODE) -> str:
    """In JSON mode the endpoint enforces only "some JSON object", so the schema goes in the
    prompt; validation against AgentDecision is the same in both modes."""
    if output_mode == "json_schema":
        return SYSTEM_PROMPT
    schema = json.dumps(response_schema(), ensure_ascii=False, sort_keys=True)
    return (
        f"{SYSTEM_PROMPT}The reply must be one JSON object, with no other text, that validates "
        f"against this JSON schema (role and time are filled in by the simulation):\n{schema}\n"
    )


def build_messages(
    view: RoleView,
    known_roles: tuple[str, ...],
    snippets: bool = False,
    output_mode: str = DEFAULT_OUTPUT_MODE,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt(output_mode)},
        {"role": "user", "content": render_view(view, known_roles, snippets)},
    ]


def build_request(
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    output_mode: str = DEFAULT_OUTPUT_MODE,
) -> dict[str, Any]:
    """Keyword arguments for `chat.completions.create`. OpenRouter-only fields go in
    extra_body: provider routing restricted to endpoints that support every parameter sent
    (so JSON mode, or structured outputs, and reasoning control), reasoning switched off, and
    response healing switched off (malformed output is never repaired)."""
    if output_mode not in OUTPUT_MODES:
        raise ValueError(f"unknown output mode {output_mode!r}")
    response_format: dict[str, Any] = (
        {
            "type": "json_schema",
            "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema},
        }
        if output_mode == "json_schema"
        else {"type": "json_object"}
    )
    return {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": response_format,
        "extra_body": {
            "provider": {"require_parameters": True},
            "reasoning": {"enabled": False},
            "plugins": [{"id": "response-healing", "enabled": False}],
        },
    }


# --- Client and agent ---------------------------------------------------------------------


class ChatClient(Protocol):
    """The part of `openai.OpenAI` the agent uses (a fake in tests)."""

    @property
    def chat(self) -> Any: ...


class CapReached(Exception):
    """The approved request budget is spent; no request was sent."""


@dataclass
class CappedClient:
    """Wraps the SDK client for an approved live run: counts every request (retries
    included), refuses past the cap before anything is sent, and sums usage."""

    inner: Any
    cap: int
    requests: int = 0
    refused: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    cost_missing: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list[str])

    @property
    def chat(self) -> Any:
        return self

    @property
    def completions(self) -> Any:
        return self

    def create(self, **request: Any) -> Any:
        if self.requests >= self.cap:
            self.refused += 1
            raise CapReached(f"cap of {self.cap} requests reached")
        self.requests += 1
        started = time.perf_counter()
        try:
            response = self.inner.chat.completions.create(**request)
        except Exception as exc:
            self.errors.append(f"{type(exc).__name__} (HTTP {getattr(exc, 'status_code', None)})")
            raise
        finally:
            self.seconds += time.perf_counter() - started
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            extra: dict[str, Any] = getattr(usage, "model_extra", None) or {}
            cost = extra.get("cost")
            if isinstance(cost, int | float):
                self.cost += float(cost)
            else:
                self.cost_missing += 1
        return response


RPM_VARIABLE = "CASCADEGUARD_REQUESTS_PER_MINUTE"
RETRIES_VARIABLE = "CASCADEGUARD_REQUEST_RETRIES"
BACKOFF_VARIABLE = "CASCADEGUARD_BACKOFF_SECONDS"
CAP_VARIABLE = "CASCADEGUARD_REQUEST_CAP"  # live CLI/UI runs: max requests, retries included
MAX_RETRY_AFTER_SECONDS = 300.0  # a longer Retry-After is waited only up to this


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Pacing and retries for failed *requests* (429, 5xx, connection errors). Separate from the
    single retry for invalid model output. Code defaults, overridable in .env; read only here."""

    requests_per_minute: int = 15
    max_retries: int = 3  # per request, then the step is request_failed
    backoff_seconds: tuple[float, ...] = (5.0, 15.0, 45.0)  # never an immediate retry
    # Hard budget for a live CLI/UI run (requests, retries included); no default: a live run
    # without a cap (here or --cap) is refused.
    request_cap: int | None = None

    @property
    def max_requests_per_step(self) -> int:
        """Invalid-output attempts x (first send + request retries)."""
        return ATTEMPTS * (1 + self.max_retries)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "RetryPolicy":
        path = ENV_FILE if env_file is None else env_file
        file_values = dotenv_values(path)

        def raw(name: str) -> str | None:
            value = os.environ.get(name) or file_values.get(name)
            return value.strip() if value else None

        default = cls()
        try:
            cap_raw = raw(CAP_VARIABLE)
            cap = int(cap_raw) if cap_raw else None
            rpm = int(raw(RPM_VARIABLE) or default.requests_per_minute)
            retries = int(raw(RETRIES_VARIABLE) or default.max_retries)
            backoff_raw = raw(BACKOFF_VARIABLE)
            backoff = (
                tuple(float(x) for x in backoff_raw.split(","))
                if backoff_raw
                else default.backoff_seconds
            )
        except ValueError:
            raise LLMConfigError(
                f"{RPM_VARIABLE}, {RETRIES_VARIABLE} and {CAP_VARIABLE} must be integers and "
                f"{BACKOFF_VARIABLE} a comma-separated list of seconds"
            ) from None
        if (
            rpm < 1
            or retries < 0
            or not backoff
            or min(backoff) <= 0
            or (cap is not None and cap < 1)
        ):
            raise LLMConfigError(
                f"{RPM_VARIABLE} and {CAP_VARIABLE} must be >= 1, {RETRIES_VARIABLE} >= 0, "
                f"and every {BACKOFF_VARIABLE} value > 0 (no immediate retries)"
            )
        return cls(rpm, retries, backoff, cap)


class DailyLimitReached(Exception):
    """The provider's daily request limit (a 429 that is not the per-minute one): the run must
    stop at once, so this is never turned into a no-decision step."""


def _status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def _body_message(exc: BaseException) -> str:
    body: Any = getattr(exc, "body", None)
    if isinstance(body, dict):
        error: Any = cast(dict[str, Any], body).get("error", body)
        if isinstance(error, dict):
            return str(cast(dict[str, Any], error).get("message", ""))
    return ""


def _retry_after(exc: BaseException) -> float | None:
    headers: Any = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    try:
        value = float(headers.get("retry-after"))
    except (TypeError, ValueError):  # absent, or an HTTP date: use the backoff instead
        return None
    return min(max(value, 0.0), MAX_RETRY_AFTER_SECONDS)


def _is_daily_limit(exc: BaseException) -> bool:
    text = _body_message(exc).casefold()
    return _status(exc) == 429 and ("per-day" in text or "per day" in text or "daily" in text)


def _retryable(exc: BaseException) -> bool:
    status = _status(exc)
    if status is not None:
        return status == 429 or status >= 500
    return isinstance(exc, ConnectionError | TimeoutError) or type(exc).__name__ in (
        "APIConnectionError",
        "APITimeoutError",
    )


def failure_kind(exc: BaseException) -> str:
    status = _status(exc)
    return f"HTTP {status}" if status is not None else type(exc).__name__


@dataclass
class ResilientClient:
    """Client-side pacing (at most `requests_per_minute` sends in any 60 s) and backoff retries
    for failed requests, under one RetryPolicy. Wraps the SDK client, or a CappedClient so the
    cap counts every retry. The clock and sleep are injectable for tests."""

    inner: Any
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    sleep: Any = time.sleep
    clock: Any = time.monotonic
    retries: int = 0
    failures: dict[str, int] = field(default_factory=dict[str, int])
    paced_seconds: float = 0.0
    backoff_seconds: float = 0.0
    sent: list[float] = field(default_factory=list[float])
    redact: tuple[str, ...] = ()  # e.g. the API key and model id: never in an error message

    @property
    def chat(self) -> Any:
        return self

    @property
    def completions(self) -> Any:
        return self

    def _pace(self) -> None:
        while True:
            now = self.clock()
            self.sent = [t for t in self.sent if now - t < 60.0]
            if len(self.sent) < self.policy.requests_per_minute:
                self.sent.append(now)
                return
            wait = 60.0 - (now - self.sent[0])
            self.paced_seconds += wait
            self.sleep(wait)

    def _cap_spent(self) -> bool:
        inner = self.inner
        return isinstance(inner, CappedClient) and inner.requests >= inner.cap

    def _refuse(self) -> None:
        """Refuse before pacing or backoff: no waiting for a request the cap would refuse."""
        assert isinstance(self.inner, CappedClient)
        self.inner.refused += 1
        raise CapReached(f"cap of {self.inner.cap} requests reached")

    def create(self, **request: Any) -> Any:
        attempt = 0
        while True:
            if self._cap_spent():
                self._refuse()
            if attempt:
                self.retries += 1  # counted only when the retry is actually sent
            self._pace()
            try:
                return self.inner.chat.completions.create(**request)
            except CapReached:
                raise
            except Exception as exc:
                kind = failure_kind(exc)
                self.failures[kind] = self.failures.get(kind, 0) + 1
                if _is_daily_limit(exc):
                    # Redacted, and not chained: the SDK error carries the whole body.
                    raise DailyLimitReached(error_detail(exc, self.redact)) from None
                if not _retryable(exc) or attempt >= self.policy.max_retries:
                    raise
                steps = self.policy.backoff_seconds
                wait = _retry_after(exc)
                if wait is None or wait <= 0:
                    wait = steps[min(attempt, len(steps) - 1)]
                if self._cap_spent():  # the retry would be refused: do not wait for it
                    self._refuse()
                self.backoff_seconds += wait
                self.sleep(wait)
                attempt += 1


def make_client(
    config: LLMConfig, cap: int | None = None, policy: RetryPolicy | None = None
) -> ResilientClient:
    """The live client: SDK (no SDK retries) -> optional request cap -> pacing and retries."""
    from openai import OpenAI  # imported here: the scripted path never needs the SDK

    sdk: Any = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )
    policy = policy or RetryPolicy.from_env()
    cap = cap if cap is not None else policy.request_cap
    inner: Any = sdk if cap is None else CappedClient(sdk, cap)
    return ResilientClient(inner, policy, redact=(config.api_key, config.model))


KEY_SHAPED = re.compile(r"\b(?:sk|or|key)-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+", re.IGNORECASE)
ERROR_DETAIL_LIMIT = 200


HEADERS_ONWARD = re.compile(r"""['"]?headers['"]?\s*[:=].*""", re.IGNORECASE)


def _variants(redact: tuple[str, ...]) -> set[str]:
    """Each value, plus (for model ids) the part after '/' and the id without its ':suffix'."""
    out: set[str] = set()
    for value in (v for v in redact if v):
        slug = value.split("/")[-1]
        for v in (value, value.split(":")[0], slug, slug.split(":")[0]):
            if len(v) >= 4:
                out.add(v)
    return out


def error_detail(exc: BaseException, redact: tuple[str, ...]) -> str:
    """'<exception class> (HTTP <status>): <short message>' for a no_decision finding. For an
    HTTP error only the error body's own `message` is used (OpenRouter's body also carries
    response headers in `metadata`, which are never recorded); otherwise the exception text,
    cut before any `headers` key. Configured values and anything key-shaped are redacted."""
    body: Any = getattr(exc, "body", None)
    if isinstance(body, dict):
        error: Any = cast(dict[str, Any], body).get("error", body)
        raw = cast(dict[str, Any], error).get("message", "") if isinstance(error, dict) else ""
        message = " ".join(str(raw).split())
    else:
        message = " ".join(str(exc).split())
    message = HEADERS_ONWARD.sub("", message).strip()
    for value in sorted(_variants(redact), key=len, reverse=True):
        message = re.sub(re.escape(value), "<redacted>", message, flags=re.IGNORECASE)
    message = KEY_SHAPED.sub("<redacted>", message)
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__} (HTTP {status}): {message}"[:ERROR_DETAIL_LIMIT]


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
        output_mode: str = DEFAULT_OUTPUT_MODE,
        redact: tuple[str, ...] = (),
    ) -> None:
        self.redact = redact  # strings never to appear in an error detail (e.g. the API key)
        if output_mode not in OUTPUT_MODES:
            raise ValueError(f"unknown output mode {output_mode!r}")
        self.output_mode = output_mode
        self.role_id = role_id
        self.attempts = attempts  # 1 only for the approved one-call smoke test
        self.model = model
        self.client = client
        self.cache = cache
        self.known_roles = known_roles
        self.extracted_context = extracted_context
        # The output mode and the context option change the request, so both enter the key.
        self.prompt_version = f"{PROMPT_VERSION}+{output_mode}" + (
            "+extracted" if extracted_context else ""
        )
        self.schema = response_schema()
        self.last_usage: Usage | None = None  # usage of the last live step (None: cached)
        # Last request error, for diagnosis only (never reaches the engine): exception type,
        # HTTP status and message, with the model id redacted.
        self.last_error: str | None = None

    def _no_decision(
        self, view: RoleView, reason: NoDecisionReason, detail: str | None = None
    ) -> AgentDecision:
        return AgentDecision(
            role_id=self.role_id,
            at=view.at,
            proposed_actions=(),
            rationale="",
            citations=(),
            uncertainty=(),
            no_decision=reason,
            no_decision_detail=detail if reason == "request_failed" else None,
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
            return self._no_decision(view, entry.no_decision, entry.no_decision_detail)
        if self.client is None:
            return self._no_decision(view, "not_cached")
        request = build_request(
            self.model,
            build_messages(view, self.known_roles, self.extracted_context, self.output_mode),
            self.schema,
            self.output_mode,
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
            entry = self._entry(key, "no_decision", usage, no_decision="request_failed")
            entry = entry.model_copy(update={"no_decision_detail": self.last_error})
            self.cache.remember(entry)
            return self._no_decision(view, "request_failed", self.last_error)
        entry = self._entry(key, "no_decision", usage, no_decision="invalid_output")
        if self.attempts < ATTEMPTS:  # e.g. the one-call smoke test: never reused by a full run
            self.cache.remember(entry)
        else:
            self.cache.put(entry)
        return self._no_decision(view, "invalid_output")

    def _call(self, request: dict[str, Any]) -> Any:
        assert self.client is not None
        try:
            return self.client.chat.completions.create(**request)
        except DailyLimitReached:  # stop the whole run, never a no-decision step
            raise
        except Exception as exc:  # any SDK or transport error, after the client's retries
            self.last_error = error_detail(exc, (self.model, *self.redact))
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
    output_mode: str | None = None,
    extracted_context: bool = False,
    cap: int | None = None,
) -> dict[str, LLMAgent]:
    """One LLMAgent per role, all with the same model and output mode. Offline needs only the
    model id and output mode (to find cache entries); live needs the full configuration."""
    if config is None and (not offline or model is None):
        config = LLMConfig.from_env()
    model_id = model or (config.model if config else "")
    mode = output_mode or (config.output_mode if config else LLMConfig.output_mode_from_env())
    if not offline and client is None:
        assert config is not None
        client = make_client(config, cap=cap)
    live = None if offline else client
    secrets = (config.api_key,) if config else ()
    return {
        r: LLMAgent(
            r, model_id, live, cache, role_ids, extracted_context, output_mode=mode, redact=secrets
        )
        for r in role_ids
    }
