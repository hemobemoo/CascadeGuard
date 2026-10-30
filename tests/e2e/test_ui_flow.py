"""Browser tests of the demo UI v2 (spec 006): guided flow, expert mode, exports, LLM (cached
only), and the performance budget (Playwright, Chromium).

CI always runs it. Locally: `uv run pytest -m "not e2e"` skips it; running it needs
`uv run playwright install chromium` once. Budgets are multiplied by CASCADEGUARD_PERF_FACTOR
(default 1; CI sets 3); every measured number and the budget applied are printed. The timing
test is also marked `perf`: CI always runs it; locally it runs in the full check and
`-m "not perf"` skips it.
"""

import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from playwright.sync_api import Browser, Locator, Page, expect, sync_playwright

from cascadeguard.agents.cache import DecisionCache
from cascadeguard.agents.llm import LLMAgent
from cascadeguard.cli import load_world, main, search_repairs
from cascadeguard.domain.decisions import AgentDecision
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


# Starts the UI with LLM (cached only) reading the decision cache in sys.argv[1] (a recorded
# test cache), never data/llm_cache.
RECORDED_LAUNCHER = (
    "import sys; from pathlib import Path; from cascadeguard import cli; "
    "from cascadeguard.ui import app; d = Path(sys.argv[1]); "
    "app.agent_choice = lambda m: cli.AgentChoice(cli.SCRIPTED) if m == 'scripted' "
    "else cli.AgentChoice(cli.LLM, offline=True, cache_dir=d); app.main()"
)
RECORDED_MODEL = "test/e2e-recorded-scripted"  # never a real model id; no call is ever made


def _payload(decision: AgentDecision) -> str:
    """A decision as the model would send it (json_schema shape)."""
    return json.dumps(
        {
            "proposed_actions": [
                {
                    "action_type": a.action_type,
                    "target": a.target,
                    "parameters": [{"name": k, "value": v} for k, v in a.parameters.items()],
                }
                for a in decision.proposed_actions
            ],
            "rationale": decision.rationale,
            "citations": [c.model_dump() for c in decision.citations],
            "uncertainty": list(decision.uncertainty),
            "gap_claims": [g.model_dump() for g in decision.gap_claims],
        }
    )


def _record_cache(directory: Path, model: str = "", baseline_only: bool = False) -> None:
    """Fill a decision cache with the scripted decisions, through a stand-in client (no API
    call), for the baseline and every replay of the repair search (or the baseline only)."""
    world = load_world(SCENARIO)
    base_views = world.baseline().views

    def create(**request: Any) -> Any:
        v = json.loads(request["messages"][1]["content"])
        view = next(x for x in base_views if x.role_id == v["role_id"] and x.minute == v["minute"])
        message = SimpleNamespace(content=_payload(world.agents[v["role_id"]].observe(view)))
        usage = SimpleNamespace(prompt_tokens=0, completion_tokens=0, model_extra={})
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    client = cast(
        Any, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    )
    cache = DecisionCache(directory)
    roles = tuple(r.id for r in world.roles.roles)
    agents = {
        r: LLMAgent(r, model or RECORDED_MODEL, client, cache, roles, output_mode="json_schema")
        for r in roles
    }
    recorded = replace(world, agents=dict(agents), cache=cache)
    if baseline_only:
        recorded.baseline()
    else:
        search_repairs(SCENARIO, world=recorded)


def _serve(model: str | None, launcher: list[str] | None = None) -> Iterator[str]:
    port = _free_port()
    # Without pytest's variables: NiceGUI switches to its own test mode when it sees them.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["CASCADEGUARD_UI_PORT"] = str(port)
    env["CASCADEGUARD_OUTPUT_MODE"] = "json_schema"
    env.pop("CASCADEGUARD_MODEL", None)
    if model is not None:
        env["CASCADEGUARD_MODEL"] = model
    command = ["-m", "cascadeguard.ui.app"] if model is not None else ["-c", NO_MODEL_LAUNCHER]
    command = launcher or command
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
def server_recorded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    cache = tmp_path_factory.mktemp("recorded_cache")
    _record_cache(cache)
    yield from _serve(RECORDED_MODEL, ["-c", RECORDED_LAUNCHER, str(cache)])


@pytest.fixture(scope="module")
def server_baseline_cached(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Only the baseline is cached: every replay whose views change misses (inconclusive)."""
    cache = tmp_path_factory.mktemp("baseline_cache")
    _record_cache(cache, "test/e2e-recorded-baseline-only", baseline_only=True)
    yield from _serve("test/e2e-recorded-baseline-only", ["-c", RECORDED_LAUNCHER, str(cache)])


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
    expect(page.locator('[data-testid="verdict-authorization"]')).to_contain_text(
        "requires authorization (needs human and institutional approval)"
    )
    expect(page.locator('[data-testid="verdict-outcome"]')).to_contain_text(
        "resolved (all critical goals met; masked failures may remain)"
    )
    # Spec 006b: the incident in one sentence; the best repair in plain language, id below.
    expect(page.locator('[data-testid="incident-summary"]')).to_contain_text(
        "Hypothetical scenario with synthetic data"
    )
    expect(page.locator('[data-testid="verdict-edit"]').first).to_have_text(
        "Assign reverse automated lockouts to Health Service Operator, 30-minute deadline "
        f"[{REPAIR_LABEL}]"
    )
    expect(a.get_by_text(TOP, exact=True)).to_be_visible()
    for key in "bcdef":
        expect(section(page, key)).to_be_hidden()

    # b. Swimlanes: facts per role; the health operator's obligations with source labels.
    page.get_by_role("button", name="Next").click()
    b = section(page, "b")
    expect(b).to_be_visible()
    expect(a).to_be_hidden()
    # Names first; the raw fact id is only in the tooltip and in Expert mode (spec 006b).
    expect(b.get_by_text("Health Service Operator", exact=True).first).to_be_visible()
    expect(b.get_by_text("Patient account records").first).to_be_visible()
    expect(b.get_by_text("locked_account_records").first).to_be_hidden()
    # Clause ids and status labels stay verbatim.
    expect(b.get_by_text("dha.pp11.4-18-4").first).to_be_visible()
    expect(b.get_by_text("reviewed (interpreted)").first).to_be_visible()
    page.locator('[data-testid="cell-baseline-health_service_operator-30"]').click()
    view = page.locator('[data-testid="role-view"]')
    expect(view).to_contain_text("Role view: Health Service Operator at T+30")
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
    assert handle is not None
    sizes = (
        "e => Object.fromEntries(getElement(e).chart.getOption().series[0].data"
        ".map(n => [n.id, n.symbolSize]))"
    )
    opacity = (
        "e => Object.fromEntries(getElement(e).chart.getOption().series[0].data"
        ".map(n => [n.id, (n.itemStyle || {}).opacity ?? 1]))"
    )
    names = (
        "e => Object.fromEntries(getElement(e).chart.getOption().series[0].data"
        ".map(n => [n.id, n.name]))"
    )
    assert handle.evaluate(names)["action:reverse_automated_lockouts"] == (
        "Reverse automated lockouts"
    )
    # Spec 006b: the graph opens on one failure (the first diagnosis card's), the rest faded.
    picker = c.locator(".q-field", has_text="Highlight")
    expect(picker).to_contain_text("orphan duty: Activate fallback channel")
    opened, opened_opacity = handle.evaluate(sizes), handle.evaluate(opacity)
    assert opened["action:activate_fallback_channel"] == 26
    assert opened["category:network_incident_status"] == 12
    assert opened_opacity["category:network_incident_status"] == 0.15
    # "All diagnosed failures": every failure highlighted, nothing faded.
    picker.click()
    page.get_by_role("option", name="all diagnosed failures").click()
    page.wait_for_function(f"() => {GRAPH_FADED} === false")
    before = handle.evaluate(sizes)
    assert before["category:network_incident_status"] == 26
    assert all(v == 1 for v in handle.evaluate(opacity).values())
    picker.click()
    page.get_by_role("option", name="orphan duty: Reverse automated lockouts").click()
    expect(picker).to_contain_text("Reverse automated lockouts")
    page.wait_for_function(
        "() => getElement(document.querySelector('[data-testid=graph]')).chart.getOption()"
        ".series[0].data"
        ".find(n => n.id === 'category:network_incident_status').symbolSize === 12"
    )
    after = handle.evaluate(sizes)
    assert after["category:network_incident_status"] == 12  # not part of this failure
    assert after["action:reverse_automated_lockouts"] == 26
    # Everything outside the selected failure's subgraph is faded; the toggle shows it all.
    faded = handle.evaluate(opacity)
    assert faded["category:network_incident_status"] == 0.15
    assert faded["action:reverse_automated_lockouts"] == 1
    c.locator('[data-testid="graph-show-all"]').click()
    page.wait_for_function(
        "() => (getElement(document.querySelector('[data-testid=graph]')).chart.getOption()"
        ".series[0].data.find(n => n.id === 'category:network_incident_status').itemStyle"
        " || {}).opacity === undefined"
    )
    assert handle.evaluate(sizes)["action:reverse_automated_lockouts"] == 26  # still highlighted
    assert handle.evaluate("e => e.isConnected")  # the same chart, updated in place

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
    expect(
        d.locator('[data-testid="failure-orphan_duty:reverse_automated_lockouts"]')
    ).to_have_text("Reverse automated lockouts")
    expect(d.locator('[data-testid="category-mandate_overlap"]')).to_contain_text("none found")

    # e. Repair ladder: rank 1 badged, requires authorization, roles touched.
    page.get_by_role("button", name="Next").click()
    rung = page.locator('[data-testid="rung-1"]')
    expect(rung).to_contain_text(SMALLEST_SAFE)
    expect(rung).to_contain_text("requires authorization")
    expect(rung).to_contain_text("roles touched: Health Service Operator, Telecom Operator")
    expect(rung).to_contain_text(
        "Allow Telecom Operator to share network incident status with Health Service Operator "
        "(minimum data share)"
    )
    expect(rung.get_by_text(TOP, exact=True)).to_be_visible()  # the id, in small print
    expect(page.locator('[data-testid="rung-2"]')).not_to_contain_text(SMALLEST_SAFE)
    # Top 3 only; the rest behind "Show all N".
    expect(page.locator('[data-testid="rung-3"]')).to_be_visible()
    expect(page.locator('[data-testid="rung-4"]')).to_be_hidden()
    toggle = page.locator('[data-testid="ladder-toggle"]')
    expect(toggle).to_have_text(re.compile(r"Show all \d+"))
    toggle.click()
    expect(page.locator('[data-testid="rung-4"]')).to_be_visible()
    expect(toggle).to_have_text("Show top 3")
    toggle.click()
    expect(page.locator('[data-testid="rung-4"]')).to_be_hidden()

    # f. Split screen for the top repair.
    page.get_by_role("button", name="Next").click()
    f = section(page, "f")
    expect(f.locator('[data-testid="comparison-id"]')).to_have_text(TOP)
    expect(f.get_by_text("Patient access restored: met at T+60")).to_be_visible()
    expect(f.get_by_text(MASKED_LABEL).first).to_be_visible()
    expect(f.locator('[data-testid="comparison-edit"]').first).to_have_text(
        "Assign reverse automated lockouts to Health Service Operator, 30-minute deadline "
        f"[{REPAIR_LABEL}]"
    )

    # g. Exports equal the CLI's (unchanged builders).
    cli = tmp_path / "cli"
    assert main(["run", SCENARIO, "--repair", TOP, "--export", str(cli)]) == 0
    name = f"{SCENARIO}-replay-{TOP}"
    for button, suffix in (("Replay JSON", "json"), ("Replay Markdown", "md")):
        got = _download(page, button, tmp_path / f"ui.{suffix}")
        assert got == (cli / f"{name}.{suffix}").read_text(encoding="utf-8"), button


def test_governance_off_step_shows_the_comparison(page: Page) -> None:
    """PR 4: the governed and ungoverned runs side by side, the ungoverned one labelled
    comparison only, with what was applied only because governance was off."""
    page.locator('[data-testid="step-h"]').click()
    h = section(page, "h")
    expect(h).to_be_visible()
    expect(section(page, "f")).to_be_hidden()
    expect(h.locator('[data-testid="governance-banner"]')).to_have_text(
        "Governance off: comparison only, not the governed result."
    )
    split = h.locator('[data-testid="governance"]')
    expect(split.get_by_text("Governed (the result)")).to_be_visible()
    expect(split.get_by_text("Ungoverned (comparison only)")).to_be_visible()
    expect(split.get_by_text("Patient access restored: unmet")).to_be_visible()
    expect(split.get_by_text("Patient access restored: met at T+60")).to_be_visible()
    expect(split.get_by_text("goal met but the cause is still present").first).to_be_visible()
    waived = h.locator('[data-testid="governance-waived"]')
    expect(waived).to_contain_text("would have been rejected (missing_information, no_authority)")
    expect(waived).to_contain_text("[reviewed (interpreted) · binding unknown]")
    page.get_by_text("Expert", exact=True).click()
    expect(h).to_be_visible()


def test_expert_mode_shows_every_section(page: Page) -> None:
    page.get_by_text("Expert", exact=True).click()
    for key in "abcdefgx":
        expect(section(page, key)).to_be_visible()
    expect(section(page, "x")).to_contain_text("draft clauses not loaded")
    expect(section(page, "x")).to_contain_text("[reviewed (interpreted) · binding unknown]")
    # Expert mode shows the raw ids next to the names (spec 006b).
    expect(section(page, "b").get_by_text("locked_account_records").first).to_be_visible()
    expect(section(page, "d").get_by_text("orphan_duty:reverse_automated_lockouts")).to_be_visible()
    page.get_by_text("Guided", exact=True).click()
    page.get_by_text("Expert", exact=True).click()
    expect(section(page, "b").get_by_text("locked_account_records").first).to_be_visible()
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
    # The incomplete-run banner is repeated where the baseline's diagnosis is shown.
    expect(section(page, "d").locator('[data-testid="incomplete-note"]')).to_be_visible()
    page.locator('[data-testid="inconclusive"]').get_by_role("button", name="Compare").first.click()
    row = page.locator('[data-testid="agents-row"]')
    expect(row).to_contain_text("Same repair, scripted vs LLM agents")
    expect(row).to_contain_text("LLM (cached): inconclusive")
    expect(page.locator('[data-testid="agents-finding"]')).to_have_count(0)  # no match: nothing
    expect(page.get_by_text("LLM (live", exact=False)).to_have_count(0)  # no live mode in the UI
    page.get_by_text("Scripted", exact=True).click()
    expect(agents).to_contain_text("scripted agents")


# Whether the graph fades what is outside the highlighted subgraph (any node at opacity 0.15).
GRAPH_FADED = (
    "getElement(document.querySelector('[data-testid=graph]')).chart.getOption().series[0].data"
    ".some(n => (n.itemStyle || {}).opacity === 0.15)"
)


def _median_ms(label: str, budget: float, runs: list[float]) -> float:
    median = statistics.median(runs)
    print(
        f"{label}: median {median:.0f} ms (runs {', '.join(f'{r:.0f}' for r in runs)}); "
        f"budget {budget:.0f} ms (factor {FACTOR:g})"
    )
    return median


@pytest.mark.perf
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
    label = "first meaningful paint (verdict, no click)"
    assert _median_ms(label, PAINT_BUDGET_MS, paints[1:]) < PAINT_BUDGET_MS, label

    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(server)
    pg.locator(".cg-lanes").first.wait_for(state="attached")

    def measure(label: str, action: Callable[[], object], reset: Callable[[], object]) -> None:
        """One warm-up click (ignored), then the median of five. If that median is over budget,
        re-measure once; fail only if both medians are over (human decision 2026-10-27)."""
        for attempt in ("", " (re-measured)"):
            runs: list[float] = []
            for _ in range(6):
                reset()
                pg.wait_for_timeout(500)  # sections streamed by the reset click finish first
                start = time.perf_counter()
                action()
                runs.append((time.perf_counter() - start) * 1000)
            if _median_ms(label + attempt, CLICK_BUDGET_MS, runs[1:]) < CLICK_BUDGET_MS:
                return
        pytest.fail(f"{label}: both medians over the {CLICK_BUDGET_MS:.0f} ms budget")

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
            pg.get_by_text("Role view: Telecom Operator at T+30").wait_for(),
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
            pg.locator('[data-testid="failure-orphan_duty:activate_fallback_channel"]').click(),
            picker.filter(has_text="Activate fallback channel").wait_for(),
        ),
        lambda: (
            picker.click(),
            pg.get_by_role("option", name="all diagnosed failures").click(),
            picker.filter(has_text="all diagnosed failures").wait_for(),
        ),
    )
    show_all = section(pg, "c").locator('[data-testid="graph-show-all"]')
    measure(
        "graph: show all at full opacity",
        lambda: (
            show_all.click(),
            pg.wait_for_function(f"() => {GRAPH_FADED} === false"),
        ),
        lambda: (
            show_all.click() if pg.evaluate(f"() => {GRAPH_FADED}") is False else None,
            pg.wait_for_function(f"() => {GRAPH_FADED} === true"),
        ),
    )
    toggle = pg.locator('[data-testid="ladder-toggle"]')
    measure(
        "ladder: Show all N",
        lambda: (toggle.click(), pg.locator('[data-testid="rung-4"]').wait_for(state="visible")),
        lambda: (
            toggle.click() if pg.locator('[data-testid="rung-4"]').is_visible() else None,
            pg.locator('[data-testid="rung-4"]').wait_for(state="hidden"),
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


def test_guided_flow_with_cached_llm_agents(server_recorded: str, browser: Browser) -> None:
    """Spec 006b "Done when": the guided flow with cached LLM agents (a cache recorded from the
    scripted decisions, read offline) shows names, sentences, the top-3 ladder, the faded
    subgraph and the summary."""
    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(server_recorded)
    pg.get_by_text("LLM (cached only)", exact=True).click()
    agents = pg.locator('[data-testid="agents-label"]')
    expect(agents).to_contain_text("offline: decision cache only", timeout=TIMEOUT_MS)
    expect(agents).to_contain_text(", 0 not cached")  # every step came from the cache
    expect(pg.locator('[data-testid="incident-summary"]')).to_contain_text("Hypothetical scenario")
    expect(pg.locator('[data-testid="verdict-badge"]')).to_have_text(SMALLEST_SAFE)
    expect(pg.locator('[data-testid="verdict-edit"]').first).to_have_text(
        "Assign reverse automated lockouts to Health Service Operator, 30-minute deadline "
        f"[{REPAIR_LABEL}]"
    )
    pg.locator('[data-testid="step-b"]').click()
    expect(section(pg, "b").get_by_text("Telecom Operator", exact=True).first).to_be_visible()
    pg.locator('[data-testid="step-c"]').click()
    expect(section(pg, "c").locator(".q-field", has_text="Highlight")).to_contain_text(
        "orphan duty: Activate fallback channel"
    )
    pg.wait_for_function(f"() => {GRAPH_FADED} === true")
    pg.locator('[data-testid="step-d"]').click()
    expect(
        pg.locator('[data-testid="failure-orphan_duty:reverse_automated_lockouts"]')
    ).to_have_text("Reverse automated lockouts")
    pg.locator('[data-testid="step-e"]').click()
    expect(pg.locator('[data-testid="rung-1"]')).to_contain_text(
        "roles touched: Health Service Operator, Telecom Operator"
    )
    expect(pg.locator('[data-testid="rung-4"]')).to_be_hidden()
    expect(pg.locator('[data-testid="ladder-toggle"]')).to_have_text(re.compile(r"Show all \d+"))
    pg.locator('[data-testid="rung-1"]').get_by_role("button", name="Compare").click()
    f = section(pg, "f")
    expect(f.locator('[data-testid="comparison-edit"]').first).to_contain_text(
        "Assign reverse automated lockouts"
    )
    expect(f.get_by_text("Patient access restored: met at T+60")).to_be_visible()
    row = pg.locator('[data-testid="agents-row"]')
    expect(row).to_contain_text("Scripted: resolved")
    expect(row).to_contain_text("LLM (cached): resolved")
    context.close()


def test_inconclusive_rows_collapse_with_the_ladder(
    server_baseline_cached: str, browser: Browser
) -> None:
    """Spec 006b c: inconclusive repairs are collapsed the same way as ranked rungs."""
    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(server_baseline_cached)
    pg.get_by_text("Expert", exact=True).click()
    pg.get_by_text("LLM (cached only)", exact=True).click()
    expect(pg.locator('[data-testid="inconclusive"]')).to_be_visible(timeout=TIMEOUT_MS)
    expect(pg.locator('[data-testid="inconclusive-3"]')).to_be_visible()
    expect(pg.locator('[data-testid="inconclusive-4"]')).to_be_hidden()
    toggle = pg.locator('[data-testid="ladder-toggle"]')
    expect(toggle).to_have_text(re.compile(r"Show all \d+"))
    toggle.click()
    expect(pg.locator('[data-testid="inconclusive-4"]')).to_be_visible()
    expect(toggle).to_have_text("Show top 3")
    context.close()
