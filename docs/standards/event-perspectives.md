# The event's eight perspectives: status in CascadeGuard

The event page ([AI for Good Lab Hackathon: United Arab Emirates](https://aiforgood.itu.int/event/ai-for-good-sandbox-hackathon-united-arab-emirates/),
read 2026-11-06) asks for solutions aligned with ITU-T Y.3172 and reflecting the ITU AI Readiness
Framework "from (including but not limited to)" eight perspectives. The perspective names below
are the page's; the status is our own assessment, kept honest: **addressed** (a core part of the
prototype, with evidence), **partial** (some evidence, not a focus), **not addressed**. Synthetic
data; hypothetical scenario. No compliance with Y.3172 or the Readiness Framework is claimed
(see [y3172-mapping.md](y3172-mapping.md) and [ai-readiness-2.0.md](ai-readiness-2.0.md)).

| # | Perspective (event page) | Status | What CascadeGuard does | Where |
|---|---|---|---|---|
| 1 | Open data and open-source management | partial | MIT-licensed code; the knowledge base is exported in the ITU reference layout; every source has a SHA-256, and an official link where one was located. The scenario data are synthetic; no open dataset is published, and three CSC PDFs are not redistributed (reproduction needs consent). | `LICENSE`, `policies/kb/`, `docs/policy-inventory.md`, `docs/corpus-counts.md` |
| 2 | Generative AI content ecosystem | not addressed | LLMs are used as role agents and for the adviser's labelled commentary, not to build or govern a generated-content ecosystem. | `src/cascadeguard/agents/llm.py`, `src/cascadeguard/agents/adviser_query.py` |
| 3 | Contextualization of AI solutions and regional development focus | partial | A UAE clause corpus (federal and Dubai texts, UAE Cyber Security Council gap examples) with status labels; one UAE-set scenario. Not a regional development analysis. | `policies/reviewed/`, `policies/gap_examples_only/`, `scenarios/uae_health_access/scenario.yaml` |
| 4 | AI integration in domains and cross-domain analysis | addressed | A telecom AI fault cascades into a health portal's AI lockouts; the engine diagnoses the cross-domain coordination failures and tests repairs by replay. | `scenarios/uae_health_access/scenario.yaml`, `src/cascadeguard/engine/diagnosis.py`, `docs/gap-analysis.md` |
| 5 | Human interaction and supervision in AI | addressed | Human gates on every reviewed clause and conclusion; the orphan duty to review automated lockouts; the adviser has no enforcement authority; repairs needing authority are marked for human and institutional approval. | `policies/approvals.yaml`, `docs/institutional-mandate-crosswalk.md`, `src/cascadeguard/ui/app.py` |
| 6 | AI policy and implementation opportunity identification | addressed | Candidate gaps for expert review with global and UAE examples, and the smallest safe repair, tested in replay, for each. | `docs/gap-analysis.md`, `src/cascadeguard/engine/repair_search.py`, `docs/report/cascadeguard-report.md` |
| 7 | AI for social inclusion | partial | A `public_access_inclusion` role assesses which patients lose access (synthetic figures include users over 65) and recommends measures. | `scenarios/uae_health_access/roles.yaml`, `scenarios/uae_health_access/scenario.yaml` |
| 8 | Digital infrastructure and energy considerations | not addressed | The telecom network appears only as the simulated infrastructure where the incident starts; energy is not modelled. | `scenarios/uae_health_access/scenario.yaml` |
