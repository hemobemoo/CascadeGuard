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

from cascadeguard.cli import main
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

    # A role view: the health operator at T+30 sees its inject, but not network data.
    _pick(page, "Inject", "T+30")
    expect(page.get_by_text("The evidence is incomplete").first).to_be_visible()
    expect(page.get_by_text("Data categories outside its boundary")).to_be_visible()
    expect(page.get_by_text("network_incident_status", exact=True)).to_be_visible()

    # The top-ranked repair carries "requires authorization"; its rules are hypothetical.
    page.get_by_role("button", name="Find repairs").click()
    expect(page.get_by_text("repairs ranked")).to_be_visible()
    expect(page.get_by_text(f"1. {TOP}")).to_be_visible()
    expect(page.get_by_text("requires authorization").first).to_be_visible()
    page.get_by_role("button", name="Compare").first.click()

    # Baseline and replay side by side.
    expect(page.get_by_text(f"Baseline vs replay: {TOP}")).to_be_visible()
    expect(page.get_by_text(f"[{REPAIR_LABEL}]").first).to_be_visible()
    expect(page.get_by_text("patient_access_restored: met at T+60")).to_be_visible()
    expect(page.get_by_text("masked (goal met another way)").first).to_be_visible()

    # Both exports (JSON and Markdown) match what `cli --export` writes.
    cli = tmp_path / "cli"
    assert main(["run", SCENARIO, "--repair", TOP, "--export", str(cli)]) == 0
    name = f"{SCENARIO}-replay-{TOP}"
    for button, suffix in (("Replay JSON", "json"), ("Replay Markdown", "md")):
        got = _download(page, button, tmp_path / f"ui.{suffix}")
        assert got == (cli / f"{name}.{suffix}").read_text(encoding="utf-8"), button
