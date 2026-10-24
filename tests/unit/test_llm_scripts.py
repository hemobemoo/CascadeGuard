"""The capped client used by the approved live runs: no request past the cap."""

from types import SimpleNamespace
from typing import Any

import pytest

from cascadeguard.agents.llm import CappedClient, CapReached


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
