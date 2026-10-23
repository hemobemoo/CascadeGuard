# 004 — Demo UI (Phase 4)

Not started. Requirements already fixed for this phase:

- **Agent statements** (human decision 5, 2026-10-24): wherever the UI shows agent free text
  (rationale, uncertainty), it shows the same label as the CLI, log and exports: "agent
  statement (unverified; not a finding or a legal conclusion)". Only structured GapClaims become
  candidate findings, always with their citations and qualification.
- Every clause shown carries its status label (`PolicyClause.status_label`, AGENTS.md).
- Repair ranking as in ADR 0001: masked blockers are shown as "masked (goal met another way)";
  repairs with new conflicts are shown as failed repairs with the conflict named, and
  `scripted_agent_limit` tags are visible.
