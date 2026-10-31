# Governed vs ungoverned: uae_health_access

_Hypothetical scenario with synthetic data only. CascadeGuard is decision support, not legal interpretation: no output is a legal conclusion or a confirmed legal gap._

**GOVERNANCE OFF: comparison only, not the governed result.**

_Governance off is a comparison mode, not a result: an action the governed engine rejects only for missing authority, a clause restriction, a missing prerequisite or missing information is applied anyway and listed as 'would have been rejected'. Role permissions, information boundaries and the evidence checks (citations, gap wording) apply in both runs._

- Scenario: `uae_health_access` (synthetic, hypothetical)
- Clause set: policies/reviewed: reviewed + illustrative clauses
- Agents: scripted agents (scripted_decisions.yaml)
- Waived in the ungoverned run: `authority_uncertain`, `missing_information`, `missing_prerequisite`, `no_authority`, `restricted_by_clause`

## Recovery goals

| Goal | Governed | Ungoverned |
|---|---|---|
| patient_access_restored | unmet | met at T+60 |
| alert_cause_known_to_health | unmet | unmet |
| network_incident_reported | met at T+45 | met at T+45 |

## Diagnosed failures

**Governed:**
- `information_deadlock:network_incident_status->health_service_operator`: health_service_operator needs network_incident_status, held by telecom_operator, telecom_regulator, but network_incident_status is outside health_service_operator's information boundary. No clause authorising this share was found. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._
- `orphan_duty:activate_fallback_channel`: No role has clear authority to activate_fallback_channel. Only uncertain authority was found (dha.pp11.4-18-1): binding unknown, conditional, or implied; it requires a determination. Clauses: `dha.pp11.4-18-1` [reviewed (interpreted) · binding unknown].
  _Uncertain in the loaded clause set (policies/reviewed: reviewed + illustrative clauses): only uncertain authority was found (binding unknown, conditional, or implied); it requires a determination. This is not a confirmed legal or standards gap; it needs expert review._
- `orphan_duty:reverse_automated_lockouts`: No role has clear authority to reverse_automated_lockouts. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._
- `undefined_trigger:review_automated_lockouts`: No clause triggers review_automated_lockouts, which reverse_automated_lockouts depends on. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**Ungoverned:**
- `information_deadlock:network_incident_status->health_service_operator`: health_service_operator needs network_incident_status, held by telecom_operator, telecom_regulator, but network_incident_status is outside health_service_operator's information boundary. No clause authorising this share was found. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**Ungoverned, goal met but the cause is still present:**
- `orphan_duty:activate_fallback_channel`: No role has clear authority to activate_fallback_channel. Only uncertain authority was found (dha.pp11.4-18-1): binding unknown, conditional, or implied; it requires a determination. Clauses: `dha.pp11.4-18-1` [reviewed (interpreted) · binding unknown].
  _Uncertain in the loaded clause set (policies/reviewed: reviewed + illustrative clauses): only uncertain authority was found (binding unknown, conditional, or implied); it requires a determination. This is not a confirmed legal or standards gap; it needs expert review._
- `orphan_duty:reverse_automated_lockouts`: No role has clear authority to reverse_automated_lockouts. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._
- `undefined_trigger:review_automated_lockouts`: No clause triggers review_automated_lockouts, which reverse_automated_lockouts depends on. Clauses: none.
  _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

## Applied only because governance was off

- T+60 health_service_operator: reverse_automated_lockouts: would have been rejected (missing_information, no_authority). Clauses: none.
- T+60 health_service_operator: activate_fallback_channel: would have been rejected (authority_uncertain). Clauses: `dha.pp11.4-18-1` [reviewed (interpreted) · binding unknown].
- T+60 health_data_oversight: issue_determination: would have been rejected (authority_uncertain). Clauses: `uae.fl2-2019.art6` [reviewed (interpreted) · binding · English translation].

## Actions whose verdict changed

- T+60 health_data_oversight: issue_determination: rejected -> accepted
- T+60 health_service_operator: activate_fallback_channel: rejected -> accepted
- T+60 health_service_operator: reverse_automated_lockouts: rejected -> accepted

_Scripted agents make the same decisions in both runs; only the engine's reaction differs. A comparison of agent behaviour without governance needs LLM agents._
