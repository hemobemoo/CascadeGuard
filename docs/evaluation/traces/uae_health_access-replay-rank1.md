# Replay: owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator

_Hypothetical scenario with synthetic data only. CascadeGuard is decision support, not legal interpretation: no output is a legal conclusion or a confirmed legal gap._

- Scenario: `uae_health_access` (synthetic, hypothetical)
- Clause set: policies/reviewed: reviewed + illustrative clauses
- Agents: scripted agents (scripted_decisions.yaml)
- Outcome: **resolved** (all critical goals met; masked failures may remain); 2 masked failures: cause still present
- Requires authorization: **yes**: creates a permission with no reviewed, binding basis; needs human and institutional approval

## Repair edits (hypothetical rules, not source clauses)

- `assign_owner`: role=health_service_operator, action=reverse_automated_lockouts, deadline_minutes=30
- `define_minimum_data_share`: role=telecom_operator, data_category=network_incident_status, counterpart=health_service_operator

Clauses the repair targets: none

## Recovery goals

| Goal | Baseline | Replay |
|---|---|---|
| patient_access_restored | unmet | met at T+60 |
| alert_cause_known_to_health | unmet | met at T+30 |
| network_incident_reported | met at T+45 | met at T+45 |

## Diagnosed failures

**Removed (the repair removes its cause):**
- `information_deadlock:network_incident_status->health_service_operator`: health_service_operator needs network_incident_status, held by telecom_operator, telecom_regulator, but network_incident_status is outside health_service_operator's information boundary. No clause authorising this share was found. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._
- `orphan_duty:reverse_automated_lockouts`: No role has clear authority to reverse_automated_lockouts. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**Masked (goal met another way; the cause is still present):**
- `orphan_duty:activate_fallback_channel`: No role has clear authority to activate_fallback_channel. Only uncertain authority was found (dha.pp11.4-18-1): binding unknown, conditional, or implied; it requires a determination. Clauses: `dha.pp11.4-18-1` [reviewed (interpreted) · binding unknown].
  _Uncertain in the loaded clause set (policies/reviewed: reviewed + illustrative clauses): only uncertain authority was found (binding unknown, conditional, or implied); it requires a determination. This is not a confirmed legal or standards gap; it needs expert review._
- `undefined_trigger:review_automated_lockouts`: No clause triggers review_automated_lockouts, which reverse_automated_lockouts depends on. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**Remaining:** none

**New conflicts introduced by the repair:** none

## Actions whose verdict changed

- T+30 telecom_operator: share_incident_status -> health_service_operator: rejected -> accepted
- T+60 health_service_operator: reverse_automated_lockouts: rejected -> accepted
- T+75 telecom_regulator: share_incident_status -> health_service_operator: rejected -> accepted

_Scripted agents replay the same decisions; they do not adapt to the repair. A new obligation that no scripted decision fulfils shows up as a missed obligation (for an owner obligation: the finding obligation_overdue, and its orphan duty remains)._
