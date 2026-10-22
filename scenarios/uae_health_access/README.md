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
  network data is outside its information boundary. No clause in the reviewed corpus authorises
  a telecom-to-health status share.
- **Orphan duty.** No clause assigns anyone to review and reverse an automated lockout.
  Human-oversight principles (the UAE AI Charter, MOCAI ethics) say it should happen, but name
  no owner or deadline.
- **Mandate overlap.** The DHA policy sets the breach-reporting period by reference to the PDPL
  Executive Regulations, but the PDPL excludes health data that has its own legislation.
- **Undefined trigger.** No reviewed clause triggers escalation when an AI fraud alert may be a
  false positive caused by another organisation's AI.

These are hypotheses for the engine to test (Phase 2), not findings yet. Any gap is reported as
*not found in the reviewed corpus*, never as a confirmed legal gap.

## Applicable health-data regime

The portal is an ICT use in the area of health, so Federal Law No. 2 of 2019 applies
(`uae.fl2-2019.art2`). The PDPL excludes personal health data that has its own legislation
(`uae.pdpl.art2-2`), so it is not assumed to govern the scenario. The scenario places the portal
operator in Dubai, so the DHA Health Data Protection and Confidentiality Policy also applies
(`dha.pp11.applicability`).

## Files

- `scenario.yaml` — timeline, facts (with data category, holder and certainty), decision
  points, relevant clauses, review points.
- `roles.yaml` — the six institutional roles, their information boundaries, allowed actions and
  instructions. The Orchestrator is code, not a role.
