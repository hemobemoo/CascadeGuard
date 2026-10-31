# Gap analysis: uae_health_access

_Hypothetical scenario with synthetic data only. CascadeGuard is decision support, not legal interpretation: no output is a legal conclusion or a confirmed legal gap._

Generated from the governed baseline run with scripted agents (clause set: policies/reviewed: reviewed + illustrative clauses) by `scripts/build_reports.py`; regenerate it, never edit it. Each diagnosed failure is a candidate for expert review, not a finding of law: its qualification below is part of it.

The examples are a **DRAFT mapping awaiting the human's approval (gate 7)** (`scenarios/uae_health_access/gap_examples.yaml`). An entry not yet approved is marked so. Foreign and international texts are shown as examples of practice elsewhere, never as UAE law; every clause carries its status label.

## `information_deadlock:network_incident_status->health_service_operator`

- Category: `information_deadlock`; blocks `patient_access_restored`, `alert_cause_known_to_health`; roles `health_service_operator`, `telecom_operator`, `telecom_regulator`.
- Diagnosis: health_service_operator needs network_incident_status, held by telecom_operator, telecom_regulator, but network_incident_status is outside health_service_operator's information boundary. No clause authorising this share was found.
- **Qualification:** _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**UAE clauses considered by the engine:**

- None found in the loaded clause set.

**Examples (context, not UAE law; UAE principles are not binding):**

- `eu.gdpr.art33-1` [reviewed · not binding · foreign precedent], GDPR-Regulation (EU) 2016-679.pdf, p. 29, Article 33(1) (DRAFT, not yet approved). Relevance: A controller's duty to notify a personal data breach to the supervisory authority without undue delay and, where feasible, not later than 72 hours after becoming aware of it, unless the breach is unlikely to result in a risk (EU, not binding in the UAE).
  > 1. In the case of a personal data breach, the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the personal data breach to the supervisory authority competent in accordance with Article 55, unless the personal data breach is unlikely to result in a risk to the rights and freedoms of natural persons.

- `oecd.ai-principles.accountability-cooperation` [reviewed · not binding · international precedent], OECD_Recommendation_AI.pdf, p. 9, Section 1, 1.5 Accountability, c) (DRAFT, not yet approved). Relevance: Risk management by AI actors, including, as appropriate, co-operation between AI actors, AI system users and other stakeholders (a non-binding recommendation).
  > c) AI actors, should, based on their roles, the context, and their ability to act, apply a systematic risk management approach to each phase of the AI system lifecycle on an ongoing basis and adopt responsible business conduct to address risks related to AI systems, including, as appropriate, via co-operation between different AI actors, suppliers of AI knowledge and AI resources, AI system users, and other stakeholders.

**Repairs tested by replay (hypothetical rules, scripted agents):**

- Remove its cause: rank 1 `owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 2 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 3 `share.network_incident_status.telecom_operator.health_service_operator+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 6 `share.network_incident_status.telecom_operator.health_service_operator` (partial; requires authorization (needs human and institutional approval)); rank 11 `requester.activate_fallback_channel.health_service_operator.health_data_oversight.t60_public_access_affected.15m+share.network_incident_status.telecom_operator.health_service_operator` (introduces new conflict; requires authorization (needs human and institutional approval)); rank 12 `requester.activate_fallback_channel.health_service_operator.telecom_regulator.t60_public_access_affected.15m+share.network_incident_status.telecom_operator.health_service_operator` (introduces new conflict; requires authorization (needs human and institutional approval)).
- Only mask it (goal met another way; cause still present): none.

## `orphan_duty:activate_fallback_channel`

- Category: `orphan_duty`; blocks `patient_access_restored`; roles `health_service_operator`.
- Diagnosis: No role has clear authority to activate_fallback_channel. Only uncertain authority was found (dha.pp11.4-18-1): binding unknown, conditional, or implied; it requires a determination.
- **Qualification:** _Uncertain in the loaded clause set (policies/reviewed: reviewed + illustrative clauses): only uncertain authority was found (binding unknown, conditional, or implied); it requires a determination. This is not a confirmed legal or standards gap; it needs expert review._

**UAE clauses considered by the engine:**

- `dha.pp11.4-18-1` [reviewed (interpreted) · binding unknown], Health Data Protection and Confidentiality Policy_EN2022810559.pdf, p. 30, 4.18.1:
  > 4.18.1. Entities must establish breach/incidence response management (Incident Response and Business Continuity) and recovery (Incident Recovery and Disaster Recovery) plans that comprise of:

**Examples (context, not UAE law; UAE principles are not binding):**

- `unesco.ai-ethics.responsibility-accountability` [reviewed · not binding · international precedent], UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf, p. 23, III.2 Principles, Responsibility and accountability, para 43 (DRAFT, not yet approved). Relevance: Appropriate oversight, audit and due-diligence mechanisms to ensure accountability for AI systems and their impact (a non-binding recommendation).
  > 43. Appropriate oversight, impact assessment, audit and due diligence mechanisms, including whistle-blowers’ protection, should be developed to ensure accountability for AI systems and their impact throughout their life cycle. Both technical and institutional designs should ensure auditability and traceability of (the working of) AI systems in particular to address any conflicts with human rights norms and standards and threats to environmental and ecosystem well-being.

**Repairs tested by replay (hypothetical rules, scripted agents):**

- Remove its cause: rank 2 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 4 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+owner.reverse_automated_lockouts.health_service_operator.30m` (partial; requires authorization (needs human and institutional approval)); rank 5 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 7 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m` (partial; requires authorization (needs human and institutional approval)); rank 13 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+requester.activate_fallback_channel.health_service_operator.health_data_oversight.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)); rank 14 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+requester.activate_fallback_channel.health_service_operator.telecom_regulator.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)).
- Only mask it (goal met another way; cause still present): rank 1 `owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)).

## `orphan_duty:reverse_automated_lockouts`

- Category: `orphan_duty`; blocks `patient_access_restored`; roles `health_service_operator`.
- Diagnosis: No role has clear authority to reverse_automated_lockouts.
- **Qualification:** _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**UAE clauses considered by the engine:**

- None found in the loaded clause set.

**Examples (context, not UAE law; UAE principles are not binding):**

- `oecd.ai-principles.robustness-override` [reviewed · not binding · international precedent], OECD_Recommendation_AI.pdf, p. 9, Section 1, 1.4 Robustness, security and safety, b) (DRAFT, not yet approved). Relevance: Mechanisms, as appropriate, so that an AI system that risks causing undue harm or behaves in an undesired way can be overridden, repaired or decommissioned safely (a non-binding recommendation).
  > b) Mechanisms should be in place, as appropriate, to ensure that if AI systems risk causing undue harm or exhibit undesired behaviour, they can be overridden, repaired, and/or decommissioned safely as needed.

- `unesco.ai-ethics.review-and-correct` [reviewed · not binding · international precedent], UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf, p. 22, III.2 Principles, Transparency and explainability, para 38 (DRAFT, not yet approved). Relevance: A designated staff member to whom individuals can make submissions, able to review and correct a decision affecting their rights and freedoms (a non-binding recommendation).
  > In addition, individuals should be able to access the reasons for a decision affecting their rights and freedoms, and have the option of making submissions to a designated staff member of the private [...] sector company or public sector institution able to review and correct the decision.

- `uae.ai-charter.human-oversight` [reviewed (interpreted) · not binding], The UAE Charter for the Development and Use of Artificial Intelligence.pdf, p. 4, General Principles of the Charter, 6 (DRAFT, not yet approved). Relevance: A UAE principle (not binding) on human oversight to correct errors of AI.
  > 6. Human Oversight: The Charter emphasizes the irreplaceable value of human judgment and human oversight over AI, aligning with ethical values and social standards to correct any errors or biases that may arise.

**Repairs tested by replay (hypothetical rules, scripted agents):**

- Remove its cause: rank 1 `owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 4 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+owner.reverse_automated_lockouts.health_service_operator.30m` (partial; requires authorization (needs human and institutional approval)); rank 8 `owner.reverse_automated_lockouts.health_service_operator.30m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 10 `owner.reverse_automated_lockouts.health_service_operator.30m` (partial; requires authorization (needs human and institutional approval)); rank 17 `owner.reverse_automated_lockouts.health_service_operator.30m+requester.activate_fallback_channel.health_service_operator.health_data_oversight.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)); rank 18 `owner.reverse_automated_lockouts.health_service_operator.30m+requester.activate_fallback_channel.health_service_operator.telecom_regulator.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)).
- Only mask it (goal met another way; cause still present): rank 2 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 5 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 7 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m` (partial; requires authorization (needs human and institutional approval)); rank 13 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+requester.activate_fallback_channel.health_service_operator.health_data_oversight.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)); rank 14 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+requester.activate_fallback_channel.health_service_operator.telecom_regulator.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)).

## `undefined_trigger:review_automated_lockouts`

- Category: `undefined_trigger`; blocks `patient_access_restored`; roles `health_service_operator`.
- Diagnosis: No clause triggers review_automated_lockouts, which reverse_automated_lockouts depends on.
- **Qualification:** _Not found in the loaded clause set (policies/reviewed: reviewed + illustrative clauses). An absent provision is not a confirmed legal or standards gap; it needs expert review._

**UAE clauses considered by the engine:**

- None found in the loaded clause set.

**Other loaded clauses on this action (not counted by the diagnosis):**

- `uae.ai-charter.human-oversight` [reviewed (interpreted) · not binding]: read as a `safeguard` for `review_automated_lockouts`; condition: an AI output may be erroneous.

**Examples (context, not UAE law; UAE principles are not binding):**

- `unesco.ai-ethics.human-oversight` [reviewed · not binding · international precedent], UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf, p. 22, III.2 Principles, Human oversight and determination, paras 35-36 (DRAFT, not yet approved). Relevance: Ultimate human responsibility for decisions taken with AI systems (a non-binding recommendation).
  > 35. Member States should ensure that it is always possible to attribute ethical and legal responsibility for any stage of the life cycle of AI systems, as well as in cases of remedy related to AI systems, to physical persons or to existing legal entities. Human oversight refers thus not only to individual human oversight, but to inclusive public oversight, as appropriate. 36. It may be the case that sometimes humans would choose to rely on AI systems for reasons of efficacy, but the decision to cede control in limited contexts remains that of humans, as humans can resort to AI systems in decision-making and acting, but an AI system can never replace ultimate human responsibility and accountability. As a rule, life and death decisions should not be ceded to AI systems.

- `uae.ai-charter.human-oversight` [reviewed (interpreted) · not binding], The UAE Charter for the Development and Use of Artificial Intelligence.pdf, p. 4, General Principles of the Charter, 6 (DRAFT, not yet approved). Relevance: A UAE principle (not binding) on human oversight to correct errors of AI.
  > 6. Human Oversight: The Charter emphasizes the irreplaceable value of human judgment and human oversight over AI, aligning with ethical values and social standards to correct any errors or biases that may arise.

**Repairs tested by replay (hypothetical rules, scripted agents):**

- Remove its cause: rank 3 `share.network_incident_status.telecom_operator.health_service_operator+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 5 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 8 `owner.reverse_automated_lockouts.health_service_operator.30m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial; requires authorization (needs human and institutional approval)); rank 9 `trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (partial); rank 15 `requester.activate_fallback_channel.health_service_operator.health_data_oversight.t60_public_access_affected.15m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (introduces new conflict); rank 16 `requester.activate_fallback_channel.health_service_operator.telecom_regulator.t60_public_access_affected.15m+trigger.review_automated_lockouts.health_service_operator.t45_responsibilities_diverge.15m` (introduces new conflict).
- Only mask it (goal met another way; cause still present): rank 1 `owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 2 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+share.network_incident_status.telecom_operator.health_service_operator` (resolved; requires authorization (needs human and institutional approval)); rank 4 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+owner.reverse_automated_lockouts.health_service_operator.30m` (partial; requires authorization (needs human and institutional approval)); rank 7 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m` (partial; requires authorization (needs human and institutional approval)); rank 13 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+requester.activate_fallback_channel.health_service_operator.health_data_oversight.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)); rank 14 `fallback.activate_fallback_channel.health_service_operator.t60_public_access_affected.15m+requester.activate_fallback_channel.health_service_operator.telecom_regulator.t60_public_access_affected.15m` (introduces new conflict; requires authorization (needs human and institutional approval)).
