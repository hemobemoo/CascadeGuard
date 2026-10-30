"""Governed versus ungoverned run of the identical incident (engine judgement, comparison only).

The ungoverned run (`Governance.OFF`) is never the result and never a golden: it shows what the
waived checks prevent. Both runs use the same scenario, clauses and agents.
"""

from dataclasses import dataclass
from typing import Any

from cascadeguard.engine.constraints import WAIVABLE, Governance
from cascadeguard.simulation.orchestrator import RunResult

GOVERNANCE_NOTE = (
    "Governance off is a comparison mode, not a result: an action the governed engine rejects "
    "only for missing authority, a clause restriction, a missing prerequisite or missing "
    "information is applied anyway and listed as 'would have been rejected'. Role permissions, "
    "information boundaries and the evidence checks (citations, gap wording) apply in both runs."
)
SCRIPTED_GOVERNANCE_NOTE = (
    "Scripted agents make the same decisions in both runs; only the engine's reaction differs. "
    "A comparison of agent behaviour without governance needs LLM agents."
)
WITHHELD_NOTE = (
    "goals, failures and changed actions withheld: {n} steps had no decision ({governed} in the "
    "governed run, {ungoverned} in the ungoverned run), so the runs are not comparable"
)
WAIVED_REASONS = tuple(sorted(r.value for r in WAIVABLE))


@dataclass(frozen=True, slots=True)
class GovernanceComparison:
    governed: RunResult
    ungoverned: RunResult

    def __post_init__(self) -> None:
        if self.governed.governance is not Governance.ON:
            raise ValueError("the governed run must have governance on")
        if self.ungoverned.governance is not Governance.OFF:
            raise ValueError("the ungoverned run must have governance off")
        same = ("scenario_id", "clause_set", "agents", "scripted", "loaded_clauses")
        if any(getattr(self.governed, f) != getattr(self.ungoverned, f) for f in same):
            raise ValueError("both runs must use the same scenario, clauses and agents")

    @property
    def failed_steps(self) -> tuple[tuple[str, int, str, str], ...]:
        return tuple(
            (name, m, r, why)
            for name, result in (("governed", self.governed), ("ungoverned", self.ungoverned))
            for m, r, why in result.failed_steps
        )

    def notes(self) -> tuple[str, ...]:
        if self.governed.scripted and self.ungoverned.scripted:
            return (GOVERNANCE_NOTE, SCRIPTED_GOVERNANCE_NOTE)
        return (GOVERNANCE_NOTE,)

    def waived(self) -> list[dict[str, Any]]:
        """Every action the ungoverned run applied that the governed engine would have rejected."""
        return [
            {
                "minute": e.minute,
                "role": e.role,
                "action": e.action,
                **({"target": e.target} if e.target else {}),
                "would_have_been_rejected": list(e.waived),
                **({"clauses": list(e.clause_ids)} if e.clause_ids else {}),
            }
            for e in self.ungoverned.log
            if e.waived
        ]

    def masked(self) -> tuple[str, ...]:
        """Ungoverned failures whose goal was met in that run although the cause is still
        present (the same diagnosis, examining met goals too)."""
        shown = {f.id for f in self.ungoverned.failures}
        return tuple(f.id for f in self.ungoverned.causes if f.id not in shown)

    def changed_actions(self) -> list[dict[str, Any]]:
        """Actions whose verdict differs between the runs: the n-th proposal of the same action
        (minute, role, action, target, data category) in each run, so repeats are kept apart."""

        def verdicts(result: RunResult) -> dict[tuple[int, str, str, str, str, int], str]:
            seen: dict[tuple[int, str, str, str, str], int] = {}
            out: dict[tuple[int, str, str, str, str, int], str] = {}
            for e in result.log:
                if e.kind in ("accepted", "rejected") and e.action is not None:
                    k = (e.minute, e.role or "", e.action, e.target or "", e.data_category or "")
                    seen[k] = seen.get(k, 0) + 1
                    out[(*k, seen[k])] = e.kind
            return out

        before, after = verdicts(self.governed), verdicts(self.ungoverned)
        return [
            {
                "minute": k[0],
                "role": k[1],
                "action": k[2],
                **({"target": k[3]} if k[3] else {}),
                "governed": before.get(k, "not proposed"),
                "ungoverned": after.get(k, "not proposed"),
            }
            for k in sorted({*before, *after})
            if before.get(k) != after.get(k)
        ]

    def summary(self) -> dict[str, Any]:
        head: dict[str, Any] = {
            "scenario": self.governed.scenario_id,
            "clause_set": self.governed.clause_set,
            "waivable_reasons": list(WAIVED_REASONS),
        }
        if self.failed_steps:  # not comparable, as for an incomplete replay
            return {
                **head,
                "withheld": WITHHELD_NOTE.format(
                    n=len(self.failed_steps),
                    governed=len(self.governed.failed_steps),
                    ungoverned=len(self.ungoverned.failed_steps),
                ),
                "failed_steps": [
                    {"run": run, "minute": m, "role": r, "reason": why}
                    for run, m, r, why in self.failed_steps
                ],
            }

        def goal(m: int | None) -> str:
            return f"met at T+{m}" if m is not None else "unmet"

        on, off = dict(self.governed.goals), dict(self.ungoverned.goals)
        return {
            **head,
            "goals": {g: {"governed": goal(on[g]), "ungoverned": goal(off[g])} for g in on},
            "failures": {
                "governed": [f.id for f in self.governed.failures],
                "ungoverned": [f.id for f in self.ungoverned.failures],
                "ungoverned_cause_still_present": list(self.masked()),
            },
            "would_have_been_rejected": self.waived(),
            "changed_actions": self.changed_actions(),
        }
