"""The live-run clients: the request cap, and pacing and retries for failed requests."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cascadeguard.agents.llm import (
    CappedClient,
    CapReached,
    DailyLimitReached,
    LLMConfigError,
    ResilientClient,
    RetryPolicy,
)


def test_cap_is_enforced_before_the_network_and_usage_is_summed() -> None:
    sent: list[dict[str, Any]] = []

    def create(**request: Any) -> Any:
        sent.append(request)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=2, model_extra={"cost": 0.5})
        return SimpleNamespace(choices=[], usage=usage)

    inner = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client = CappedClient(inner, cap=3)
    for _ in range(3):
        client.chat.completions.create(model="m")
    for _ in range(2):
        with pytest.raises(CapReached):
            client.chat.completions.create(model="m")
    assert len(sent) == 3 and client.requests == 3 and client.refused == 2
    assert (client.prompt_tokens, client.completion_tokens, client.cost) == (30, 6, 1.5)


# --- Pacing and retries for failed requests (human decision 2026-10-25) -----------------------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


class HTTPError(Exception):
    def __init__(self, status: int, message: str = "", retry_after: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status
        self.body = {"message": message}
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers)


def scripted_inner(outcomes: list[Any]) -> tuple[Any, list[int]]:
    calls: list[int] = []

    def create(**_: Any) -> Any:
        calls.append(1)
        out = outcomes.pop(0) if outcomes else "ok"
        if isinstance(out, Exception):
            raise out
        return out

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), calls


def resilient(outcomes: list[Any], **policy: Any) -> tuple[ResilientClient, Clock, list[int]]:
    clock = Clock()
    inner, calls = scripted_inner(outcomes)
    client = ResilientClient(inner, RetryPolicy(**policy), sleep=clock.sleep, clock=clock.time)
    return client, clock, calls


def test_pacing_keeps_at_most_15_requests_in_any_minute() -> None:
    client, clock, calls = resilient([])
    for _ in range(31):
        client.create(model="m")
    assert len(calls) == 31
    assert clock.sleeps == [60.0, 60.0]  # before the 16th and the 31st request
    assert client.paced_seconds == 120.0


def test_429_waits_for_retry_after_and_5xx_backs_off_never_immediately() -> None:
    client, clock, calls = resilient(
        [HTTPError(429, "Rate limit exceeded: free-models-per-min.", retry_after="7"),
         HTTPError(502, "Provider returned error"), "ok"]
    )  # fmt: skip
    assert client.create(model="m") == "ok"
    assert clock.sleeps == [7.0, 15.0]  # Retry-After first; then the second backoff step
    assert client.retries == 2 and client.failures == {"HTTP 429": 1, "HTTP 502": 1}
    assert len(calls) == 3


def test_at_most_three_retries_then_the_error_is_raised() -> None:
    client, clock, calls = resilient([HTTPError(503)] * 10)
    with pytest.raises(HTTPError):
        client.create(model="m")
    assert len(calls) == 4 and clock.sleeps == [5.0, 15.0, 45.0]


def test_daily_limit_stops_at_once_and_other_errors_are_not_retried() -> None:
    client, clock, calls = resilient([HTTPError(429, "Rate limit exceeded: free-models-per-day")])
    with pytest.raises(DailyLimitReached):
        client.create(model="m")
    assert len(calls) == 1 and clock.sleeps == []
    client, clock, calls = resilient([HTTPError(400, "bad request")])
    with pytest.raises(HTTPError):
        client.create(model="m")
    assert len(calls) == 1 and clock.sleeps == []
    capped = CappedClient(scripted_inner([])[0], cap=1)
    paced = ResilientClient(capped, RetryPolicy(), sleep=Clock().sleep, clock=Clock().time)
    paced.create(model="m")
    with pytest.raises(CapReached):  # the cap counts retries and is never retried
        paced.create(model="m")
    assert paced.retries == 0


def test_daily_limit_propagates_through_the_agent(tmp_path: Path) -> None:
    from cascadeguard.agents.cache import DecisionCache
    from cascadeguard.agents.llm import LLMAgent
    from cascadeguard.cli import load_world

    view = load_world("uae_health_access").baseline().views[0]
    client, _, _ = resilient([HTTPError(429, "free-models-per-day")])
    agent = LLMAgent(view.role_id, "test/model", client, DecisionCache(tmp_path), ())
    with pytest.raises(DailyLimitReached):
        agent.observe(view)
    assert not list(tmp_path.glob("*.json"))


def test_retry_policy_comes_from_code_defaults_or_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absent = tmp_path / "absent.env"
    assert RetryPolicy.from_env(absent) == RetryPolicy(15, 3, (5.0, 15.0, 45.0))
    env = tmp_path / ".env"
    env.write_text(
        "CASCADEGUARD_REQUESTS_PER_MINUTE=10\nCASCADEGUARD_BACKOFF_SECONDS=2,4\n", encoding="utf-8"
    )
    assert RetryPolicy.from_env(env) == RetryPolicy(10, 3, (2.0, 4.0))
    monkeypatch.setenv("CASCADEGUARD_BACKOFF_SECONDS", "0,5")
    with pytest.raises(LLMConfigError, match="no immediate retries"):
        RetryPolicy.from_env(env)


def test_a_retried_5xx_uses_up_the_cap_and_no_wait_is_spent_past_it() -> None:
    clock = Clock()
    inner, calls = scripted_inner([HTTPError(502), HTTPError(502), "ok"])
    capped = CappedClient(inner, cap=2)
    client = ResilientClient(capped, RetryPolicy(), sleep=clock.sleep, clock=clock.time)
    with pytest.raises(CapReached):
        client.create(model="m")
    assert len(calls) == 2 and capped.requests == 2  # the first send and one retry
    assert client.retries == 1  # the refused retry is not counted
    assert clock.sleeps == [5.0]  # no backoff slept for the refused retry
    # Once spent, further requests are refused without pacing waits.
    for _ in range(40):
        with pytest.raises(CapReached):
            client.create(model="m")
    assert client.paced_seconds == 0.0
