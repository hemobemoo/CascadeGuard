"""CascadeGuard demo UI v2 (Phase 6; see specs/006-demo-ui-v2.md).

The UI only displays engine results: runs, searches and replays come from the same helpers
the CLI uses, and `ui/view_model.py` formats them. No logic lives here. The scripted baseline
and repair search are computed once at startup and held in memory, so the page opens with the
verdict, diagnosis and repair ladder already rendered. LLM agents are read from the decision
cache only (no live calls in the UI; the CLI keeps live runs).
"""

import asyncio
import html
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml
from nicegui import app as nicegui_app
from nicegui import background_tasks, run, ui

from cascadeguard.agents.llm import LLMAgent, LLMConfigError
from cascadeguard.cli import LLM, SCRIPTED, AgentChoice, World, load_world, search_repairs
from cascadeguard.engine.constraints import AGENT_STATEMENT
from cascadeguard.engine.repair_search import (
    MASKED_LABEL,
    REMOVED_LABEL,
    ReplayComparison,
    SearchResult,
    outcome_definition,
)
from cascadeguard.simulation.loader import SCENARIOS_DIR
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.ui import view_model as vm

STATEMENT = AGENT_STATEMENT.split(" (", 1)[0]  # short form; the full label is the tooltip
DEFAULT_PORT = 8765  # 8080 is often taken by other local servers
PORT_VARIABLE = "CASCADEGUARD_UI_PORT"
THEME = Path(__file__).with_name("theme.css")
HIDDEN_DELAY = 0.3  # seconds before sections not on screen are refreshed after a click
FILL_DELAY = 0.15  # seconds after the websocket connects before the other sections are sent
EXPORTS = (
    "Baseline JSON",
    "Baseline Markdown",
    "Repairs JSON",
    "Repairs Markdown",
    "Replay JSON",
    "Replay Markdown",
)
AGENT_MODES = {"scripted": "Scripted", "llm-offline": "LLM (cached only)"}
STEPS = (  # (key, title, one sentence of narration) for the guided demo
    ("a", "Verdict", "What broke in the baseline, and what the best repair achieves on replay."),
    (
        "b",
        "Timeline",
        "Each role sees only what reaches it: facts, actions and obligations per inject.",
    ),
    ("c", "Cascade", "How roles, actions, data and clauses depend on each other."),
    (
        "d",
        "Diagnosis",
        "Each failure is classified, with the clauses considered and their review status.",
    ),
    ("e", "Repairs", "Candidate repairs from the closed grammar, replayed and ranked."),
    ("f", "Replay", "The identical incident with the repair applied, side by side."),
)


def agent_choice(mode: str) -> AgentChoice:
    return AgentChoice(SCRIPTED) if mode == "scripted" else AgentChoice(LLM, offline=True)


def port() -> int:
    return int(os.environ.get(PORT_VARIABLE, DEFAULT_PORT))


def scenarios() -> list[str]:
    return sorted(p.name for p in SCENARIOS_DIR.iterdir() if (p / "scenario.yaml").is_file())


def findings_for(scenario_id: str) -> tuple[vm.EvaluationFinding, ...]:
    path = SCENARIOS_DIR / scenario_id / "evaluation_findings.yaml"
    if not path.is_file():
        return ()
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields = set(vm.EvaluationFinding.__dataclass_fields__)
    wrong = ValueError(
        f"{path}: expected 'findings:', a list of entries with exactly the text fields "
        f"{sorted(fields)}; scripted and llm one of {list(vm.FINDING_OUTCOMES)}"
    )
    if not isinstance(raw, dict) or set(cast(dict[object, object], raw)) != {"findings"}:
        raise wrong
    entries = cast(dict[str, object], raw)["findings"]
    if not isinstance(entries, list):
        raise wrong
    out: list[vm.EvaluationFinding] = []
    for entry in cast(list[object], entries):
        if not isinstance(entry, dict):
            raise wrong
        f = cast(dict[object, object], entry)
        text = {str(k): v for k, v in f.items() if isinstance(k, str) and isinstance(v, str)}
        if set(f) != fields or set(text) != fields:
            raise wrong
        if text["scripted"] not in vm.FINDING_OUTCOMES or text["llm"] not in vm.FINDING_OUTCOMES:
            raise wrong
        out.append(vm.EvaluationFinding(**text))
    return tuple(out)


DISPLAY_FILE = "display.yaml"  # UI-only display labels (spec 006b); nothing else reads it
DISPLAY_SECTIONS = ("categories", "actions", "goals")
NOT_PLAIN = set("<>[]{}`*_#|")  # markup or formatting: labels are plain text


def _plain(text: object) -> bool:
    """Plain one-line text: printable (no line breaks, tabs or control characters), no markup,
    no surrounding spaces, and something visible."""
    return (
        isinstance(text, str)
        and text.isprintable()
        and text == text.strip()
        and any(c.isalnum() for c in text)
        and not NOT_PLAIN & set(text)
    )


def _one_sentence(text: object) -> bool:
    """One sentence: plain, ends with a full stop, no other sentence end inside."""
    return _plain(text) and str(text).endswith(".") and not re.search(r"[.?!]\s*\S", str(text))


class _UniqueKeys(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys (PyYAML would keep the last one silently)."""


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys: list[Any] = [loader.construct_object(k) for k, _ in node.value]  # pyright: ignore[reportUnknownMemberType]
    if duplicates := sorted({str(k) for k in keys if keys.count(k) > 1}):
        raise ValueError(f"duplicate keys {duplicates}")
    return dict(loader.construct_pairs(node))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


_UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def labels_for(world: World) -> vm.Labels:
    """The scenario's display names: role names from roles.yaml, the rest from display.yaml.
    Every category, action and goal the scenario defines needs exactly one one-line label; a
    missing or malformed file is an error, never a silent fallback to ids."""
    sc, roles = world.scenario, world.roles
    path = SCENARIOS_DIR / sc.id / DISPLAY_FILE
    need = {
        "categories": set(roles.known_categories())
        | {f.data_category for e in sc.events for f in e.facts},
        "actions": {a.id for a in roles.actions},
        "goals": {g.id for g in sc.recovery_goals},
    }
    if not path.is_file():
        raise ValueError(f"{path}: missing; the UI needs display labels for this scenario")
    try:
        raw: object = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeys)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from None
    shape = (
        f"{path}: expected incident_summary (one sentence, one line) and {list(DISPLAY_SECTIONS)}, "
        "each mapping exactly the scenario's ids to one-line text labels"
    )
    if not isinstance(raw, dict) or set(cast(dict[object, object], raw)) != {
        "incident_summary",
        *DISPLAY_SECTIONS,
    }:
        raise ValueError(shape)
    data = cast(dict[str, object], raw)
    maps: dict[str, dict[str, str]] = {}
    for key, ids in need.items():
        entry = data[key]
        if not isinstance(entry, dict):
            raise ValueError(f"{shape}; {key} is not a mapping")
        m = cast(dict[object, object], entry)
        text = {
            str(k): v
            for k, v in m.items()
            if isinstance(k, str) and isinstance(v, str) and _plain(v)
        }
        if set(m) != ids or set(text) != ids:
            extra, missing = sorted(map(str, set(m) - ids)), sorted(ids - set(text))
            raise ValueError(f"{shape}; {key}: unknown {extra}, missing or invalid {missing}")
        values = [v.casefold() for v in text.values()]  # "Monitor" and "monitor" are one label
        if shared := sorted({v for v in values if values.count(v) > 1}):
            raise ValueError(f"{shape}; {key}: one label for several ids {shared} (not a rename)")
        maps[key] = text
    summary = data["incident_summary"]
    if not _one_sentence(summary):
        raise ValueError(f"{shape}; incident_summary is not one sentence on one line")
    return vm.Labels(
        roles={r.id: r.name for r in roles.roles},
        categories=maps["categories"],
        actions=maps["actions"],
        goals=maps["goals"],
        events={e.id: (e.at_minute, e.title) for e in sc.events},
        summary=cast(str, summary),
    )


@dataclass(frozen=True, slots=True)
class Bundle:
    """Everything one scenario and agent mode shows: computed once, held in memory."""

    world: World
    baseline: RunResult
    search: SearchResult
    prompt_version: str  # "" for scripted agents
    labels: vm.Labels = vm.IDS


def compute(scenario_id: str, mode: str) -> Bundle:
    world = load_world(scenario_id, None, SCENARIOS_DIR, agent_choice(mode))
    labels = labels_for(world)
    baseline = world.baseline()
    found = search_repairs(scenario_id, world=world)
    agent = next(iter(world.agents.values()))
    version = agent.prompt_version if isinstance(agent, LLMAgent) else ""
    return Bundle(world, baseline, found, version, labels)


_CACHE: dict[tuple[str, str], Bundle | str] = {}  # a str is the reason it could not be computed
# One lock per key, so an LLM precompute never blocks a page that needs the cached scripted one.
_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


def bundle(scenario_id: str, mode: str) -> Bundle | str:
    key = (scenario_id, mode)
    if (found := _CACHE.get(key)) is not None:
        return found
    with _LOCKS_LOCK:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:
        if key not in _CACHE:
            try:
                _CACHE[key] = compute(scenario_id, mode)
            except LLMConfigError as exc:  # names missing variables, never values
                _CACHE[key] = str(exc)
        return _CACHE[key]


def recompute(scenario_id: str, mode: str) -> Bundle | str:
    _CACHE.pop((scenario_id, mode), None)
    return bundle(scenario_id, mode)


def precompute() -> None:
    """At startup: every scenario with scripted agents; LLM (cache only) in the background."""
    for name in scenarios():
        bundle(name, "scripted")
    threading.Thread(
        target=lambda: [bundle(n, "llm-offline") for n in scenarios()], daemon=True
    ).start()


@dataclass
class Session:
    """What one browser tab shows (engine results only)."""

    scenario: str
    mode: str = "scripted"
    data: Bundle | None = None
    selected: ReplayComparison | None = None
    failure: str | None = None  # highlighted in the graph; None: every failure
    lanes_run: str = "baseline"  # or "replay"
    cell: tuple[str, int] | None = None  # (role, minute) of the opened role view
    step: int = 0
    guided: bool = True
    error: str = ""  # why the selected agents have no result (shown instead of one)
    fade: bool = True  # graph: everything outside the highlighted subgraph faded (spec 006b)
    ladder_all: bool = False  # ladder: every rung, not only the top TOP_RUNGS
    sections: dict[str, ui.element] = field(default_factory=dict[str, ui.element])


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def raw_id(text: str) -> str:
    """A raw id in small print: hidden in Guided mode (the tooltip has it), shown in Expert."""
    return f'<div class="cg-rawid">{esc(text)}</div>'


def chip_html(c: vm.Chip) -> str:
    return (
        f'<span class="cg-chip {esc(c.css)}"><span class="cg-chip-id">{esc(c.text)}</span>'
        f"<span>{esc(c.label)}</span></span>"
    )


def chips(items: tuple[vm.Chip, ...]) -> None:
    for c in items:
        with ui.element("span").classes(f"cg-chip {c.css}"):
            ui.label(c.text).classes("cg-chip-id")
            ui.label(c.label)


def named(names: tuple[str, ...], raw: tuple[str, ...]) -> None:
    """Lines by name, each with its raw-id wording in small print (shown in Expert mode)."""
    if not names:
        ui.label("none").classes("cg-muted")
    ui.html(
        "".join(
            f'<div class="cg-wrap" title="{esc(r)}">{esc(n)}</div>{raw_id(r)}'
            for n, r in zip(names, raw, strict=True)
        )
    ).classes("w-full")


def lines(items: tuple[str, ...] | list[str], empty: str = "none") -> None:
    with ui.column().classes("gap-0 w-full"):
        if not items and empty:
            ui.label(empty).classes("cg-muted")
        for item in items:
            ui.label(item).classes("cg-mono whitespace-pre-wrap")


def section(s: Session, key: str, kicker: str, title: str) -> ui.column:
    box = ui.column().classes("cg-section gap-2").props(f"data-testid=section-{key}")
    s.sections[key] = box
    with box:
        ui.label(kicker).classes("cg-kicker")
        ui.label(title).classes("cg-h2")
    return box


@ui.page("/")
def index() -> None:
    ui.add_css(THEME)
    names = scenarios()
    s = Session(scenario=names[0])
    dark = ui.dark_mode(False)

    def current() -> Bundle | str:
        return bundle(s.scenario, s.mode)

    def use(data: Bundle) -> None:
        s.data = data
        s.selected = (data.search.ranked or data.search.inconclusive or (None,))[0]
        s.failure, s.cell = vm.default_failure(data.baseline), None

    with ui.header().classes("cg-header column gap-0 p-0"):
        with ui.row().classes("w-full items-center gap-4 px-6 py-2 no-wrap"):
            ui.icon("account_tree", size="28px").classes("cg-brand-icon")
            with ui.column().classes("gap-0"):
                ui.label("CascadeGuard").classes("cg-wordmark")
                ui.label(
                    "Where AI decisions and institutional rules collide: smallest safe repair, "
                    "tested by replay"
                ).classes("cg-tagline")
            ui.space()
            ui.select(names, value=s.scenario, label="Scenario", on_change=lambda e: pick(e.value))
            ui.toggle(AGENT_MODES, value=s.mode, on_change=lambda e: pick_mode(e.value)).props(
                "data-testid=agents"
            )
            ui.toggle(
                {"guided": "Guided", "expert": "Expert"},
                value="guided",
                on_change=lambda e: set_guided(e.value == "guided"),
            ).props("data-testid=view-mode")
            ui.button(icon="dark_mode", on_click=dark.toggle).props("flat round").tooltip(
                "Light / dark"
            )
        ui.label(vm.DISCLAIMER).classes("cg-disclaimer").props("data-testid=disclaimer")
        clause_set = ui.label("").classes("cg-disclaimer pt-0").props("data-testid=clause-set")

    agents_label = ui.label("").classes("cg-muted").props("data-testid=agents-label")

    # ----- guided stepper -----
    stepper = ui.row().classes("cg-steps items-center w-full")

    with stepper:  # built once; go() only changes props
        step_buttons = [
            ui.button(f"{key}. {title}", on_click=lambda _, i=i: go(i))
            .props(
                ("unelevated" if i == 0 else "outline") + f" no-caps dense data-testid=step-{key}"
            )
            .classes("cg-step")
            for i, (key, title, _) in enumerate(STEPS)
        ]
        ui.space()
        back = ui.button("Back", on_click=lambda: go(s.step - 1)).props("flat no-caps")
        back.set_enabled(False)
        forward = ui.button("Next", on_click=lambda: go(s.step + 1)).props(
            "unelevated no-caps data-testid=next"
        )
    narration = ui.label(STEPS[0][2]).classes("cg-narration").props("data-testid=narration")

    # ----- a. verdict strip -----
    with section(s, "a", "a · verdict", "Baseline vs best replay"):

        @ui.refreshable
        def verdict_view() -> None:
            d = s.data
            if d is None:
                if s.error:  # e.g. LLM agents without a configured model: no result is shown
                    ui.label(s.error).classes("cg-bad cg-wrap").props("data-testid=verdict-error")
                return
            v = vm.verdict(d.baseline, d.search, d.world.scenario, d.labels)
            ui.label(d.labels.summary).classes("cg-summary").props("data-testid=incident-summary")
            with ui.element("div").classes("cg-verdict"):
                stat(f"{v.baseline_met} / {v.critical}", "critical goals met: baseline", "cg-bad")
                replay = "n/a" if v.replay_met is None else f"{v.replay_met} / {v.critical}"
                good = v.replay_met == v.critical
                stat(replay, "critical goals met: best replay", "cg-good" if good else "cg-warn")
                stat(str(v.baseline_failures), "diagnosed failures (baseline)", "cg-bad")
                stat(count(v.removed), REMOVED_LABEL, "cg-good")
                stat(count(v.masked), MASKED_LABEL, "cg-warn")
                stat(count(v.remaining), "remaining", "")
                stat(count(v.new_conflicts), "new conflicts", "")
            if v.repair_id:
                with ui.row().classes("items-center gap-2 w-full"):
                    css = "cg-badge-safe" if v.badge == vm.SMALLEST_SAFE else "cg-badge-top"
                    ui.label(v.badge).classes(f"cg-badge {css}").props("data-testid=verdict-badge")
                    if v.authorization:
                        ui.label(v.authorization).classes("cg-badge cg-badge-auth").props(
                            "data-testid=verdict-authorization"
                        )
                for sentence in v.sentences:
                    ui.label(sentence).classes("cg-sentence").props("data-testid=verdict-edit")
                ui.label(v.repair_id).classes("cg-idline")
            ui.label(f"Outcome: {v.outcome}").classes("cg-wrap").props(
                "data-testid=verdict-outcome"
            )
            if v.caveat:
                ui.label(f"Caveat: {v.caveat}").classes("cg-warn cg-wrap")
            if b := vm.incomplete_banner(d.baseline.failed_steps):
                ui.label(b).classes("cg-bad cg-wrap").props("data-testid=incomplete")

        verdict_view()

    def count(n: int | None) -> str:
        return "n/a" if n is None else str(n)

    def incomplete_note() -> None:
        """The incomplete-run banner, repeated in every section built on the baseline."""
        d = s.data
        if d is not None and (b := vm.incomplete_banner(d.baseline.failed_steps)):
            ui.label(b).classes("cg-bad cg-wrap").props("data-testid=incomplete-note")

    def stat(value: str, label: str, css: str) -> None:
        with ui.element("div").classes("cg-stat"):
            ui.label(value).classes(f"cg-stat-value {css}")
            ui.label(label).classes("cg-stat-label")

    # ----- b. swimlanes -----
    with section(s, "b", "b · timeline", "Who knew what, when: information boundaries"):
        ui.toggle(
            {"baseline": "Baseline", "replay": "Replay (selected repair)"},
            value=s.lanes_run,
            on_change=lambda e: pick_lanes(e.value),
        ).props("data-testid=lanes-run")

        # (run, role, minute) -> cell, to mark the open cell in place. Baseline and replay lanes
        # are both built; the switch only toggles which one is visible (spec 006 budget).
        cells: dict[tuple[str, str, int], ui.element] = {}

        def run_result(run: str) -> RunResult | None:
            d = s.data
            if d is None:
                return None
            if run == "replay":
                return s.selected.replay if s.selected is not None else None
            return d.baseline

        def lanes(run: str) -> None:
            d, result = s.data, run_result(run)
            if d is None or result is None:
                return
            for key in [k for k in cells if k[0] == run]:
                del cells[key]
            events = d.world.scenario.events
            with ui.element("div").classes("cg-lanes").props(f"data-testid=lanes-{run}"):
                ui.label("role").classes("cg-lane-head")
                for e in events:
                    ui.label(f"T+{e.at_minute:02d} {e.title}").classes("cg-lane-head")
                for lane in vm.swimlanes(result, d.world.scenario, d.labels):
                    ui.html(
                        f'<div title="{esc(lane.role)}">{esc(lane.name)}</div>{raw_id(lane.role)}'
                    ).classes("cg-lane-role")
                    for c in lane.cells:
                        cell(run, lane.role, c)
                    if lane.bars:
                        ui.label("obligations").classes("cg-lane-head")
                        with ui.element("div").classes("cg-bars"):
                            for bar in lane.bars:
                                obligation(bar, len(events))

        @ui.refreshable
        def baseline_lanes() -> None:
            incomplete_note()
            lanes("baseline")

        @ui.refreshable
        def replay_lanes() -> None:
            lanes("replay")

        @ui.refreshable
        def role_panel_view() -> None:
            result = run_result(s.lanes_run)
            if result is not None and s.cell is not None:
                role_panel(result, *s.cell)

        with ui.element("div").classes("w-full") as baseline_box:
            baseline_lanes()
        with ui.element("div").classes("w-full") as replay_box:
            replay_lanes()
        replay_box.set_visibility(False)
        role_panel_view()

    def cell(run: str, role: str, c: vm.Cell) -> None:
        css = "cg-cell" + (" cg-cell-recipient" if c.recipient else "")
        css += " cg-cell-selected" if s.lanes_run == run and s.cell == (role, c.minute) else ""
        with (
            ui.element("div")
            .classes(css)
            .on("click", lambda _, r=role, m=c.minute: open_cell(r, m))
            .props(f"data-testid=cell-{run}-{role}-{c.minute}") as box
        ):
            cells[(run, role, c.minute)] = box
            # One escaped HTML block per cell (DOMPurify on top): far fewer components, so
            # the lanes render within the click budget. Agent text only in the labelled title.
            parts = [
                f'<div class="cg-factline" title="{esc(f.text)}">'
                f'<div class="cg-fact-cat">{esc(f.label)}</div>{raw_id(f.text)}</div>'
                for f in c.facts
            ]
            tip = f' title="{esc(c.raw)}"' if c.raw else ""
            parts += [f'<div class="cg-act-ok cg-wrap"{tip}>✓ {esc(a)}</div>' for a in c.accepted]
            parts += [f'<div class="cg-act-no cg-wrap"{tip}>✗ {esc(a)}</div>' for a in c.rejected]
            parts += [raw_id(c.raw)] if c.raw else []
            parts += [
                f'<div class="cg-muted underline" title="{esc(st)}">{esc(STATEMENT)}</div>'
                for st in c.statements
            ]
            if parts:
                ui.html("".join(parts))

    def obligation(bar: vm.Bar, columns: int) -> None:
        state = (
            "cg-bar-fulfilled"
            if bar.state.startswith("fulfilled")
            else "cg-bar-open"
            if vm.OPEN_AT_END_STATE in bar.state
            else "cg-bar-overdue"
        )
        left = 100 * bar.start / columns
        width = 100 * (bar.end - bar.start + 1) / columns
        ui.html(
            f'<div class="cg-wrap">{esc(bar.action)}: {esc(bar.opened)} → due {esc(bar.due)}; '
            f"{esc(bar.state)}</div>{chip_html(bar.source)}"
        ).classes(f"cg-bar {state}").style(f"margin-left: {left:.2f}%; width: {width:.2f}%")

    def role_panel(result: RunResult, role: str, minute: int) -> None:
        d = s.data
        assert d is not None
        v = vm.role_view(result, role, minute, d.world.roles.known_categories())
        with ui.column().classes("cg-pane w-full gap-1 mt-2").props("data-testid=role-view"):
            ui.label(
                f"Role view: {d.labels.role(role)} at T+{minute:02d} "
                "(exactly what its agent received)"
            ).classes("font-semibold")
            ui.label(role).classes("cg-idline")
            ui.label(v.title if v.recipient else f"{v.title} (not a recipient of this inject)")
            ui.label(f"Simulation time: {v.at}").classes("cg-muted")
            for title, items in (
                ("Facts known (inside its boundary)", v.facts),
                ("Clauses shown with this inject", v.clauses),
                ("Clauses relevant to this role (what an LLM agent may cite)", v.role_clauses),
                ("Open obligations (opened by the engine)", v.open_obligations),
                ("Own accepted actions so far", v.own_history),
                ("Data categories outside its boundary (never shown to it)", v.outside),
                ("What its agent said", v.agent_statements),
            ):
                ui.label(title).classes("font-semibold mt-1")
                lines(items)

    # ----- c. cascade graph (created once; updated in place) -----
    with section(s, "c", "c · cascade", "Dependency graph"):
        failure_picker = ui.select(
            {"": "all diagnosed failures"},
            value="",
            label="Highlight",
            on_change=lambda e: pick_failure(str(e.value) or None),
        ).classes("cg-picker")
        ui.switch(
            "Show all at full opacity", value=not s.fade, on_change=lambda e: set_fade(not e.value)
        ).props("data-testid=graph-show-all")
        graph_box = ui.element("div").classes("w-full")
    charts: list[ui.echart] = []  # the one chart, created after the first paint, never rebuilt

    def refresh_graph() -> None:
        d = s.data
        if d is None:
            return
        if not charts:
            with graph_box:
                charts.append(
                    ui.echart(vm.graph_option(d.baseline, s.failure, d.labels, s.fade))
                    .classes("w-full cg-graph")
                    .props("data-testid=graph")
                )
        chart = charts[0]
        choices = {"": "all diagnosed failures"} | {
            f.id: f"{f.category.value.replace('_', ' ')}: {vm.failure_title(f.subject, d.labels)}"
            for f in d.baseline.failures
        }
        if failure_picker.options != choices:  # pyright: ignore[reportUnknownMemberType]
            failure_picker.options = choices
            failure_picker.update()
        if failure_picker.value != (s.failure or ""):
            failure_picker.value = s.failure or ""  # its change handler sees nothing new
        options = cast(dict[str, Any], chart.options)  # pyright: ignore[reportUnknownMemberType]
        options.clear()
        options.update(vm.graph_option(d.baseline, s.failure, d.labels, s.fade))
        chart.update()

    # ----- d. diagnosis -----
    with section(s, "d", "d · diagnosis", "Coordination failures by category"):

        @ui.refreshable
        def diagnosis_view() -> None:
            d = s.data
            if d is None:
                return
            incomplete_note()
            with ui.element("div").classes("cg-cards"):
                for card in vm.diagnosis_cards(d.baseline, d.labels):
                    with (
                        ui.column()
                        .classes("cg-card gap-1" + ("" if card.items else " cg-card-empty"))
                        .props(f"data-testid=category-{card.category}")
                    ):
                        ui.label(card.title).classes("cg-kicker").tooltip(card.category)
                        if not card.items:
                            ui.label("none found").classes("cg-muted")
                        for item in card.items:
                            ui.button(
                                item.title, on_click=lambda _, fid=item.id: pick_failure(fid)
                            ).props(
                                f"flat dense no-caps align=left data-testid=failure-{item.id}"
                            ).classes("cg-wrap font-semibold p-0").tooltip(
                                f"Highlight in the cascade graph ({item.id})"
                            )
                            ui.html(raw_id(item.id))
                            ui.label(item.description).classes("cg-wrap")
                            ui.label(f"blocks: {item.blocks}").classes("cg-muted")
                            with ui.row().classes("gap-0"):
                                chips(item.evidence)
                                if not item.evidence:
                                    ui.label(
                                        "clauses: none found in the loaded clause set"
                                    ).classes("cg-muted")
                            ui.label(item.qualification).classes("cg-qual")

        diagnosis_view()

    # ----- e. repair ladder -----
    with section(s, "e", "e · repairs", "Repair ladder (every repair rule is hypothetical)"):
        rungs: dict[str, ui.element] = {}  # repair id -> its rung, to highlight in place
        # Rungs below the top TOP_RUNGS and the "Show all N" button: built once per refresh and
        # shown or hidden in place (spec 006b; click budget).
        extra_rungs: dict[str, ui.element] = {}  # repair id -> rung or inconclusive row
        ladder_button: list[ui.button] = []

        @ui.refreshable
        def ladder_view() -> None:
            d = s.data
            if d is None:
                return
            rungs.clear()
            extra_rungs.clear()
            ladder_button.clear()
            ui.label(d.search.summary()["ranking"]).classes("cg-muted")
            chosen = s.selected.proposal.repair_id if s.selected else ""
            all_rungs = vm.ladder(d.search, d.labels)
            for r in all_rungs:
                with (
                    ui.element("div")
                    .classes("cg-rung" + (" cg-rung-selected" if r.repair_id == chosen else ""))
                    .props(f"data-testid=rung-{r.rank}") as rung
                ):
                    rungs[r.repair_id] = rung
                    if r.rank > vm.TOP_RUNGS:
                        extra_rungs[r.repair_id] = rung
                        rung.set_visibility(s.ladder_all)
                    css = "cg-badge-safe" if r.badge == vm.SMALLEST_SAFE else "cg-badge-top"
                    badges = (
                        f'<span class="cg-badge {css}">{esc(r.badge)}</span> ' if r.badge else ""
                    ) + (
                        f'<span class="cg-badge cg-badge-auth">{esc(r.authorization)}</span>'
                        if r.authorization
                        else ""
                    )
                    body = [
                        f"<div>{badges}</div>" if badges else "",
                        *(f'<div class="cg-sentence">{esc(x)}</div>' for x in r.sentences),
                        f'<div class="cg-idline">{esc(r.repair_id)}</div>',
                        f'<div class="cg-wrap text-sm">{esc(r.outcome)}; {r.edits} edit(s); '
                        f"roles touched: {esc(', '.join(r.roles))}; critical blockers removed "
                        f"{r.removed}</div>",
                        *(f'<div class="cg-mono">{esc(m)}</div>' for m in r.masked),
                        *(
                            f'<div class="cg-bad cg-wrap text-sm">new conflict: {esc(x)}</div>'
                            for x in r.new_conflicts
                        ),
                    ]
                    ui.label(str(r.rank)).classes("cg-rank")
                    ui.html("".join(body)).classes("min-w-0 flex-1")
                    ui.button("Compare", on_click=lambda _, rid=r.repair_id: compare(rid)).props(
                        "outline dense no-caps"
                    )
            unranked = vm.inconclusive(d.search)
            if unranked:
                with ui.column().classes("w-full gap-0 mt-2").props("data-testid=inconclusive"):
                    ui.label(
                        f"inconclusive ({outcome_definition('inconclusive')}): unranked"
                    ).classes("font-semibold")
                    for i, (repair_id, label) in enumerate(unranked, 1):
                        with (
                            ui.row()
                            .classes("items-center gap-2 w-full no-wrap")
                            .props(f"data-testid=inconclusive-{i}") as row
                        ):
                            ui.button(
                                "Compare", on_click=lambda _, rid=repair_id: compare(rid)
                            ).props("flat dense no-caps")
                            ui.label(f"{repair_id}: {label}").classes("cg-mono")
                        if i > vm.TOP_RUNGS:  # collapsed the same way as the ranked rungs
                            extra_rungs[repair_id] = row
                            row.set_visibility(s.ladder_all)
            ui.label("Discarded by the hard filter").classes("font-semibold mt-2")
            dropped = vm.discarded(d.search)
            if not dropped:
                ui.label("none").classes("cg-muted")
            for i, line in enumerate(dropped, 1):
                item = ui.label(line).classes("cg-mono whitespace-pre-wrap")
                if i > vm.TOP_RUNGS:  # collapsed the same way as the ranked rungs
                    extra_rungs[f"discarded-{i}"] = item
                    item.set_visibility(s.ladder_all)
            if extra_rungs:
                ladder_button.append(
                    ui.button(ladder_text(ladder_total()), on_click=lambda: toggle_ladder()).props(
                        "flat no-caps data-testid=ladder-toggle"
                    )
                )

        ladder_view()

    # ----- f. split screen -----
    with section(s, "f", "f · replay", "Baseline vs replay of the identical incident"):

        @ui.refreshable
        def split_view() -> None:
            d, c = s.data, s.selected
            if d is None or c is None:
                ui.label("No repair selected.").classes("cg-muted")
                return
            v = vm.comparison(c, d.labels)
            for sentence in v.edits:
                ui.label(sentence).classes("cg-sentence").props("data-testid=comparison-edit")
            ui.label(v.repair_id).classes("cg-idline").props("data-testid=comparison-id")
            for edit_id in v.edit_ids:
                ui.label(edit_id).classes("cg-rawid")
            if v.incomplete:
                ui.label(v.incomplete).classes("cg-bad cg-wrap")
            if v.withheld:
                ui.label(f"Not comparable: {v.withheld}.").classes("italic").props(
                    "data-testid=withheld"
                )
            ui.label(
                f"Outcome: {v.outcome}" + (f"; {v.authorization}" if v.authorization else "")
            ).classes("cg-wrap font-medium").props("data-testid=comparison-outcome")
            ui.label(f"Clauses the repair targets: {v.targets}").classes("cg-muted")
            with ui.element("div").classes("cg-split").props("data-testid=comparison"):
                with ui.column().classes("cg-pane gap-1"):
                    ui.label("Baseline").classes("cg-h2")
                    lines([f"{g}: {base}" for g, base, _ in v.goals])
                    ui.label("Diagnosed failures").classes("font-semibold")
                    named(v.baseline_named, v.baseline_failures)
                with ui.column().classes("cg-pane gap-1"):
                    ui.label("Replay").classes("cg-h2")
                    lines([f"{g}: {rep}" for g, _, rep in v.goals])
                    ui.label("Diagnosed failures").classes("font-semibold")
                    named(v.replay_named, (*v.removed, *v.replay_failures))
            agents_row(c)
            ui.label("Actions whose verdict changed").classes("font-semibold")
            lines(v.changed_actions)
            for note in v.notes:
                ui.label(note).classes("cg-qual")

        split_view()

    def agents_row(c: ReplayComparison) -> None:
        """LLM mode: the same repair under scripted and LLM agents, with a recorded finding
        only when it matches the computed verdicts."""
        d = s.data
        if d is None or not d.prompt_version:  # only a run that really used LLM agents
            return
        scripted = bundle(s.scenario, "scripted")
        if isinstance(scripted, str):
            return
        try:
            same = scripted.search.comparison(c.proposal.repair_id)
        except KeyError:
            return
        row = vm.scripted_vs_llm(same, c, d.prompt_version, findings_for(s.scenario))
        with ui.column().classes("cg-agents-row w-full gap-1").props("data-testid=agents-row"):
            ui.label("Same repair, scripted vs LLM agents").classes("font-semibold")
            ui.label(f"Scripted: {row.scripted}").classes("cg-wrap")
            ui.label(f"LLM (cached): {row.llm}").classes("cg-wrap")
            if row.finding:
                ui.label(f"Evaluation finding: {row.finding}").classes("cg-wrap font-medium").props(
                    "data-testid=agents-finding"
                )
                ui.label(f"Source: {row.source}").classes("cg-muted")

    # ----- expert extras -----
    with section(s, "x", "expert", "Clause set and engine findings"):

        @ui.refreshable
        def expert_view() -> None:
            d = s.data
            if d is None:
                return
            ui.label(d.baseline.clause_set)
            lines(vm.clause_set(d.baseline, d.world.corpus_ids))
            ui.label("Findings").classes("font-semibold mt-2")
            lines(vm.findings(d.baseline))
            ui.label("Outcome definitions").classes("font-semibold mt-2")
            lines(
                [
                    f"{o}: {outcome_definition(o)}"
                    for o in ("resolved", "partial", "no effect", "introduces new conflict")
                ]
            )

        expert_view()

    # ----- g. exports and re-run -----
    with section(
        s, "g", "g · exports", "Export (JSON and Markdown, same content as the CLI --export)"
    ):

        def download(label: str) -> None:
            """Exports are built only when asked for (the CLI's builders, unchanged)."""
            d = s.data
            if d is None:
                return
            files = vm.export_files(d.world.scenario.id, d.baseline, d.search, s.selected)
            f = next((f for f in files if f.label == label), None)
            if f is None:  # e.g. no replay selected
                ui.notify(f"{label}: nothing to export yet", type="warning")
                return
            ui.download.content(f.content, f.filename)

        with ui.row():
            for label in EXPORTS:
                ui.button(label, on_click=lambda _, label=label: download(label)).props(
                    "outline dense no-caps"
                )
        with ui.row().classes("items-center gap-2"):
            ui.button("Run baseline", on_click=lambda: rerun()).props("flat no-caps")
            ui.button("Find repairs", on_click=lambda: rerun()).props("flat no-caps")
            ui.label(
                "Results are precomputed; these re-run the engine for the selected agents "
                "(LLM: from the decision cache only)."
            ).classes("cg-muted")
        ui.label(vm.DISCLAIMER).classes("cg-qual")

    # ----- behaviour -----
    def show_sections() -> None:
        visible = {STEPS[s.step][0]} if s.guided else {"a", "b", "c", "d", "e", "f", "x", "g"}
        visible |= {"g"} if s.guided and s.step == len(STEPS) - 1 else set()
        for key, box in s.sections.items():
            box.set_visibility(key in visible)
        stepper.set_visibility(s.guided)
        narration.set_visibility(s.guided)

    def go(i: int) -> None:
        s.step = max(0, min(i, len(STEPS) - 1))
        narration.set_text(STEPS[s.step][2])
        for i, button in enumerate(step_buttons):
            on = i == s.step
            button.props(
                add="unelevated" if on else "outline", remove="outline" if on else "unelevated"
            )
        back.set_enabled(s.step > 0)
        forward.set_enabled(s.step < len(STEPS) - 1)
        show_sections()
        if pending & step_views():  # not refreshed yet: do it now that it is shown
            update(pending & step_views())

    def set_guided(guided: bool) -> None:
        s.guided = guided
        # Raw ids (class cg-rawid) are shown in Expert mode by one class on the page body.
        ui.query("body").classes(remove="cg-expert") if guided else ui.query("body").classes(
            add="cg-expert"
        )
        show_sections()
        split_view.refresh()

    def step_views() -> set[str]:
        key = STEPS[s.step][0]
        return {key, "r"} if key == "b" else {key}

    views = {
        "a": verdict_view.refresh,
        "b": lambda: (baseline_lanes.refresh(), role_panel_view.refresh()),
        "r": lambda: refresh_replay_lanes(),  # in section b
        "c": refresh_graph,
        "d": diagnosis_view.refresh,
        "e": ladder_view.refresh,
        "f": split_view.refresh,
        "x": expert_view.refresh,
    }
    pending: set[str] = set()
    in_section = {"r": "b"}  # view key -> the section that shows it

    def visible(key: str) -> bool:
        return s.sections[in_section.get(key, key)].visible

    def update(keys: set[str], now: set[str] | None = None) -> None:
        """Refresh what the click is about now (the verdict, or the guided step on screen) and
        everything else right after, so a click waits only for that (spec 006 budget)."""
        if now is None:
            now = {"a", *step_views()} if s.guided else {"a"}
        shown = {k for k in keys & now if visible(k)}
        pending.difference_update(shown)
        for k in sorted(shown):
            views[k]()
        if keys - shown and not pending:
            background_tasks.create(flush())  # pyright: ignore[reportUnknownMemberType]
        pending.update(keys - shown)

    async def flush() -> None:
        await asyncio.sleep(HIDDEN_DELAY)  # the visible update is drawn first
        while pending:
            views[pending.pop()]()

    def render_all() -> None:
        d = s.data
        if d is None:
            return
        clause_set.set_text(f"Clause set: {d.baseline.clause_set}")
        agents_label.set_text(f"Agents: {d.world.agent_label}" + cache_text(d.world))
        update(set(views))

    def load(data: Bundle | str) -> None:
        if isinstance(data, str):  # never keep showing the other agents' results
            ui.notify(data, type="warning")
            agents_label.set_text(data)
            s.data, s.selected, s.error, s.cell = None, None, data, None
            clause_set.set_text("")
            for view in (verdict_view, baseline_lanes, replay_lanes, role_panel_view):
                view.refresh()
            for view in (diagnosis_view, ladder_view, split_view, expert_view):
                view.refresh()
            if charts:
                charts[0].set_visibility(False)
            return
        s.error = ""
        if charts:
            charts[0].set_visibility(True)
        use(data)
        render_all()

    async def pick(name: str) -> None:
        s.scenario = name
        load(cast(Bundle | str, await run.io_bound(current)))

    async def pick_mode(mode: str) -> None:
        s.mode = mode
        load(cast(Bundle | str, await run.io_bound(current)))

    async def rerun() -> None:
        load(cast(Bundle | str, await run.io_bound(recompute, s.scenario, s.mode)))
        ui.notify("Re-ran the baseline and repair search.")

    replay_stale = [False]  # replay lanes not rebuilt since the data or selection changed

    def refresh_replay_lanes() -> None:
        """Rebuild the replay lanes only while they are shown; otherwise on the switch to them."""
        if replay_box.visible:
            replay_lanes.refresh()
            role_panel_view.refresh()
        else:
            replay_stale[0] = True

    def pick_lanes(which: str) -> None:
        if which == "replay" and replay_stale[0]:
            replay_stale[0] = False
            replay_lanes.refresh()
        if s.cell is not None and (s.lanes_run, *s.cell) in cells:
            cells[(s.lanes_run, *s.cell)].classes(remove="cg-cell-selected")
        s.lanes_run, s.cell = which, None
        baseline_box.set_visibility(which == "baseline")
        replay_box.set_visibility(which == "replay")
        role_panel_view.refresh()

    def open_cell(role: str, minute: int) -> None:
        if s.cell is not None and (s.lanes_run, *s.cell) in cells:
            cells[(s.lanes_run, *s.cell)].classes(remove="cg-cell-selected")
        s.cell = None if s.cell == (role, minute) else (role, minute)
        if s.cell is not None and (s.lanes_run, *s.cell) in cells:
            cells[(s.lanes_run, *s.cell)].classes(add="cg-cell-selected")
        role_panel_view.refresh()

    def pick_failure(failure: str | None) -> None:
        if failure == s.failure and charts:  # e.g. the picker echoing a highlight just made
            return
        s.failure = failure
        refresh_graph()

    def set_fade(fade: bool) -> None:
        s.fade = fade
        refresh_graph()

    def ladder_total() -> int:
        """Rows behind "Show all N": ranked, inconclusive and discarded repairs."""
        d = s.data
        if d is None:
            return 0
        return len(d.search.ranked) + len(d.search.inconclusive) + len(d.search.discarded)

    def ladder_text(n: int) -> str:
        return f"Show top {vm.TOP_RUNGS}" if s.ladder_all else f"Show all {n}"

    def toggle_ladder() -> None:
        s.ladder_all = not s.ladder_all
        for rung in extra_rungs.values():
            rung.set_visibility(s.ladder_all)
        if ladder_button:
            ladder_button[0].set_text(ladder_text(ladder_total()))

    def compare(repair_id: str) -> None:
        if s.data is None:
            return
        if repair_id in extra_rungs and not s.ladder_all:  # never select a hidden rung
            toggle_ladder()
        s.selected = s.data.search.comparison(repair_id)
        for rid, rung in rungs.items():  # highlight in place; the ladder is not rebuilt
            rung.classes(add="cg-rung-selected") if rid == repair_id else rung.classes(
                remove="cg-rung-selected"
            )
        if s.guided:
            go(len(STEPS) - 1)
        update({"f", "r"}, now={"f"})  # the replay lanes follow the selected repair

    # First paint: header, stepper and verdict only. The other sections are filled over the
    # websocket right after the page is shown (all from the precomputed bundle; no click).
    data = current()
    if isinstance(data, Bundle):
        use(data)
        clause_set.set_text(f"Clause set: {data.baseline.clause_set}")
        agents_label.set_text(f"Agents: {data.world.agent_label}" + cache_text(data.world))
        verdict_view.refresh()
    else:
        load(data)
    show_sections()

    async def fill() -> None:
        await ui.context.client.connected()
        await asyncio.sleep(FILL_DELAY)  # let the browser paint the verdict first
        render_all()

    ui.timer(0, fill, once=True)


def cache_text(world: World) -> str:
    if world.cache is None:
        return ""
    st = world.cache.stats
    return f" | decision cache: {st.hits} steps reused, {st.misses} not cached"


def main() -> None:
    nicegui_app.on_startup(precompute)  # pyright: ignore[reportUnknownMemberType]
    ui.run(  # pyright: ignore[reportUnknownMemberType]
        title="CascadeGuard",
        host="127.0.0.1",
        port=port(),
        reload=False,
        show=False,
        tailwind=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
