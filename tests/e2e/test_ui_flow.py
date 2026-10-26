"""Browser tests of the demo UI v2 (spec 006): guided flow, expert mode, exports, LLM (cached
only), and the performance budget (Playwright, Chromium).

CI always runs it. Locally: `uv run pytest -m "not e2e"` skips it; running it needs
`uv run playwright install chromium` once. Budgets are multiplied by CASCADEGUARD_PERF_FACTOR
(default 1; CI sets 3); every measured number and the budget applied are printed.
"""

import os
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Locator, Page, expect, sync_playwright

from cascadeguard.cli import main
from cascadeguard.engine.repair_search import MASKED_LABEL
from cascadeguard.simulation.replay import REPAIR_LABEL
from cascadeguard.storage.export import DISCLAIMER
from cascadeguard.ui.view_model import SMALLEST_SAFE

pytestmark = pytest.mark.e2e

SCENARIO = "uae_health_access"
TOP = (
    "owner.reverse_automated_lockouts.health_service_operator.30m"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)
TIMEOUT_MS = 60_000
FACTOR = float(os.environ.get("CASCADEGUARD_PERF_FACTOR", "1"))
PAINT_BUDGET_MS = 1500 * FACTOR
CLICK_BUDGET_MS = 200 * FACTOR


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# Starts the UI with no CASCADEGUARD_MODEL anywhere: not in the environment, and .env pointed at
# a file that does not exist.
NO_MODEL_LAUNCHER = (
    "from pathlib import Path; import cascadeguard.agents.llm as llm; "
    "llm.ENV_FILE = Path('no-such-dir') / '.env'; "
    "from cascadeguard.ui import app; app.main()"
)


def _serve(model: str | None) -> Iterator[str]:
    port = _free_port()
    # Without pytest's variables: NiceGUI switches to its own test mode when it sees them.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["CASCADEGUARD_UI_PORT"] = str(port)
    env["CASCADEGUARD_OUTPUT_MODE"] = "json_schema"
    env.pop("CASCADEGUARD_MODEL", None)
    if model is not None:
        env["CASCADEGUARD_MODEL"] = model
    command = ["-m", "cascadeguard.ui.app"] if model is not None else ["-c", NO_MODEL_LAUNCHER]
    process = subprocess.Popen(
        [sys.executable, *command],
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
def server() -> Iterator[str]:
    # LLM mode is only exercised from the cache, under a model id that has no cache entries.
    yield from _serve("test/e2e-no-such-model")


@pytest.fixture(scope="module")
def server_without_model() -> Iterator[str]:
    yield from _serve(None)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(server: str, browser: Browser) -> Iterator[Page]:
    context = browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(server)
    pg.locator(".cg-verdict").wait_for()
    pg.locator(".cg-lanes").first.wait_for(state="attached")  # the other sections have streamed in
    yield pg
    context.close()


def section(page: Page, key: str) -> Locator:
    return page.locator(f'[data-testid="section-{key}"]')


def _download(page: Page, button: str, target: Path) -> str:
    with page.expect_download() as info:
        page.get_by_role("button", name=button, exact=True).click()
    info.value.save_as(target)
    return target.read_text(encoding="utf-8")


def test_guided_flow_a_to_f(page: Page, tmp_path: Path) -> None:
    # Opens precomputed: the verdict is on screen without any click; disclaimer always visible.
    expect(page.get_by_text(DISCLAIMER).first).to_be_visible()
    expect(page.locator('[data-testid="clause-set"]')).to_contain_text("policies/reviewed")
    a = section(page, "a")
    expect(a).to_be_visible()
    expect(page.locator('[data-testid="verdict-badge"]')).to_have_text(SMALLEST_SAFE)
    expect(page.locator('[data-testid="verdict-outcome"]')).to_contain_text(
        "resolved (all critical goals met; masked failures may remain)"
    )
    for key in "bcdef":
        expect(section(page, key)).to_be_hidden()

    # b. Swimlanes: facts per role; the health operator's obligations with source labels.
    page.get_by_role("button", name="Next").click()
    b = section(page, "b")
    expect(b).to_be_visible()
    expect(a).to_be_hidden()
    expect(b.get_by_text("locked_account_records").first).to_be_visible()
    expect(b.get_by_text("dha.pp11.4-18-4").first).to_be_visible()
    expect(b.get_by_text("reviewed (interpreted)").first).to_be_visible()
    page.locator('[data-testid="cell-baseline-health_service_operator-30"]').click()
    view = page.locator('[data-testid="role-view"]')
    expect(view).to_contain_text("Role view: health_service_operator at T+30")
    expect(view).to_contain_text("Data categories outside its boundary")
    # In the baseline the network status is outside the health operator's boundary.
    expect(view.get_by_text("network_incident_status", exact=True)).to_be_visible()
    page.get_by_text("Replay (selected repair)").click()
    expect(b.get_by_text(REPAIR_LABEL).first).to_be_visible()
    expect(b.get_by_text("fulfilled at T+60").first).to_be_visible()

    # c. Cascade graph renders; highlighting changes its options in place.
    page.get_by_role("button", name="Next").click()
    c = section(page, "c")
    expect(c.locator("canvas").first).to_be_visible()
    handle = c.locator('[data-testid="graph"]').element_handle()
    c.locator(".q-field", has_text="Highlight").click()
    page.get_by_role("option", name="orphan_duty:reverse_automated_lockouts").click()
    expect(c.locator(".q-field", has_text="Highlight")).to_contain_text("reverse_automated")
    assert handle is not None and handle.evaluate("e => e.isConnected")  # never rebuilt

    # d. Diagnosis: one card per category, evidence chips with status labels.
    page.get_by_role("button", name="Next").click()
    d = section(page, "d")
    for category in (
        "orphan_duty",
        "mandate_overlap",
        "information_deadlock",
        "temporal_infeasibility",
        "undefined_trigger",
    ):
        expect(d.locator(f'[data-testid="category-{category}"]')).to_be_visible()
    expect(d.get_by_text("dha.pp11.4-18-1").first).to_be_visible()
    expect(d.locator('[data-testid="category-mandate_overlap"]')).to_contain_text("none found")

    # e. Repair ladder: rank 1 badged, requires authorization, roles touched.
    page.get_by_role("button", name="Next").click()
    rung = page.locator('[data-testid="rung-1"]')
    expect(rung).to_contain_text(SMALLEST_SAFE)
    expect(rung).to_contain_text("requires authorization")
    expect(rung).to_contain_text("roles touched: health_service_operator, telecom_operator")
    expect(page.locator('[data-testid="rung-2"]')).not_to_contain_text(SMALLEST_SAFE)

    # f. Split screen for the top repair.
    page.get_by_role("button", name="Next").click()
    f = section(page, "f")
    expect(f.locator('[data-testid="comparison-id"]')).to_have_text(TOP)
    expect(f.get_by_text("patient_access_restored: met at T+60")).to_be_visible()
    expect(f.get_by_text(MASKED_LABEL).first).to_be_visible()
    expect(f.get_by_text(f"[{REPAIR_LABEL}]").first).to_be_visible()

    # g. Exports equal the CLI's (unchanged builders).
    cli = tmp_path / "cli"
    assert main(["run", SCENARIO, "--repair", TOP, "--export", str(cli)]) == 0
    name = f"{SCENARIO}-replay-{TOP}"
    for button, suffix in (("Replay JSON", "json"), ("Replay Markdown", "md")):
        got = _download(page, button, tmp_path / f"ui.{suffix}")
        assert got == (cli / f"{name}.{suffix}").read_text(encoding="utf-8"), button


def test_expert_mode_shows_every_section(page: Page) -> None:
    page.get_by_text("Expert", exact=True).click()
    for key in "abcdefgx":
        expect(section(page, key)).to_be_visible()
    expect(section(page, "x")).to_contain_text("draft clauses not loaded")
    expect(section(page, "x")).to_contain_text("[reviewed (interpreted)]")
    # Compare another repair: the ladder highlights it in place; the split screen follows.
    page.locator('[data-testid="rung-2"]').get_by_role("button", name="Compare").click()
    expect(page.locator('[data-testid="rung-2"]')).to_have_class("cg-rung cg-rung-selected")
    expect(page.locator('[data-testid="comparison-id"]')).not_to_have_text(TOP)


def test_llm_cached_mode_never_calls_and_shows_the_agents_row(page: Page) -> None:
    page.get_by_text("Expert", exact=True).click()
    page.get_by_text("LLM (cached only)", exact=True).click()
    agents = page.locator('[data-testid="agents-label"]')
    expect(agents).to_contain_text("LLM agents (model from CASCADEGUARD_MODEL")
    expect(agents).to_contain_text("offline: decision cache only")
    expect(agents).to_contain_text("0 steps reused")  # baseline and every replay: no entry
    # No step is cached under this model id: every replay is inconclusive, never ranked.
    expect(page.locator('[data-testid="inconclusive"]')).to_be_visible()
    expect(page.locator('[data-testid="incomplete"]')).to_be_visible()
    page.locator('[data-testid="inconclusive"]').get_by_role("button", name="Compare").first.click()
    row = page.locator('[data-testid="agents-row"]')
    expect(row).to_contain_text("Same repair, scripted vs LLM agents")
    expect(row).to_contain_text("LLM (cached): inconclusive")
    expect(page.locator('[data-testid="agents-finding"]')).to_have_count(0)  # no match: nothing
    expect(page.get_by_text("LLM (live", exact=False)).to_have_count(0)  # no live mode in the UI
    page.get_by_text("Scripted", exact=True).click()
    expect(agents).to_contain_text("scripted agents")


def _median_ms(label: str, budget: float, runs: list[float]) -> None:
    median = statistics.median(runs)
    print(
        f"{label}: median {median:.0f} ms (runs {', '.join(f'{r:.0f}' for r in runs)}); "
        f"budget {budget:.0f} ms (factor {FACTOR:g})"
    )
    assert median < budget, label


def test_performance_budget(server: str, browser: Browser) -> None:
    paints: list[float] = []
    for _ in range(6):  # one warm-up, then five measured
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = context.new_page()
        start = time.perf_counter()
        pg.goto(server)
        pg.locator(".cg-verdict").wait_for()
        paints.append((time.perf_counter() - start) * 1000)
        context.close()
    _median_ms("first meaningful paint (verdict, no click)", PAINT_BUDGET_MS, paints[1:])

    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(server)
    pg.locator(".cg-lanes").first.wait_for(state="attached")

    def measure(label: str, action: Callable[[], object], reset: Callable[[], object]) -> None:
        runs: list[float] = []
        for _ in range(6):  # one warm-up, then five measured
            reset()
            pg.wait_for_timeout(500)  # sections streamed by the reset click finish first
            start = time.perf_counter()
            action()
            runs.append((time.perf_counter() - start) * 1000)
        _median_ms(label, CLICK_BUDGET_MS, runs[1:])

    def to(key: str) -> Callable[[], object]:
        return lambda: pg.locator(f'[data-testid="step-{key}"]').click()

    measure(
        "stepper: a -> b",
        lambda: (to("b")(), section(pg, "b").wait_for(state="visible")),
        lambda: (to("a")(), section(pg, "a").wait_for(state="visible")),
    )
    measure(
        "swimlane cell -> role view",
        lambda: (
            pg.locator('[data-testid="cell-baseline-telecom_operator-30"]').click(),
            pg.get_by_text("Role view: telecom_operator at T+30").wait_for(),
        ),
        lambda: (
            to("b")(),
            pg.locator('[data-testid="cell-baseline-telecom_operator-30"]').click()
            if pg.locator('[data-testid="role-view"]').count()
            else None,
            pg.locator('[data-testid="role-view"]').wait_for(state="detached"),
        ),
    )
    measure(
        "swimlane switch: baseline -> replay",
        lambda: (
            pg.locator('[data-testid="lanes-run"]').get_by_text("Replay (selected repair)").click(),
            pg.locator('[data-testid="lanes-replay"]').wait_for(state="visible"),
        ),
        lambda: (
            to("b")(),
            pg.locator('[data-testid="lanes-run"]').get_by_text("Baseline").click(),
            pg.locator('[data-testid="lanes-replay"]').wait_for(state="hidden"),
        ),
    )
    pg.get_by_text("Expert", exact=True).click()
    section(pg, "c").wait_for(state="visible")
    picker = section(pg, "c").locator(".q-field", has_text="Highlight")
    measure(
        "graph highlight (in place)",
        lambda: (
            pg.locator('[data-testid="section-d"] button', has_text="orphan_duty:activate").click(),
            picker.filter(has_text="activate_fallback").wait_for(),
        ),
        lambda: (
            picker.click(),
            pg.get_by_role("option", name="all diagnosed failures").click(),
            picker.filter(has_text="all diagnosed failures").wait_for(),
        ),
    )
    pg.get_by_text("Guided", exact=True).click()

    def reset_compare() -> None:
        to("e")()
        rung = pg.locator('[data-testid="rung-1"]')
        rung.wait_for(state="visible")
        rung.get_by_role("button", name="Compare").click()
        to("e")()
        rung.wait_for(state="visible")

    measure(
        "Compare -> split screen",
        lambda: (
            pg.locator('[data-testid="rung-3"]').get_by_role("button", name="Compare").click(),
            pg.locator('[data-testid="comparison-id"]', has_text="trigger.review").wait_for(),
        ),
        reset_compare,
    )
    measure(
        "agents: Scripted -> LLM (cached only), verdict updated",
        lambda: (
            pg.get_by_text("LLM (cached only)", exact=True).click(),
            pg.locator('[data-testid="verdict-outcome"]', has_text="no complete replay").wait_for(),
        ),
        lambda: (
            to("a")(),
            pg.get_by_text("Scripted", exact=True).click(),
            pg.locator('[data-testid="verdict-outcome"]', has_text="resolved").wait_for(),
        ),
    )
    context.close()


def test_llm_mode_without_a_model_shows_no_result(
    server_without_model: str, browser: Browser
) -> None:
    """Never a silent fallback: with no model configured, the LLM toggle shows the error and no
    verdict, ladder or scripted-vs-LLM row (spec 005: every result says which agents made it)."""
    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(server_without_model)
    pg.locator(".cg-lanes").first.wait_for(state="attached")
    pg.get_by_text("Expert", exact=True).click()
    pg.get_by_text("LLM (cached only)", exact=True).click()
    error = pg.locator('[data-testid="verdict-error"]')
    expect(error).to_contain_text("CASCADEGUARD_MODEL")
    expect(error).to_contain_text("no default model is used")
    expect(pg.locator('[data-testid="agents-label"]')).to_contain_text("CASCADEGUARD_MODEL")
    for gone in ("verdict-outcome", "verdict-badge", "rung-1", "agents-row", "comparison-id"):
        expect(pg.locator(f'[data-testid="{gone}"]')).to_have_count(0)
    expect(pg.locator(".cg-lanes")).to_have_count(0)
    # Back to scripted: its results return.
    pg.get_by_text("Scripted", exact=True).click()
    expect(pg.locator('[data-testid="verdict-badge"]')).to_have_text(SMALLEST_SAFE)
    expect(pg.locator('[data-testid="verdict-error"]')).to_have_count(0)
    context.close()
