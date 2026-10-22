# uae_health_access — AI-driven healthcare access disruption

**Everything here is hypothetical.** No real UAE system, organisation or person is described,
and all patient data is synthetic.

## The incident

| Time | What happens | Who learns of it |
|---|---|---|
| T+00 | A telecom AI traffic-management model, newly updated, deprioritises authentication SMS under peak load. One-time passwords arrive late or not at all. | Telecom operator |
| T+15 | Patients retry. The health portal's AI fraud-risk model reads the retries as credential stuffing, locks 4,812 accounts and raises an alert. The alert is **suspected**, not proof of a breach. | Health service operator |
| T+30 | The telecom operator suspects its model. The health operator sees failures and an alert but not the common cause. No intrusion is confirmed. | Both operators, separately |
| T+45 | Every role must decide what to report, what may be shared, who may authorise recovery, and whether to review or reverse the locks. | All six roles |
| T+60 | 3,950 patients are still locked out, most of them SMS-only or over 65. The call centre can verify identity but is not an authorised fallback. | Health operator, Public Access and Inclusion |
| T+75 | The incident window closes. CascadeGuard diagnoses the failure and replays repairs. | — |

## Why it is hard

- **Information deadlock.** The health operator needs to know the failure is network-side, but
  network data is outside its information boundary. No clause authorising a telecom-to-health
  status share was found in the reviewed corpus (Telecom Law pp.13-47 unreadable; cf.
  `uae.fl2-2019.art4`, `uae.fl2-2019.art16`; draft, unreviewed). Candidate finding.
- **Orphan duty.** No owner for reviewing and reversing an automated lockout was found in the
  reviewed corpus for this scenario (Telecom Law pp.13-47 unreadable). Human-oversight principles
  (`uae.ai-charter.human-oversight`, `mocai.ethics.contest-redress`) say it should happen but name
  no owner or deadline; PDPL Art 18(4) assigns review to the Controller on request, but its
  applicability is uncertain (`uae.pdpl.art18-1`, `uae.pdpl.art2-2`). All draft, unreviewed.
  Candidate finding.
- **Mandate overlap.** The DHA policy appears to set the breach-reporting period by reference to
  the PDPL Executive Regulations (`dha.pp11.4-18-4`), while the PDPL may exclude health data that
  has its own legislation (`uae.pdpl.art2-2`). The DHA policy defines that law as Decree-Law
  45/2021 and says the more specialised health regulation supersedes (section 4.2, PDF pages
  9-10). Draft, unreviewed. Candidate finding.
- **Undefined trigger.** No clause was found in the reviewed corpus that triggers escalation when
  an AI fraud alert may be a false positive caused by another organisation's AI (cf.
  `dha.pp11.4-18-2`; draft, unreviewed). Candidate finding.

These are hypotheses for the engine to test (Phase 2), not findings yet. Any gap is reported as
*not found in the reviewed corpus*, never as a confirmed legal gap.

## Applicable health-data regime

This is the project's reading of draft, unreviewed clauses, pending human review; it is not a
legal conclusion. The portal is an ICT use in the area of health, so Federal Law No. 2 of 2019 is
treated as applicable for this scenario (`uae.fl2-2019.art2`, draft). The PDPL excludes personal
health data that has its own legislation (`uae.pdpl.art2-2`, draft), so it is not assumed to
govern the scenario. The scenario places the portal operator in Dubai, so the DHA Health Data
Protection and Confidentiality Policy is treated as applicable too (`dha.pp11.applicability`,
draft, `binding: unknown`).

## Files

- `scenario.yaml` — timeline, facts (with data category, holder and certainty), decision
  points, relevant clauses, review points.
- `roles.yaml` — the six institutional roles, their information boundaries, allowed actions and
  instructions. The Orchestrator is code, not a role.
