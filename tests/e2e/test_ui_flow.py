"""Browser smoke test of the demo UI's core flow (Playwright, Chromium, scripted agents).

CI always runs it. Locally: `uv run pytest -m "not e2e"` skips it; running it needs
`uv run playwright install chromium` once.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from cascadeguard.cli import load_world, main
from cascadeguard.engine.repair_search import MASKED_LABEL
from cascadeguard.simulation.replay import REPAIR_LABEL
from cascadeguard.storage.export import DISCLAIMER

pytestmark = pytest.mark.e2e

SCENARIO = "uae_health_access"
TOP = (
    "owner.reverse_automated_lockouts.health_service_operator"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)
TIMEOUT_MS = 60_000


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    port = _free_port()
    # Without pytest's variables: NiceGUI switches to its own test mode when it sees them.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["CASCADEGUARD_UI_PORT"] = str(port)
    # LLM mode is only exercised from the cache, under a model id that has no cache entries.
    env["CASCADEGUARD_MODEL"] = "test/e2e-no-such-model"
    env["CASCADEGUARD_OUTPUT_MODE"] = "json_schema"
    process = subprocess.Popen(
        [sys.executable, "-m", "cascadeguard.ui.app"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(url, timeout=2):
                    break
            except OSError:
                if time.monotonic() > deadline or process.poll() is not None:
                    raise RuntimeError("demo UI did not start") from None
                time.sleep(0.5)
        yield url
    finally:
        process.terminate()
        process.wait(timeout=30)


@pytest.fixture(scope="module")
def page(server: str) -> Iterator[Page]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1400, "height": 1000}
        )
        pg = context.new_page()
        pg.set_default_timeout(TIMEOUT_MS)
        pg.goto(server)
        yield pg
        browser.close()


def _pick(page: Page, field: str, option: str) -> None:
    page.locator(".q-field", has_text=field).first.click()
    page.get_by_role("option", name=option, exact=True).click()


def _download(page: Page, button: str, target: Path) -> str:
    with page.expect_download() as info:
        page.get_by_role("button", name=button, exact=True).click()
    info.value.save_as(target)
    return target.read_text(encoding="utf-8")


def test_core_flow_in_the_browser(page: Page, tmp_path: Path) -> None:
    # Pick the scenario and run the baseline.
    _pick(page, "Scenario", SCENARIO)
    page.get_by_role("button", name="Run baseline").click()
    expect(page.get_by_text("4 diagnosed failures")).to_be_visible()

    # The disclaimer and a clause status label are visible.
    expect(page.get_by_text(DISCLAIMER)).to_be_visible()
    expect(page.get_by_text("uae.fl2-2019.art4 [reviewed (interpreted)]").first).to_be_visible()

    # A role view: the health operator at T+30 sees its inject, but not network data. Checked
    # inside the role card only, on text that exists only at T+30.
    card = page.locator(".q-card", has_text="Role views")
    expect(card.locator(".q-field", has_text="Inject")).to_contain_text("T+00")
    _pick(page, "Inject", "T+30")
    expect(card.locator(".q-field", has_text="Inject")).to_contain_text("T+30")
    world = load_world(SCENARIO)
    expect(
        card.get_by_text(f"Simulation time: {world.scenario.time_at(30).isoformat()}")
    ).to_be_visible()
    t30 = next(e for e in world.scenario.events if e.at_minute == 30)
    expect(card.get_by_text(t30.title, exact=True)).to_be_visible()
    expect(card.get_by_text("Data categories outside its boundary")).to_be_visible()
    expect(card.get_by_text("network_incident_status", exact=True)).to_be_visible()

    # The dependency graph renders, and clicking a failure highlights it.
    graph = page.locator(".q-card", has_text="Dependency graph")
    expect(graph.locator("canvas").first).to_be_visible()
    failure = world.baseline().failures[0].id
    graph.get_by_role("button", name=f"[{failure.split(':')[0]}] {failure}").click()
    expect(graph.locator(".q-field", has_text="Highlight")).to_contain_text(failure)

    # The top-ranked repair carries "requires authorization"; its rules are hypothetical.
    page.get_by_role("button", name="Find repairs").click()
    expect(page.get_by_text("repairs ranked")).to_be_visible()
    top = page.locator("div.border-b", has_text=f"1. {TOP}")
    expect(top).to_have_count(1)
    expect(top.get_by_text("requires authorization")).to_be_visible()
    page.get_by_role("button", name="Compare").first.click()

    # Baseline and replay side by side.
    expect(page.get_by_text(f"Baseline vs replay: {TOP}")).to_be_visible()
    expect(page.get_by_text(f"[{REPAIR_LABEL}]").first).to_be_visible()
    expect(page.get_by_text("patient_access_restored: met at T+60")).to_be_visible()
    expect(page.get_by_text(MASKED_LABEL).first).to_be_visible()

    # Both exports (JSON and Markdown) match what `cli --export` writes.
    cli = tmp_path / "cli"
    assert main(["run", SCENARIO, "--repair", TOP, "--export", str(cli)]) == 0
    name = f"{SCENARIO}-replay-{TOP}"
    for button, suffix in (("Replay JSON", "json"), ("Replay Markdown", "md")):
        got = _download(page, button, tmp_path / f"ui.{suffix}")
        assert got == (cli / f"{name}.{suffix}").read_text(encoding="utf-8"), button

    # The agents toggle: LLM agents from the cache only (no call is possible). Every step is
    # a no-decision finding, and the result says which agents produced it.
    page.get_by_text("LLM (cached only)", exact=True).click()
    page.get_by_role("button", name="Run baseline").click()
    agents = page.get_by_text(
        "Agents: LLM agents (model from CASCADEGUARD_MODEL; output mode json_schema; offline"
    )
    expect(agents).to_be_visible()
    expect(agents).to_contain_text("0 steps reused, 36 not cached")
    expect(page.get_by_text("made no decision at this step (not_cached)").first).to_be_visible()
    page.get_by_text("Scripted", exact=True).click()
    page.get_by_role("button", name="Run baseline").click()
    expect(page.get_by_text("Agents: scripted agents")).to_be_visible()
