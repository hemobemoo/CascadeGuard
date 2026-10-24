"""No test may reach a live LLM: the real .env is never read and no SDK client is built."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import cascadeguard.agents.llm as llm


@pytest.fixture(autouse=True)
def no_live_llm(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    for name in llm.ENV_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "ENV_FILE", Path(tmp_path_factory.mktemp("env")) / "absent.env")

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("tests must not build a live LLM client")

    monkeypatch.setattr(llm, "make_client", refuse)
    yield
