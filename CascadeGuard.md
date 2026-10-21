# CascadeGuard  
**Cross-Agency Policy Crash-Testing for AI-Dependent Public Services**

### Final project concept

Find where AI decisions and institutional rules collide. Test the smallest safe repair.

An evidence-grounded, multi-agent simulation and policy-failure discovery platform for the ITU AI for Good Sandbox Hackathon — United Arab Emirates.

---

## 1. Executive summary

CascadeGuard is a multi-agent AI governance stress-testing platform that discovers how AI failures can cascade across institutions, exposing gaps in responsibilities, policy, incident escalation, information-sharing, and human recourse.

Using a UAE-grounded knowledge base and simulated institutional agents, CascadeGuard introduces incidents progressively, as different actors receive incomplete and sometimes conflicting information. It identifies the specific decisions and dependencies that prevent a critical public service from recovering, links each suspected policy gap to its supporting evidence, and proposes the smallest feasible coordination repair that preserves all verified legal safeguards.

The system then replays the identical incident with the proposed repair, checks whether the failure is resolved, and records any remaining or newly introduced conflicts.

Its distinctive contribution is the combination of cross-agency failure discovery, constrained policy repair, counterfactual replay, and a reusable dataset of evidence-backed policy failure scenarios.

The platform is decision support for policy experts and service operators. It does not issue binding legal interpretations, authorize data access, or execute changes in real public infrastructure.

---

## 2. The problem

AI systems increasingly participate in complex public-service workflows, where one system's output can influence another organization's operational decisions.

An AI error can create consequences beyond the system that generated it. A network-management model may disrupt authentication messages; a healthcare fraud detector may interpret the resulting retries as malicious behaviour; and an incident-response process may then trigger actions based on a misleading alert.

Each organization may follow its own documented process while the combined response remains ineffective.

The critical weaknesses may include:

- No clearly assigned responsibility for reversing an incorrect automated decision.
- Conflicting or unclear responsibilities between service operators and regulators.
- An information-sharing dependency that cannot be resolved within the incident's timeline.
- Missing escalation triggers for AI-generated false positives.
- Inadequate mechanisms for affected users to contest an automated lockout.
- No clearly authorized fallback procedure that maintains essential service access.

CascadeGuard turns these potential coordination weaknesses into reproducible tests.

---

## 3. Primary use case: AI-driven healthcare access disruption

The first implementation will simulate a combined telecom and healthcare incident in which two AI-enabled systems interact unexpectedly.

### The incident timeline

All events below are hypothetical scenario injects, not claims about actual UAE systems.

1. **T+00 — An AI-driven network-management error**  
   Under heavy network load, a simulated telecom traffic-management model incorrectly deprioritizes authentication SMS messages. One-time passwords begin arriving late or not at all.

2. **T+15 — A second AI system compounds the failure**  
   Patients repeatedly retry authentication. The healthcare portal's simulated AI fraud-risk model classifies the unusual retry pattern as possible credential stuffing, automatically locking accounts and raising a suspicious-access alert.

3. **T+30 — The evidence is incomplete**  
   The telecom operator has partial evidence of a traffic-management problem. The health service operator sees authentication failures and a security alert but does not yet know their common cause.

4. **T+45 — Institutional responsibilities diverge**  
   Different actors must determine what should be reported, which information can be shared, who may authorize recovery actions, and whether the automated account locks should be reviewed or reversed.

5. **T+60 — Public access is affected**  
   Some patients remain unable to use the digital service. People with limited alternative connectivity, limited digital access, or dependence on the affected authentication channel may face additional barriers.

6. **T+75 — CascadeGuard diagnoses the failure**  
   The platform identifies any unresolved handoffs, constraints, missing triggers, or unclear responsibilities supported by the scenario evidence and relevant policy corpus. It proposes candidate repairs and tests them through replay.

The security alert is not automatically treated as proof of a data breach. Whether unauthorized access actually occurred remains uncertain until further evidence is available.

This distinction forces the agents to reason under uncertainty instead of allowing an early AI-generated alert to become an unquestioned fact.

---

## 4. How CascadeGuard works

1. **Policy knowledge base**  
   Verified UAE laws, standards, institutional mandates, and carefully selected global precedents.

2. **Multi-agent incident simulation**  
   Independent institutional roles receive progressively released events and different information.

3. **Deterministic constraint and dependency analysis**  
   Trace decisions, permissions, obligations, handoffs, deadlines, and unresolved dependencies.

4. **Evidence-backed policy-gap diagnosis**  
   Classify the failure and distinguish a verified conflict from a suspected gap or missing evidence.

5. **Constrained repair and counterfactual replay**  
   Test the smallest permissible coordination changes against the identical incident sequence.

6. **Auditable failure-case dataset**  
   Publish structured scenario records, evidence, tested repairs, and replay outcomes.

### The five failure categories

Each suspected policy or coordination failure is classified into a consistent taxonomy.

| Category                    | What it identifies                                                                                                        |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------------|
| Orphan duty                 | An essential obligation has no clearly designated owner.                                                                  |
| Mandate overlap or conflict | Responsibilities overlap or relevant institutional requirements conflict.                                                 |
| Information deadlock        | A required decision depends on information whose availability or authorized sharing is unresolved.                        |
| Temporal infeasibility      | Required actions cannot be completed within the applicable deadline or incident sequence under the simulated constraints. |
| Undefined trigger           | No applicable trigger is found for escalation, human review, reporting, or recovery in the reviewed policy corpus.        |

The last category needs particular care. A system cannot prove that a legal rule does not exist simply because retrieval fails to find it. CascadeGuard must distinguish an absent provision in the reviewed corpus from a confirmed legal or standards gap.

---

## 5. Multi-agent architecture

The platform will simulate seven distinct roles. These are functional roles, not representations of real government agencies or official positions.

| Agent or component                             | Primary responsibility                                                                                                                                                  |
|------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Health Service Operator                        | Tracks patient access, authentication failures, service status, and recovery options.                                                                                   |
| Telecom Operator                               | Evaluates network evidence and the behaviour of its simulated AI traffic-management pipeline.                                                                           |
| Telecom Regulator                              | Reviews telecom-related responsibilities, relevant regulatory obligations, and escalation options.                                                                      |
| Relevant Health-Data or Privacy Oversight Role | Evaluates applicable data-governance obligations and information-sharing constraints. Its authority must be defined from the verified legal regime rather than assumed. |
| Public Access and Inclusion Role               | Assesses accessibility, alternative channels, and the impact on affected users.                                                                                         |
| Policy and Legal Adviser                       | Retrieves applicable provisions, compares them with global precedents, and explains uncertainty and potential gaps.                                                     |
| Orchestrator                                   | Controls the event timeline, maintains each role's information boundary, coordinates handoffs, and records the sequence of decisions.                                   |

The Constraint and Replay Engine operates alongside these roles as a deterministic component rather than another LLM agent.

It checks proposed actions against structured obligations and restrictions, tracks dependencies, searches the fixed repair space, and compares baseline and repaired scenario results.

The system should log the information available to each role at each time, source passages retrieved, constraints checked, actions proposed, concise decision rationales, unresolved issues, and final replay results. This creates an inspectable audit trail without relying on raw internal model reasoning as the sole evidence of correctness.

---

## 6. The core innovation: minimum-repair counterfactual replay

This is the most important feature of the project.

CascadeGuard does not stop after identifying a failure. It tests whether a specific change actually resolves it.

### Fixed repair grammar

The engine generates candidate repairs from five predefined edit types:

1. Assign an owner to an unresolved handoff or operational responsibility.
2. Add an escalation trigger for a defined incident condition.
3. Define an authorized minimum data-share that allows a necessary decision without unnecessary disclosure.
4. Add a fallback-channel rule for when the primary service becomes unavailable.
5. Designate a decision-requester responsible for obtaining a determination from the appropriate authority.

These are deliberately narrow changes, not free-form proposals to rewrite legislation.

Every repair must preserve prohibitions and other verified constraints. New permissions can be used only when an existing, applicable authority supports them. A proposed new legal or policy permission must instead be recorded as a change requiring appropriate human and institutional approval.

### Formal optimization objective

The engine searches for a minimum-edit repair subject to hard constraints:

- No prohibited action becomes permitted.
- Every newly proposed permission has a verified basis or is marked as requiring authorization.
- Critical recovery blockers are reduced or removed.
- Any unresolved issue requiring expert judgment remains explicit.

The optimization is lexicographic: preserve safeguards first, remove critical blockers second, and minimize the number of repair edits third.

If one repair removes a blocker but creates another conflict, the engine records the failed repair and identifies the new conflict.

### Illustrative result

**What the judge sees**

**Baseline failure**  
Problem: The health service receives insufficient information to distinguish a network-side authentication problem from a suspected security incident. Recovery responsibility is unresolved.

**Repair 1**  
Candidate change: Define an authorized minimum incident-status message between the relevant operators, assuming the required authority exists.  
Replay result: The additional information may resolve the initial uncertainty, but account lockouts persist.

**Second-order failure**  
New finding: The simulation has no supported handoff for reviewing and reversing an automated lockout when the original risk signal is disputed.

**Repair 2 — candidate outcome**  
Candidate change: Assign the existing authorized recovery process an explicit owner and define an escalation trigger for human review.  
Replay result: If the verified rules and operational model allow it, the recovery path becomes available while the security safeguards remain intact. Otherwise, the remaining blocker is documented.

This sequence illustrates the expected method and output. It is not a completed experiment or a claim of measured success.

The second-order failure is especially valuable because it demonstrates why a single recommendation is not enough: resolving the initial information problem does not necessarily resolve the downstream consequence of an automated decision.

---

## 7. Global precedent registry and policy-gap analysis

The knowledge base will connect relevant UAE provisions to carefully verified international examples.

I would target 25–40 manually verified precedent clauses or framework provisions, beginning with a smaller, carefully validated set for the first working demonstration.

### Candidate sources

| Source                                                   | Intended comparative use                                                                                        |
|----------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| EU AI Act                                                | Serious-incident reporting obligations for covered high-risk AI systems.                                        |
| GDPR                                                     | Personal-data breach notification requirements and their applicability thresholds.                              |
| NIS2 Directive                                           | Cybersecurity incident-reporting and staged notification requirements for entities within scope.                |
| Canada's Directive on Automated Decision-Making          | Human involvement, monitoring, contingency measures, and recourse in its applicable federal-government context. |
| NIST AI Risk Management Framework                        | AI risk governance and the Govern, Map, Measure, and Manage functions.                                          |
| Singapore's Model AI Governance Framework for Agentic AI | Risk boundaries, human accountability, lifecycle controls, and multi-agent governance.                          |
| OECD AI incident reporting framework                     | Common incident terminology and interoperable reporting structures.                                             |
| WHO AI-in-health guidance                                | Human rights, accountability, inclusiveness, and responsible deployment of AI in healthcare.                    |

Relevant references include the EU AI Act, GDPR Article 33, Canada's Directive, NIST AI RMF, Singapore's official AI governance framework, and the OECD's AI incident-reporting work.

Every entry must record the issuing authority, jurisdiction, publication date, applicable scope, source passage, legal or normative status, and the precise problem it addresses. An international precedent can inform a gap analysis without becoming binding UAE law.

### UAE knowledge base

The initial collection should prioritize:

- ITU-T Y.3172 and the ITU AI Readiness Framework.
- The UAE National AI Strategy 2031 and relevant AI ethics and government-adoption guidance.
- Federal Law No. 2 of 2019 concerning ICT in health fields and its applicable executive regulation.
- Relevant telecom regulations and institutional mandates under the TDRA framework.
- Applicable health-data, cybersecurity, public-service continuity, and emergency-management requirements.
- The relevant NCEMA business-continuity standards and procedures.
- Carefully selected global precedents tied to the same failure categories.

Two legal implementation details are important.

First, UAE Federal Decree-Law No. 45 of 2021 excludes certain categories, including government data, governmental entities, and personal health data governed by separate legislation. Consequently, the prototype must determine the applicable health-data and institutional regime rather than automatically treating that decree-law as governing every public-health scenario.

Second, ITU-T Y.3172 is specifically an architectural framework for machine learning in future networks, including ML pipelines and their management and orchestration. The project will map the simulated telecom AI pipeline to that framework and investigate whether the relevant cross-organizational evidence-handoff requirements reveal a standards gap. A proposed standards contribution will be made only if a clause-level review supports it.

---

## 8. Evidence and reusable scenario format

The knowledge base will prioritize authoritative English legal texts and official translations.

Each source record will preserve the original clause, document identity, applicable date and jurisdiction, and precise evidence references.

Incident scenarios will use an MSEL-inspired, machine-readable event format. Each event will define its release time, recipients, content, information visibility, expected decision points, potentially relevant obligations, and the outcomes a reviewer should examine.

This makes the scenarios repeatable and suitable for future adaptation to other countries or sectors without assuming their legal regimes are equivalent.

---

## 9. Evaluation plan

The evaluation will compare three system configurations on the same incident scenario and controlled variants.

| Configuration                                | Purpose                                                                                            |
|----------------------------------------------|----------------------------------------------------------------------------------------------------|
| Single policy-grounded assistant             | Establishes a baseline for evidence retrieval and recommendations.                                 |
| Multi-agent system without the repair engine | Tests the value of separate institutional roles and progressive information release.               |
| Full CascadeGuard system                     | Tests the additional contribution of deterministic gap diagnosis, constrained repairs, and replay. |

The variants will contain controlled changes, such as an assigned versus unassigned handoff owner or a present versus absent escalation trigger. Reviewers will establish the expected classifications in advance.

The principal evaluation outputs will be:

- Detection of seeded gaps and the rate of unsupported gap claims.
- Correctness and traceability of policy citations.
- Unresolved critical blockers before and after replay.
- Number of repair edits needed to unblock a feasible recovery path.
- New conflicts introduced by candidate repairs.
- Completion of essential handoffs and the availability of an authorized fallback.
- Coverage of affected user groups in the simulated recovery process.

The hackathon FAQ states that raw AI prototype accuracy is not itself an evaluation criterion, while the main brief emphasizes relevant agent responses, policy and standards gap quality, auditability, and alignment with ITU frameworks. Accordingly, the quantitative measurements should support the central demonstration—not turn the project into an unrelated classifier-accuracy competition.

---

## 10. Implementation toolkit

The initial technical stack should remain compact.

| Tool               | Purpose                                                                                                       |
|--------------------|---------------------------------------------------------------------------------------------------------------|
| ITUAIReadiness     | Start with the repository referenced by the hackathon for knowledge-base development.                         |
| GitHub Spec Kit    | Specify scenario formats, policy records, agent contracts, and acceptance tests before implementation.        |
| Python and DuckDB  | Store structured policies, graph edges, audit records, and replay comparisons in a local analytical database. |
| Graphify           | Support graph-based exploration of relationships between rules, responsibilities, and dependencies.           |
| OpenAPPA           | Evaluate for deterministic guardrails, subject to implementation fit.                                         |
| NiceGUI            | Create the incident timeline, role views, conflict graph, and replay-comparison dashboard.                    |

Use a deterministic graph and constraint-checking layer regardless of which AI orchestration framework is chosen. Fine-tuning is not required for the initial prototype; effort is better spent on evidence quality, realistic information boundaries, reliable replay, and evaluation scenarios.

---

## 11. Expected deliverables

The final submission should contain:

1. A working prototype demonstrating the staged incident, institutional views, gap classification, candidate repairs, and baseline-versus-replay comparison.
2. An evidence-grounded policy knowledge base with documented source provenance, applicable scope, and verified comparisons to global precedents.
3. An open scenario and failure-case dataset with machine-readable event injects, identified coordination failures, proposed interventions, and actual replay results.
4. A technical report of up to five pages, covering the use case, architecture, ITU-T Y.3172 and AI Readiness Framework mapping, applicable UAE policies, evaluation scenarios, and substantiated policy or standards gaps. The submission page lists the technical report, GitHub repository, and knowledge base as required materials.

---

## 12. Project boundaries and success criteria

The initial version will support one healthcare-access disruption scenario and three controlled variants. It will not attempt to build a live telecom network controller, a production healthcare system, a general-purpose legal assistant, or a complete multi-country governance platform.

Its success depends on answering one question convincingly:

> Can CascadeGuard identify a cross-agency failure caused by interacting AI systems, trace the blockage to applicable evidence, and demonstrate that a minimal, safeguard-preserving coordination repair improves the simulated outcome?

If the answer is demonstrated through a reproducible experiment, a carefully grounded knowledge base, and a clear audit trail, the project will have a stronger contribution than a generic multi-agent policy chatbot.

---

**Final pitch:** CascadeGuard discovers how AI failures cascade across institutional boundaries, identifies the policy and coordination gaps that prevent recovery, and tests the smallest permissible repair—producing evidence-backed, repeatable lessons for safer AI-dependent public services.
