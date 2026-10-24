"""CascadeGuard demo UI (Phase 4 skeleton; see specs/004-demo-ui.md).

The UI only displays engine results: every run, search and replay comes from the same helpers
the CLI uses, with scripted agents.
"""

from nicegui import ui

from cascadeguard.cli import run_scenario
from cascadeguard.simulation.loader import SCENARIOS_DIR

PORT = 8765  # 8080 is often taken by other local servers
BANNER = "Hypothetical scenario, synthetic data only. Decision support, not legal interpretation."
SECTIONS = (
    "Timeline",
    "Role views",
    "Dependency graph",
    "Repairs",
    "Baseline vs replay",
    "Export",
)


def scenarios() -> list[str]:
    return sorted(p.name for p in SCENARIOS_DIR.iterdir() if (p / "scenario.yaml").is_file())


@ui.page("/")
def index() -> None:
    ui.label(BANNER).classes("w-full bg-amber-100 text-amber-900 p-2 font-medium")
    ui.label("CascadeGuard").classes("text-2xl font-bold")
    names = scenarios()
    picker = ui.select(names, value=names[0], label="Scenario").classes("w-72")
    status = ui.label("")

    def run() -> None:
        result = run_scenario(str(picker.value))
        status.set_text(
            f"Baseline run: {len(result.log)} log entries, {len(result.failures)} diagnosed "
            f"failures. Clause set: {result.clause_set}"
        )

    ui.button("Run baseline", on_click=run)
    for title in SECTIONS:
        with ui.card().classes("w-full"):
            ui.label(title).classes("text-lg font-semibold")
            ui.label("Not built yet (skeleton).").classes("text-gray-500")


def main() -> None:
    ui.run(title="CascadeGuard", port=PORT, reload=False, show=False)  # pyright: ignore[reportUnknownMemberType]


if __name__ in {"__main__", "__mp_main__"}:
    main()
