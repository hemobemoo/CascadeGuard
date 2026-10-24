"""The capped client of scripts/llm_baseline.py: no request past the approved cap."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "llm_baseline.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("llm_baseline", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cap_is_enforced_before_the_network_and_usage_is_summed() -> None:
    baseline = _module()
    sent: list[dict[str, Any]] = []

    def create(**request: Any) -> Any:
        sent.append(request)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=2, model_extra={"cost": 0.5})
        return SimpleNamespace(choices=[], usage=usage)

    inner = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client = baseline.CappedClient(inner, cap=3)
    for _ in range(3):
        client.chat.completions.create(model="m")
    for _ in range(2):
        with pytest.raises(baseline.CapReached):
            client.chat.completions.create(model="m")
    assert len(sent) == 3 and client.requests == 3 and client.refused == 2
    assert (client.prompt_tokens, client.completion_tokens, client.cost) == (30, 6, 1.5)
