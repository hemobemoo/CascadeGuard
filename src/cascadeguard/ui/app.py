"""CascadeGuard demo UI (Phase 4; see specs/004-demo-ui.md).

The UI only displays engine results: runs, searches and replays come from the same helpers
the CLI uses, and `ui/view_model.py` formats them. No logic lives here. The agents toggle picks
scripted agents (default), LLM agents from the decision cache only, or live LLM calls
(specs/005-llm-agents.md).
"""

import os
from dataclasses import dataclass

from nicegui import run, ui

from cascadeguard.agents.llm import DailyLimitReached, LLMConfigError
from cascadeguard.cli import (
    DAILY_LIMIT_STOP,
    LLM,
    SCRIPTED,
    AgentChoice,
    World,
    live_llm,
    load_world,
    search_repairs,
)
from cascadeguard.engine.repair_search import ReplayComparison, SearchResult
from cascadeguard.simulation.loader import SCENARIOS_DIR
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.ui import view_model as vm

DEFAULT_PORT = 8765  # 8080 is often taken by other local servers
PORT_VARIABLE = "CASCADEGUARD_UI_PORT"
AGENT_MODES = {
    "scripted": "Scripted",
    "llm-offline": "LLM (cached only)",
    "llm-live": "LLM (live, paid calls)",
}

LIVE_SEARCH_REFUSED = (
    "Repair search with live LLM calls is not enabled (hundreds of paid calls; needs explicit "
    "approval). Run the baseline with 'LLM (cached only)' to search from cached decisions."
)


def agent_choice(mode: str) -> AgentChoice:
    if mode == "scripted":
        return AgentChoice(SCRIPTED)
    return AgentChoice(LLM, offline=mode == "llm-offline")


def port() -> int:
    return int(os.environ.get(PORT_VARIABLE, DEFAULT_PORT))


def scenarios() -> list[str]:
    return sorted(p.name for p in SCENARIOS_DIR.iterdir() if (p / "scenario.yaml").is_file())


@dataclass
class Session:
    """What one browser tab has computed so far (engine results only)."""

    world: World | None = None
    baseline: RunResult | None = None
    search: SearchResult | None = None
    selected: ReplayComparison | None = None
    failure: str | None = None  # highlighted in the graph; None: every failure
    role: str | None = None
    minute: int = 0
    mode: str = "scripted"


def heading(text: str) -> None:
    ui.label(text).classes("text-lg font-semibold [overflow-wrap:anywhere]")


def lines(items: tuple[str, ...] | list[str], empty: str = "none") -> None:
    with ui.column().classes("gap-0"):
        if not items and empty:
            ui.label(empty).classes("text-gray-500 text-sm")
        for item in items:
            ui.label(item).classes("font-mono text-sm whitespace-pre-wrap [overflow-wrap:anywhere]")


@ui.page("/")
def index() -> None:
    s = Session()
    with ui.header().classes("bg-amber-100 text-amber-900 py-2"), ui.column().classes("gap-0"):
        ui.label(vm.DISCLAIMER).classes("font-medium").mark("disclaimer")
        clause_set = ui.label("Clause set: not run yet").classes("text-sm")

    ui.label("CascadeGuard").classes("text-2xl font-bold")
    with ui.row().classes("items-end gap-4"):
        names = scenarios()
        picker = ui.select(names, value=names[0], label="Scenario").classes("w-72")
        ui.toggle(
            AGENT_MODES, value=s.mode, on_change=lambda e: setattr(s, "mode", str(e.value))
        ).mark("agents")
        run_button = ui.button("Run baseline")
    status = ui.label("Pick a scenario and the agents, then run the baseline.")
    agents_label = ui.label("Agents: not run yet").classes("text-sm").mark("agents-label")

    @ui.refreshable
    def baseline_view() -> None:
        b, w = s.baseline, s.world
        if b is None or w is None:
            return
        banner = vm.incomplete_banner(b.failed_steps)
        if banner:
            ui.label(banner).classes("text-red-700 font-medium [overflow-wrap:anywhere]").mark(
                "incomplete"
            )
        with ui.card().classes("w-full"):
            heading("Clause set")
            ui.label(b.clause_set)
            lines(vm.clause_set(b, w.corpus_ids))
        with ui.card().classes("w-full"):
            heading("Timeline")
            for row in vm.timeline(b, w.scenario):
                with ui.expansion(
                    f"T+{row.minute:02d}  {row.title}  (to: {', '.join(row.recipients)})",
                    value=row.minute == 0,
                ).classes("w-full"):
                    lines(row.lines)
        role_card()
        graph_card()

    @ui.refreshable
    def role_card() -> None:
        b, w = s.baseline, s.world
        if b is None or w is None:
            return
        with ui.card().classes("w-full"):
            heading("Role views: only what this role could see")
            roles = [r.id for r in w.roles.roles]
            minutes = {e.at_minute: f"T+{e.at_minute:02d}" for e in w.scenario.events}
            with ui.row():
                ui.select(
                    roles,
                    value=s.role or roles[0],
                    label="Role",
                    on_change=lambda e: pick_role(str(e.value)),
                ).classes("w-72")
                ui.select(
                    minutes,
                    value=s.minute,
                    label="Inject",
                    on_change=lambda e: pick_minute(int(e.value)),
                ).classes("w-40")
            v = vm.role_view(b, s.role or roles[0], s.minute, w.roles.known_categories())
            ui.label(
                v.title if v.recipient else f"{v.title} (not a recipient of this inject)"
            ).classes("font-medium")
            ui.label(f"Simulation time: {v.at}").classes("text-sm text-gray-600")
            if v.description:
                ui.label(v.description)
            ui.label("Role instructions").classes("font-semibold mt-2")
            ui.label(v.instructions).classes("text-sm")
            for title, items in (
                ("Allowed actions", v.allowed_actions),
                ("Decision points", v.decision_points),
                ("Facts known (inside its boundary)", v.facts),
                ("Clauses shown with this inject", v.clauses),
                ("Clauses relevant to this role (what an LLM agent may cite)", v.role_clauses),
                ("Own accepted actions so far", v.own_history),
                ("Open obligations (opened by the engine)", v.open_obligations),
                ("Data categories inside its boundary", v.inside),
                ("Data categories outside its boundary (never shown to it)", v.outside),
            ):
                ui.label(title).classes("font-semibold mt-2")
                lines(items)
            ui.label("What its agent said (unverified agent statement)").classes(
                "font-semibold mt-2"
            )
            lines(v.agent_statements, "no decision recorded at this inject")

    def pick_role(role: str) -> None:
        s.role = role
        role_card.refresh()

    def pick_minute(minute: int) -> None:
        s.minute = minute
        role_card.refresh()

    @ui.refreshable
    def graph_card() -> None:
        b = s.baseline
        if b is None:
            return
        with ui.card().classes("w-full"):
            heading("Dependency graph and diagnosed failures")
            choices = {"": "all diagnosed failures"} | {f.id: f.id for f in b.failures}
            ui.select(
                choices,
                value=s.failure or "",
                label="Highlight",
                on_change=lambda e: pick_failure(str(e.value) or None),
            ).classes("w-[32rem]")
            ui.echart(vm.graph_option(b, s.failure)).classes("w-full h-[36rem]")
            for f in vm.failures(b):
                with ui.column().classes("gap-0 mt-2"):
                    ui.button(
                        f"[{f.category}] {f.id}",
                        on_click=lambda _, fid=f.id: pick_failure(fid),
                    ).props("flat dense no-caps align=left").classes(
                        "font-semibold [overflow-wrap:anywhere]"
                    ).tooltip("Highlight only this failure in the graph")
                    ui.label(f.description)
                    ui.label(f"clauses: {f.clauses}").classes("font-mono text-sm")
                    ui.label(f"blocks: {f.blocks}").classes("text-sm")
                    ui.label(f.qualification).classes("italic text-sm text-gray-600")
            ui.label("Findings").classes("font-semibold mt-2")
            lines(vm.findings(b))

    def pick_failure(failure: str | None) -> None:
        s.failure = failure
        graph_card.refresh()

    @ui.refreshable
    def repairs_view() -> None:
        r = s.search
        if r is None:
            return
        with ui.card().classes("w-full"):
            heading("Ranked repairs (every repair rule is hypothetical)")
            ui.label(r.summary()["ranking"]).classes("text-sm text-gray-600")
            for row in vm.repairs(r):
                with ui.row().classes("items-start w-full gap-3 border-b py-1 no-wrap"):
                    ui.button("Compare", on_click=lambda _, rid=row.repair_id: compare(rid)).props(
                        "dense flat"
                    )
                    with ui.column().classes("gap-0 min-w-0 flex-1"):
                        ui.label(f"{row.rank}. {row.repair_id}").classes(
                            "font-mono text-sm [overflow-wrap:anywhere]"
                        )
                        ui.label(
                            f"{row.outcome}; critical blockers removed {row.removed}; "
                            f"{row.edits} edit(s)"
                            + (f"; {row.authorization}" if row.authorization else "")
                        ).classes("text-sm")
                        lines(row.masked, "")
                        for conflict in row.new_conflicts:
                            ui.label(f"new conflict: {conflict}").classes(
                                "text-sm text-red-700 [overflow-wrap:anywhere]"
                            )
        unranked = vm.inconclusive(r)
        if unranked:
            with ui.card().classes("w-full").mark("inconclusive"):
                heading("Inconclusive (unranked; not comparable: steps had no decision)")
                for repair_id, label in unranked:
                    with ui.row().classes("items-start w-full gap-3 border-b py-1 no-wrap"):
                        ui.button("Compare", on_click=lambda _, rid=repair_id: compare(rid)).props(
                            "dense flat"
                        )
                        ui.label(f"{repair_id}: {label}").classes(
                            "font-mono text-sm [overflow-wrap:anywhere]"
                        )
        with ui.card().classes("w-full"):
            heading("Discarded by the hard filter")
            lines(vm.discarded(r))
        comparison_view()

    @ui.refreshable
    def comparison_view() -> None:
        c = s.selected
        if c is None:
            return
        v = vm.comparison(c)
        with ui.card().classes("w-full").mark("comparison"):
            heading(f"Baseline vs replay: {v.repair_id}")
            if v.incomplete:
                ui.label(v.incomplete).classes("text-red-700 font-medium [overflow-wrap:anywhere]")
            if v.withheld:
                ui.label(f"Not comparable: {v.withheld}.").classes("italic").mark("withheld")
            ui.label(f"Outcome: {v.outcome}" + (f"; {v.authorization}" if v.authorization else ""))
            lines(v.edits)
            ui.label(f"Clauses the repair targets: {v.targets}").classes("text-sm")
            with ui.row().classes("w-full no-wrap gap-6"):
                with ui.column().classes("w-1/2"):
                    heading("Baseline")
                    lines([f"{g}: {base}" for g, base, _ in v.goals])
                    ui.label("Diagnosed failures").classes("font-semibold")
                    lines(v.baseline_failures)
                with ui.column().classes("w-1/2"):
                    heading("Replay")
                    lines([f"{g}: {rep}" for g, _, rep in v.goals])
                    ui.label("Diagnosed failures").classes("font-semibold")
                    lines((*v.removed, *v.replay_failures))
            ui.label("Actions whose verdict changed").classes("font-semibold")
            lines(v.changed_actions)
            for note in v.notes:
                ui.label(note).classes("italic text-sm text-gray-600")

    @ui.refreshable
    def export_view() -> None:
        b, w = s.baseline, s.world
        if b is None or w is None:
            return
        with ui.card().classes("w-full"):
            heading("Export (JSON and Markdown, same content as the CLI --export)")
            with ui.row():
                for f in vm.export_files(w.scenario.id, b, s.search, s.selected):
                    ui.button(
                        f.label,
                        on_click=lambda _, f=f: ui.download.content(f.content, f.filename),
                    ).props("outline dense no-caps").tooltip(f.filename)

    async def run_baseline() -> None:
        status.set_text("Running the baseline ...")
        try:
            world = await run.io_bound(
                load_world, str(picker.value), None, SCENARIOS_DIR, agent_choice(s.mode)
            )
        except LLMConfigError as exc:  # names missing variables, never values
            status.set_text(str(exc))
            ui.notify(str(exc), type="warning")
            return
        except DailyLimitReached:
            status.set_text(DAILY_LIMIT_STOP)
            ui.notify(DAILY_LIMIT_STOP, type="warning")
            return
        assert world is not None  # load_world raises on failure
        baseline = await run.io_bound(world.baseline)
        assert baseline is not None
        s.world, s.search, s.selected, s.failure = world, None, None, None
        s.baseline = baseline
        s.role, s.minute = world.roles.roles[0].id, world.scenario.events[0].at_minute
        status.set_text(
            f"Baseline: {len(s.baseline.failures)} diagnosed failures. "
            f"Clause set: {s.baseline.clause_set}"
        )
        clause_set.set_text(f"Clause set: {s.baseline.clause_set}")
        agents_label.set_text(f"Agents: {world.agent_label}" + cache_text(world))
        baseline_view.refresh()
        repairs_view.refresh()
        export_view.refresh()

    async def find_repairs() -> None:
        if s.world is None:
            ui.notify("Run the baseline first.")
            return
        if live_llm(s.world):  # the world in use, not the toggle (it may have changed since)
            # A live repair search is hundreds of paid calls: not approved (PROGRESS P5-4).
            ui.notify(LIVE_SEARCH_REFUSED, type="warning")
            status.set_text(LIVE_SEARCH_REFUSED)
            return
        status.set_text("Replaying every candidate repair on the identical incident ...")
        world = s.world
        try:
            found = await run.io_bound(lambda: search_repairs(world.scenario.id, world=world))
        except DailyLimitReached:
            status.set_text(DAILY_LIMIT_STOP)
            ui.notify(DAILY_LIMIT_STOP, type="warning")
            return
        s.search, s.selected = found, None
        status.set_text(
            f"{len(found.ranked) if found else 0} repairs ranked."
            + (
                f" {len(found.inconclusive)} inconclusive (unranked)."
                if found and found.inconclusive
                else ""
            )
        )
        agents_label.set_text(f"Agents: {world.agent_label}" + cache_text(world))
        repairs_view.refresh()
        export_view.refresh()

    def compare(repair_id: str) -> None:
        if s.search is None:
            return
        s.selected = s.search.comparison(repair_id)
        comparison_view.refresh()
        export_view.refresh()

    run_button.on_click(run_baseline)
    baseline_view()
    ui.button("Find repairs", on_click=find_repairs).classes("mt-2")
    repairs_view()
    export_view()


def cache_text(world: World) -> str:
    if world.cache is None:
        return ""
    st = world.cache.stats
    return f" | decision cache: {st.hits} steps reused, {st.misses} not cached"


def main() -> None:
    ui.run(  # pyright: ignore[reportUnknownMemberType]
        title="CascadeGuard", host="127.0.0.1", port=port(), reload=False, show=False
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
