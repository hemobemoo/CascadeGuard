# Baseline: uae_health_access

_Hypothetical scenario with synthetic data only. CascadeGuard is decision support, not legal interpretation: no output is a legal conclusion or a confirmed legal gap._

```text
Scenario: uae_health_access (synthetic, hypothetical)
Clause set: policies/reviewed: reviewed + illustrative clauses
Agents: scripted agents (scripted_decisions.yaml)
  21 clauses loaded
  21 draft clauses not loaded (awaiting human review)
  Decisions citing drafts are rejected; diagnosis covers loaded clauses only
  - dha.pp11.4-18-1 [reviewed (interpreted) · binding unknown]
  - dha.pp11.4-18-2 [reviewed (interpreted) · binding unknown]
  - dha.pp11.4-18-4 [reviewed (interpreted) · binding unknown]
  - dha.pp11.applicability [reviewed · binding unknown]
  - eu.gdpr.art33-1 [reviewed · not binding · foreign precedent]
  - illus.telecom.incident-report [illustrative]
  - illus.telecom.regulator-information-request [illustrative]
  - oecd.ai-principles.accountability-cooperation [reviewed · not binding · international precedent]
  - oecd.ai-principles.robustness-override [reviewed · not binding · international precedent]
  - uae.ai-charter.human-oversight [reviewed (interpreted) · not binding]
  - uae.ai-charter.safety [reviewed · not binding]
  - uae.fl2-2019.art16 [reviewed (interpreted) · binding · English translation]
  - uae.fl2-2019.art16-exceptions [reviewed · binding · English translation]
  - uae.fl2-2019.art2 [reviewed · binding · English translation]
  - uae.fl2-2019.art4 [reviewed (interpreted) · binding · English translation]
  - uae.fl2-2019.art6 [reviewed (interpreted) · binding · English translation]
  - uae.mohap-smart-health.p7-liability [reviewed · binding unknown · web transcription]
  - uae.pdpl.art2-2 [reviewed · binding · English translation]
  - unesco.ai-ethics.human-oversight [reviewed · not binding · international precedent]
  - unesco.ai-ethics.responsibility-accountability [reviewed · not binding · international precedent]
  - unesco.ai-ethics.review-and-correct [reviewed · not binding · international precedent]

Timeline
T+00  AI traffic-management error
  obligation_opened telecom_operator: report_to_telecom_regulator  {illus.telecom.incident-report [illustrative]}
  ACCEPTED telecom_operator: investigate_network_fault
T+15  A second AI system compounds the failure
  obligation_opened health_service_operator: raise_security_incident (uncertain: binding unknown)  {dha.pp11.4-18-2 [reviewed (interpreted) · binding unknown]}
  obligation_opened health_service_operator: notify_health_data_oversight (uncertain: binding unknown)  {dha.pp11.4-18-4 [reviewed (interpreted) · binding unknown]}
  ACCEPTED health_service_operator: raise_security_incident
  obligation_fulfilled health_service_operator: raise_security_incident  {dha.pp11.4-18-2 [reviewed (interpreted) · binding unknown]}
T+30  The evidence is incomplete
  ACCEPTED health_service_operator: request_information -> telecom_operator  network_incident_status from telecom_operator
  REJECTED health_service_operator: share_incident_status -> telecom_operator  (outside_recipient_boundary, authority_uncertain)  {uae.fl2-2019.art16 [reviewed (interpreted) · binding · English translation], uae.fl2-2019.art4 [reviewed (interpreted) · binding · English translation]}  locked_account_records (patient_account_records) to telecom_operator; authority uncertain - requires determination (the clause depends on a condition the engine cannot evaluate; it never decides the condition is met)
  REJECTED telecom_operator: share_incident_status -> health_service_operator  (outside_recipient_boundary)  otp_delivery_status (network_incident_status) to health_service_operator
T+45  Institutional responsibilities diverge
  ACCEPTED health_service_operator: notify_health_data_oversight
  obligation_fulfilled health_service_operator: notify_health_data_oversight  {dha.pp11.4-18-4 [reviewed (interpreted) · binding unknown]}
  ACCEPTED health_service_operator: review_automated_lockouts
  ACCEPTED telecom_operator: report_to_telecom_regulator
  obligation_fulfilled telecom_operator: report_to_telecom_regulator  {illus.telecom.incident-report [illustrative]}
  goal_met telecom_operator: network_incident_reported
  ACCEPTED telecom_regulator: request_information -> telecom_operator  network_incident_status from telecom_operator
  ACCEPTED policy_legal_adviser: provide_policy_analysis
T+60  Public access is affected
  REJECTED health_service_operator: reverse_automated_lockouts  (missing_information, no_authority)  has not seen network_incident_status; no loaded clause gives this role authority
  REJECTED health_service_operator: activate_fallback_channel  (authority_uncertain)  {dha.pp11.4-18-1 [reviewed (interpreted) · binding unknown]}  authority uncertain - requires determination (the clause depends on a condition the engine cannot evaluate; it never decides the condition is met)
  ACCEPTED telecom_operator: share_incident_status -> telecom_regulator  otp_delivery_status (network_incident_status) to telecom_regulator
  REJECTED health_data_oversight: issue_determination  (authority_uncertain)  {uae.fl2-2019.art6 [reviewed (interpreted) · binding · English translation]}  authority uncertain - requires determination (the clause depends on a condition the engine cannot evaluate; it never decides the condition is met)
  ACCEPTED public_access_inclusion: assess_access_impact
  ACCEPTED public_access_inclusion: recommend_measure -> health_service_operator
  ACCEPTED policy_legal_adviser: provide_policy_analysis
T+75  End of the incident window
  REJECTED telecom_regulator: share_incident_status -> health_service_operator  (outside_recipient_boundary)  otp_delivery_status (network_incident_status) to health_service_operator

Obligations
  illus.telecom.incident-report [illustrative]: telecom_operator report_to_telecom_regulator, due T+60, fulfilled T+45
  dha.pp11.4-18-2 [reviewed (interpreted) · binding unknown]: health_service_operator raise_security_incident, due undetermined, fulfilled T+15, uncertain (binding unknown)
  dha.pp11.4-18-4 [reviewed (interpreted) · binding unknown]: health_service_operator notify_health_data_oversight, due undetermined, fulfilled T+45, uncertain (binding unknown)

Recovery goals
  patient_access_restored: UNMET
  alert_cause_known_to_health: UNMET
  network_incident_reported: met at T+45

Findings
  T+15 deadline_undetermined: the deadline for raise_security_incident cannot be determined from the loaded clauses  {dha.pp11.4-18-2 [reviewed (interpreted) · binding unknown]}
  T+15 deadline_undetermined: the deadline for notify_health_data_oversight cannot be determined from the loaded clauses  {dha.pp11.4-18-4 [reviewed (interpreted) · binding unknown]}

Diagnosed coordination failures
  [information_deadlock] network_incident_status->health_service_operator
    health_service_operator needs network_incident_status, held by telecom_operator, telecom_regulator, but network_incident_status is outside health_service_operator's information boundary. No clause authorising this share was found.
    blocks: patient_access_restored, alert_cause_known_to_health; roles: health_service_operator, telecom_operator, telecom_regulator
    Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review.
  [orphan_duty] activate_fallback_channel
    No role has clear authority to activate_fallback_channel. Only uncertain authority was found (dha.pp11.4-18-1): binding unknown, conditional, or implied; it requires a determination.
    clauses: dha.pp11.4-18-1 [reviewed (interpreted) · binding unknown]
    blocks: patient_access_restored; roles: health_service_operator
    Uncertain in the loaded clause set (policies/reviewed: reviewed + illustrative clauses): only uncertain authority was found (binding unknown, conditional, or implied); it requires a determination. This is not a confirmed legal or standards gap; it needs expert review.
  [orphan_duty] reverse_automated_lockouts
    No role has clear authority to reverse_automated_lockouts.
    blocks: patient_access_restored; roles: health_service_operator
    Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review.
  [undefined_trigger] review_automated_lockouts
    No clause triggers review_automated_lockouts, which reverse_automated_lockouts depends on.
    blocks: patient_access_restored; roles: health_service_operator
    Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review.
```
