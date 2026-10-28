# Draft review packet (gate 1)

Prepared 2026-10-28 on main after Phase 6d (`bf753c9`, tag `phase-6d`). It covers every item on
the consolidated review list in `PROGRESS.md`: the 10 drafts from 6c and 6d and the four older
items. **Every clause is `status: draft` and stays so until you decide.** Recommendations are
mine; the decisions are yours.

**How the impact columns were measured.** I set one clause at a time to `reviewed` in a temporary
copy of `policies/reviewed/` and ran the baseline and the repair search. I compared them with
`expected_baseline.yaml` and `expected_repairs.yaml`, and compared every role view (and so every
LLM cache key) with today's. "Reaches" means the roles that get the clause from
`clauses_for_role` (the engine's scope rule). A changed view means a changed cache key: an LLM run
asks that role again (a paid run, gate 4). The scripted default path and the goldens change only
where the table says so.

## Summary

| # | clause id | type | binding | reaches | baseline / goldens if reviewed | open flag | recommendation |
|---|---|---|---|---|---|---|---|
| 1 | `uae.mohap-smart-health.p2-coordination` | national public policy (web transcription) | unknown | policy_legal_adviser | unchanged | none | keep as draft |
| 2 | `uae.mohap-smart-health.p6-cybersecurity` | national public policy (web transcription) | unknown | policy_legal_adviser | unchanged | none | keep as draft |
| 3 | `uae.mohap-smart-health.p7-liability` | national public policy (web transcription) | unknown | policy_legal_adviser | unchanged | none | reviewed, after checking the page |
| 4 | `uae.cyber-strategy-2025.governance-aim` | national strategy (announcement summary, web transcription) | false | policy_legal_adviser | unchanged | NEEDS-HUMAN-JUDGMENT | keep as draft |
| 5 | `uae.cyber-strategy-2025.partnership-aim` | national strategy (announcement summary, web transcription) | false | policy_legal_adviser | unchanged | NEEDS-HUMAN-JUDGMENT | keep as draft |
| 6 | `unesco.ai-ethics.human-oversight` | international precedent (ethical principle) | false | policy_legal_adviser | unchanged | none | reviewed |
| 7 | `unesco.ai-ethics.review-and-correct` | international precedent (ethical principle) | false | policy_legal_adviser | unchanged | none | reviewed |
| 8 | `unesco.ai-ethics.responsibility-accountability` | international precedent (ethical principle) | false | policy_legal_adviser | unchanged | none | reviewed |
| 9 | `oecd.ai-principles.robustness-override` | international precedent (ethical principle) | false | policy_legal_adviser | unchanged | QUESTION (UAE adherence) | reviewed |
| 10 | `oecd.ai-principles.accountability-cooperation` | international precedent (ethical principle) | false | policy_legal_adviser | unchanged | QUESTION (UAE adherence) | reviewed |
| 11 | `dha.pp11.applicability` | health-authority policy | unknown | policy_legal_adviser | unchanged | NEEDS-HUMAN-JUDGMENT | reviewed, binding stays unknown |
| 12 | `dha.pp11.4-18-5` | health-authority policy | unknown | health_service_operator, policy_legal_adviser | unchanged | NEEDS-HUMAN-JUDGMENT | keep as draft |
| 13 | `mocai.ethics.fallback-plan` | ethical principle (national guidance) | false | health_service_operator, policy_legal_adviser | unchanged | NEEDS-HUMAN-JUDGMENT | keep as draft |
| 14 | `eu.gdpr.art33-1` | law (EU); international precedent for the UAE | false | policy_legal_adviser | **baseline and baseline golden change** | MINOR (title) | retitle, then reviewed |

Views changed per clause (out of 36 baseline views): 6 for items 1–11 and 14 (all of them
`policy_legal_adviser`'s), 16 for item 12, and 13 for item 13. The repair search and
`expected_repairs.yaml` are unchanged for all 14.

If you review any of items 1–14, `policy_legal_adviser`'s views and cache keys change. Reviewing
several at once costs the same LLM re-run as reviewing one.

---

## 1. `uae.mohap-smart-health.p2-coordination`

- **Source:** `web/01_uae_smart_health_ai_policy.pdf`, page 3. Priorities and Key Components, 2
  (Building partnerships at all levels and achieving integration), first item.
- **Text:** "Strengthening coordination through national partnerships."
- **Notes:** web transcription — unverified (uaelegislation.gov.ae policy page; MANIFEST.md row
  01). binding unknown: national public policy; legal effect not verified. Public policy
  priority, not legislation: it names no actor, counterpart, data category or deadline, so it
  carries no normalized reading and authorises no share. Cascade: context for the information
  deadlock between the telecom operator and the health service operator
  (network_incident_status); it does not permit the telecom-to-health status share.
- **Binding / type:** unknown; national public policy (MOHAP lead entity), web transcription.
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** none (CLEAN).
- **Recommendation: keep as draft.** It is a six-word priority with no actor or duty, so it gives
  the adviser almost nothing to cite.

## 2. `uae.mohap-smart-health.p6-cybersecurity`

- **Source:** `web/01_uae_smart_health_ai_policy.pdf`, page 4. Priorities and Key Components, 6
  (Ensuring the security and ethics of smart health services), first item.
- **Text:** "Strengthening an integrated cybersecurity system for the healthcare sector."
- **Notes:** web transcription — unverified (uaelegislation.gov.ae policy page; MANIFEST.md row
  01). binding unknown: national public policy; legal effect not verified. Public policy
  priority, not legislation: no reporting duty, regulator or deadline is read from it. Cascade:
  context for the health service operator's security incident at T+15, raised on a suspected
  (unconfirmed) credential-stuffing alert from its own AI fraud model.
- **Binding / type:** unknown; national public policy, web transcription.
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** none (CLEAN).
- **Recommendation: keep as draft.** Like item 1, it is a priority with no duty. The reviewed
  DHA breach clauses already cover the incident.

## 3. `uae.mohap-smart-health.p7-liability`

- **Source:** `web/01_uae_smart_health_ai_policy.pdf`, page 4. Priorities and Key Components, 7
  (Ensuring the ethical use of smart health services and AI), second item.
- **Text:** "Establishing clear medical liability frameworks for the delivery of smart health
  services and the use of artificial intelligence applications across the healthcare sector."
- **Notes:** web transcription — unverified (uaelegislation.gov.ae policy page; MANIFEST.md row
  01). binding unknown: national public policy; legal effect not verified. An aim to establish
  liability frameworks, not a framework and not a duty: it assigns no owner. Cascade: context for
  the orphan duty to review and reverse the AI fraud model's automated lockouts (candidate
  finding: no owner found in the reviewed corpus; cf. uae.ai-charter.human-oversight,
  uae.pdpl.art18-1). Whether the portal's fraud-risk model is an "artificial intelligence
  application" in the policy's sense is not decided.
- **Binding / type:** unknown; national public policy, web transcription.
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** none (CLEAN).
- **Recommendation: reviewed, once you have checked the sentence against the
  uaelegislation.gov.ae page.** It is the only UAE health-sector source that names AI liability.
  The web flag and `binding: unknown` would stay.

## 4. `uae.cyber-strategy-2025.governance-aim`

- **Source:** `web/03_uae_national_cybersecurity_strategy.pdf`, page 2. Cabinet approval
  announcement, 'The strategy seeks to', first item.
- **Text:** "Establish a cohesive and highly effective governance framework for cybersecurity."
- **Notes:** web transcription — unverified (summary of the Cabinet approval announcement;
  MANIFEST.md row 03). Not the strategy text: the Cyber Security Council strategy document is not
  in the repository. Strategy-level context only: no deadline, regulator or reporting duty is
  inferred. Cascade: context for the two security incidents (telecom and health) handled without
  a shared escalation path.
- **Binding / type:** false; national strategy aim, from a summary of an announcement.
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** NEEDS-HUMAN-JUDGMENT (6c, 6d): the file is a composed summary, so it is not
  verified that the wording is the Cabinet's own.
- **Recommendation: keep as draft.** It can't be checked against the Cabinet's own wording until
  the 2025 strategy text or the Cabinet page is in the repository.

## 5. `uae.cyber-strategy-2025.partnership-aim`

- **Source:** `web/03_uae_national_cybersecurity_strategy.pdf`, page 2. Cabinet approval
  announcement, 'The strategy seeks to', fifth item.
- **Text:** "Bolster partnerships and collaborative relations at national and international
  levels."
- **Notes:** web transcription — unverified (summary of the Cabinet approval announcement;
  MANIFEST.md row 03). Not the strategy text. Strategy-level context only: it authorises no data
  share and sets no duty. Cascade: context for the cross-sector information deadlock between the
  telecom and health operators.
- **Binding / type:** false; national strategy aim, from a summary of an announcement.
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** NEEDS-HUMAN-JUDGMENT (same attribution question as item 4).
- **Recommendation: keep as draft.** Same reason as item 4.

## 6. `unesco.ai-ethics.human-oversight`

- **Source:** `UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf`, page 22.
  III.2 Principles, Human oversight and determination, paras 35–36.
- **Text:** "35. Member States should ensure that it is always possible to attribute ethical and
  legal responsibility for any stage of the life cycle of AI systems, as well as in cases of
  remedy related to AI systems, to physical persons or to existing legal entities. Human
  oversight refers thus not only to individual human oversight, but to inclusive public
  oversight, as appropriate. 36. It may be the case that sometimes humans would choose to rely on
  AI systems for reasons of efficacy, but the decision to cede control in limited contexts
  remains that of humans, as humans can resort to AI systems in decision-making and acting, but an
  AI system can never replace ultimate human responsibility and accountability. As a rule, life
  and death decisions should not be ceded to AI systems."
- **Notes:** Official original (SHS/BIO/PI/2021/1, p.2). Not binding: operative para 2
  "Recommends that Member States apply on a voluntary basis the provisions of this
  Recommendation" (p.7). International precedent, not UAE law. Cascade: precedent for a human
  owner of the review and reversal of the automated lockouts (candidate orphan duty; cf.
  uae.ai-charter.human-oversight, uae.pdpl.art18-1).
- **Binding / type:** false; international precedent (UNESCO ethical principle, non-binding
  recommendation).
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** none (CLEAN, checked against the page image).
- **Recommendation: reviewed.** It is quoted word for word from the official original, with no
  gap, and is clearly labelled as a non-binding precedent.

## 7. `unesco.ai-ethics.review-and-correct`

- **Source:** same PDF, page 22. III.2 Principles, Transparency and explainability, para 38.
- **Text:** "In addition, individuals should be able to access the reasons for a decision
  affecting their rights and freedoms, and have the option of making submissions to a designated
  staff member of the private [...] sector company or public sector institution able to review
  and correct the decision."
- **Notes:** Official original (SHS/BIO/PI/2021/1). The [...] skips only the page number "22",
  printed between the bottom of the left column and the top of the right column. Not binding:
  operative para 2, "apply on a voluntary basis" (p.7). International precedent, not UAE law; no
  normalized obligation. Cascade: precedent for a named person able to review and correct the
  fraud model's lockout decisions (candidate finding: no owner found in the reviewed corpus; cf.
  uae.ai-charter.human-oversight, uae.pdpl.art18-1).
- **Binding / type:** false; international precedent (ethical principle).
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** none (CLEAN).
- **Recommendation: reviewed.** Of all the sources, it is the closest precedent for the
  lockout-review owner. The only gap skips a page number.

## 8. `unesco.ai-ethics.responsibility-accountability`

- **Source:** same PDF, page 23. III.2 Principles, Responsibility and accountability, para 43.
- **Text:** "43. Appropriate oversight, impact assessment, audit and due diligence mechanisms,
  including whistle-blowers’ protection, should be developed to ensure accountability for AI
  systems and their impact throughout their life cycle. Both technical and institutional designs
  should ensure auditability and traceability of (the working of) AI systems in particular to
  address any conflicts with human rights norms and standards and threats to environmental and
  ecosystem well-being."
- **Notes:** Official original (SHS/BIO/PI/2021/1). Quoted without a gap (human decision
  2026-10-28): the extraction gives the apostrophe of "whistle-blowers’" as U+2019. Para 42 starts
  on p.22 and ends on p.23, so it is not quoted (a clause cites one page); its last sentence reads
  "The ethical responsibility and liability for the decisions and actions based in any way on an
  AI system should always ultimately be attributable to AI actors corresponding to their role in
  the life cycle of the AI system." Not binding: operative para 2, "apply on a voluntary basis"
  (p.7). International precedent, not UAE law. Cascade: precedent for tracing the lockouts back to
  the telecom traffic model's update.
- **Binding / type:** false; international precedent (ethical principle).
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** none (CLEAN in round 3).
- **Recommendation: reviewed.** The quote is exact and has no gap. It is the only source that
  supports traceability, though less directly than item 7.

## 9. `oecd.ai-principles.robustness-override`

- **Source:** `OECD_Recommendation_AI.pdf`, page 9. Section 1, 1.4 Robustness, security and
  safety, b).
- **Text:** "b) Mechanisms should be in place, as appropriate, to ensure that if AI systems risk
  causing undue harm or exhibit undesired behaviour, they can be overridden, repaired, and/or
  decommissioned safely as needed."
- **Notes:** Official original, OECD/LEGAL/0449 (adopted 22 May 2019; revised 8 November 2023
  and 3 May 2024, p.3). Not binding: "Recommendations are adopted by Council and are not legally
  binding" (OECD Legal Instruments, p.12). The PDF lists no Adherents; UAE adherence not checked.
  International precedent, not UAE law. Cascade: precedent for suspending the telecom
  traffic-management model and reversing the fraud model's automated lockouts.
- **Binding / type:** false; international precedent (OECD principle, non-binding).
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** QUESTION-FOR-HUMAN (6c): does the UAE adhere to OECD/LEGAL/0449? Not checked.
- **Recommendation: reviewed.** The quote is exact, and the jurisdiction field already says
  "UAE adherence not checked", so reviewing it claims nothing about adherence.

## 10. `oecd.ai-principles.accountability-cooperation`

- **Source:** same PDF, page 9. Section 1, 1.5 Accountability, c).
- **Text:** "c) AI actors, should, based on their roles, the context, and their ability to act,
  apply a systematic risk management approach to each phase of the AI system lifecycle on an
  ongoing basis and adopt responsible business conduct to address risks related to AI systems,
  including, as appropriate, via co-operation between different AI actors, suppliers of AI
  knowledge and AI resources, AI system users, and other stakeholders."
- **Notes:** Official original, OECD/LEGAL/0449 (p.3 for dates). The quote ends at a sentence
  boundary; the next sentence only lists examples of risks. Not binding: "Recommendations are
  adopted by Council and are not legally binding" (OECD Legal Instruments, p.12). International
  precedent, not UAE law. Cascade: precedent for co-operation between the two AI actors (telecom
  traffic model, health fraud model) whose interaction caused the lockouts.
- **Binding / type:** false; international precedent (OECD principle, non-binding).
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** same adherence question as item 9.
- **Recommendation: reviewed.** It is the only source that speaks to co-operation between two AI
  actors, which is the cascade's core.

## 11. `dha.pp11.applicability`

- **Source:** `Health Data Protection and Confidentiality Policy_EN2022810559.pdf`, page 1. Cover
  page.
- **Text:** "Applicability: All Healthcare Entities under the Jurisdiction of Dubai Health
  Authority"
- **Notes:** Applies only because the scenario places the portal operator in Dubai. Whether the
  policy is binding (and on whom) is for the human to confirm.
- **Binding / type:** unknown; health-authority policy (DHA, 2022-08-10).
- **Reaches:** policy_legal_adviser. **Baseline/goldens:** unchanged.
- **Open flag:** NEEDS-HUMAN-JUDGMENT (since 6b): does DHA PP-11 bind the synthetic portal
  operator, and on what basis?
- **Recommendation: reviewed, with `binding: unknown` kept.** The quote is exact. Reviewing it
  confirms the text, not the legal effect, and the notes already make the applicability depend
  on the scenario's Dubai premise.

## 12. `dha.pp11.4-18-5`

- **Source:** same PDF, page 32. 4.18.5.
- **Text:** "4.18.5. Breach notifications must be reported to both the UAE Information Office and
  DHA"
- **Notes:** Binding status: see dha.pp11.applicability. The text names "both the UAE Information
  Office and DHA"; only DHA (health_data_oversight) is modelled. The UAE Information Office is out
  of scope for this slice (human decision h2, 2026-10-23). The quote stops before
  "(HISH@dha.gov.ae).", a contact address; no qualifier is lost. The actor is not in this quote:
  it comes from 4.18.4 ("The Entity is required to report breaches/incidents",
  dha.pp11.4-18-4). The two clauses stay separate (human decision 3p, 2026-10-24); the actor's
  source is part of this clause's review.
- **Normalized (interpreted):** obligation; actor health_service_operator; action
  notify_health_data_oversight; condition "a breach notification". Mapping note: the sentence is
  passive and names no actor; the actor is taken from dha.pp11.4-18-4, outside this quote.
- **Binding / type:** unknown; health-authority policy.
- **Reaches:** health_service_operator, policy_legal_adviser. **Baseline/goldens:** unchanged,
  because the reviewed `dha.pp11.4-18-4` already sets the same obligation (same actor and
  action).
- **Open flag:** NEEDS-HUMAN-JUDGMENT (3p): the actor comes from outside the quote.
- **Recommendation: keep as draft.** It adds nothing to the engine beyond `dha.pp11.4-18-4`. Its
  only new content is the recipient, the UAE Information Office, which is out of scope (h2).

## 13. `mocai.ethics.fallback-plan`

- **Source:** `MOCAI-AI-Ethics-EN-1.pdf`, page 16. 3.5.1 (printed page 31).
- **Text:** "AI systems should have safeguards that enable a fallback plan in case of problems."
- **Notes:** Guidance, not law. The text names no actor or action; `health_service_operator` and
  `maintain_fallback_plan` are the scenario's mapping, an interpretation (4d, consistent with h2
  for dha.pp11.4-18-1).
- **Normalized (interpreted):** safeguard; actor health_service_operator; action
  maintain_fallback_plan; condition "in case of problems".
- **Binding / type:** false; ethical principle (UAE national AI ethics guidance).
- **Reaches:** health_service_operator, policy_legal_adviser. **Baseline/goldens:** unchanged,
  because the reviewed `dha.pp11.4-18-1` already sets maintain_fallback_plan for the same actor.
- **Open flag:** NEEDS-HUMAN-JUDGMENT (4d): the actor and action are interpreted; the text says
  only "AI systems".
- **Recommendation: keep as draft.** It repeats a reviewed obligation as a softer safeguard, with
  an actor the text doesn't name. Reviewing it changes 13 views for no change in outcome.

## 14. `eu.gdpr.art33-1`

- **Source:** `GDPR-Regulation (EU) 2016-679.pdf`, page 29. Article 33(1).
- **Title today:** "GDPR: breach notification within 72 hours unless unlikely to result in risk"
- **Text:** "1. In the case of a personal data breach, the controller shall without undue delay
  and, where feasible, not later than 72 hours after having become aware of it, notify the
  personal data breach to the supervisory authority competent in accordance with Article 55,
  unless the personal data breach is unlikely to result in a risk to the rights and freedoms of
  natural persons."
- **Notes:** Not binding in the UAE. Precedent with an explicit regulator-notification deadline.
  No explicit regulator-notification deadline was found in the reviewed corpus for UAE health
  data (see dha.pp11.4-18-4, uae.pdpl.art9-1); candidate finding, not a confirmed gap. The DHA
  policy does state a risk threshold for informing data subjects (4.18.10, PDF page 33) and
  "immediately" for processor-to-controller notice (4.18.7). The PDF is the consolidated text,
  which states it is a documentation tool with no legal effect (PDF page 1). Unchanged by the
  2026 amendment (Regulation (EU) 2026/1744 does not amend Regulation (EU) 2016/679; EUR-Lex lists
  only corrigenda for it; checked on EUR-Lex, 2026-10-23,
  https://eur-lex.europa.eu/eli/reg/2026/1744/oj; that source is not in the reviewed corpus).
- **Binding / type:** false; law (EU regulation), an international precedent for the UAE.
- **Reaches:** policy_legal_adviser.
- **Baseline/goldens: change.** The scripted `policy_legal_adviser` cites this clause at T+60.
  Today that decision is rejected as a `draft_citation`. Once the clause is reviewed:
  - the adviser's `provide_policy_analysis` is accepted;
  - the `draft_citation` finding and the rejected decision disappear;
  - every goal keeps its status.

  `expected_baseline.yaml` must be updated in the same commit, with the reason given (review-loop
  rule 4). `expected_repairs.yaml` is unchanged.
- **Open flag:** MINOR (deferred since 6c): the title leaves out "where feasible".
- **Recommendation: retitle, then reviewed.** For example: "GDPR: breach notification without
  undue delay and, where feasible, within 72 hours". It is the corpus's only explicit
  notification deadline, and reviewing it removes a standing draft-citation finding.

---

## Related open items (no status change needed)

- The ITU report `T-AI4G-AI4GOOD-2025-6-PDF-E.pdf` really does contain U+FFFD in its extracted
  text: 1,294 characters, on page 5 (table-of-contents dot leaders) and pages 41–44 (full stops).
  No clause quotes it. Reported only; nothing changed.
