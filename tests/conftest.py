"""No test may reach a live LLM or the network: the real .env is never read, no SDK client or
CLI embedder is built, and any socket connection outside the loopback interface fails the test
(human decision 2026-11-05: no API call of any kind without the human's approval, tests and
smoke checks included). The e2e UI servers run under the same guard (tests/e2e)."""

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import cascadeguard.agents.llm as llm
import cascadeguard.cli as cli


@pytest.fixture(autouse=True)
def no_live_llm(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    for name in (
        *llm.ENV_VARIABLES,
        llm.OUTPUT_MODE_VARIABLE,
        llm.RPM_VARIABLE,
        llm.RETRIES_VARIABLE,
        llm.BACKOFF_VARIABLE,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "ENV_FILE", Path(tmp_path_factory.mktemp("env")) / "absent.env")

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("tests must not build a live LLM client")

    monkeypatch.setattr(llm, "make_client", refuse)
    # The CLI binds these names at import: refuse them there too (test-breaker, Task 1).
    monkeypatch.setattr(cli, "make_client", refuse)
    monkeypatch.setattr(cli, "OpenRouterEmbedder", refuse)
    yield


LOOPBACK = ("localhost", "::1")


def is_loopback(address: object) -> bool:
    """A socket address on this machine (127.x, ::1, localhost); a non-tuple (AF_UNIX path)
    counts as local."""
    if not isinstance(address, tuple):
        return True
    host = str(address[0])  # pyright: ignore[reportUnknownArgumentType]
    return host in LOOPBACK or host.startswith("127.") or host == "::ffff:127.0.0.1"


class NetworkBlocked(AssertionError):
    """A test tried to open a connection outside the loopback interface."""


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex

    def guarded(self: socket.socket, address: Any) -> Any:
        if not is_loopback(address):
            raise NetworkBlocked(f"tests must not reach the network (tried {address!r})")
        return connect(self, address)

    def guarded_ex(self: socket.socket, address: Any) -> Any:
        if not is_loopback(address):
            raise NetworkBlocked(f"tests must not reach the network (tried {address!r})")
        return connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_ex)
    yield
