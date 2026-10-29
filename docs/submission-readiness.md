# Submission readiness audit (AI for Good Sandbox Hackathon, UAE)

Audit of 2026-10-29. **Deadline: 10 November 2026.** Scope: the repository with the gate-1 PR #12
and the qualifier-label change (branch `clause-qualifier-labels`) on top of `main` (`phase-6d`). No code was changed for this audit and no LLM call was made.

Sources for the requirements:
- The event page, https://aiforgood.itu.int/event/ai-for-good-sandbox-hackathon-united-arab-emirates/,
  read on 2026-10-29 (requirements 1–6, roles, evaluation criteria, FAQ report sections a–h).
- The human's notes from the mentoring sessions (listed in the request).
- The reference code, https://github.com/CrashingGuru/ITUAIReadiness (READMEs and file lists
  only; its Python source was not read).
- ITU-T Y.3172 and the ITU AI Readiness Report 2.0, both read from `policies/extracted/`.

Status key: **covered** · **partial** · **missing**. "Not checked" means nothing in this session
showed it.

> **Note on submission method.** The event page lists what to submit (a technical report of at
> most 5 pages on the official template, the GitHub repository, the knowledge base, and an
> optional demo video) but does not state how to submit. The human's instruction is to email
> the repository link, so everything must be in the repository.

## Ranked gaps (by effect on scoring, then effort)

| Rank | Gap | Criteria / requirements hit | Effect | Effort | Smallest change |
|---|---|---|---|---|---|
| 1 | **Knowledge base is not vectorized and does not use the ITU reference code** | KB quality; Req. 3; mentoring "RAG or graph DB, chunked, vectorized, cited by exact text" | High | Medium (+ dependency gate 3) | §1: chunk the corpus with provenance, embed it once, and serve vector retrieval on the LLM context path only |
| 2 | **No technical report** (a–h) and no Y.3172 or readiness mapping in prose | Alignment criterion; submission item 1 | High | Medium (writing) | §9: a 5-page report on the official template, from the drafts in §7–§8 |
| 3 | **Non-official sources** behind one reviewed clause and two drafts, and news pages searched as context | Req. 2; mentoring "official documents; no news or press releases" | High | Low–medium (human downloads) | §2: add the official CSC 2025 strategy and Charter PDFs, and keep news pages out of the search |
| 4 | **Gap analysis with global examples** is not one open table | Gap-identification criterion (page: "critical part of the evaluation") | High | Low | §6: one generated table, failure → UAE clause evidence → global example clause, each with its qualification |
| 5 | **Governed vs ungoverned comparison** is missing | Bonus (mentoring) | Medium | Medium | §3: an engine-owned `--governance off` run beside the governed one |
| 6 | **Reasoning traces and audit logs are not in the repository** (`data/` is gitignored) | Auditability; Req. 6 | Medium | Low | §4: commit one exported scripted run and one cached LLM run with rationales and citations |
| 7 | **Policy adviser cannot be queried** by a participant during the scenario | Req. 4 roles ("an agent that participants can query") | Medium | Medium (LLM cost, gate 4) | §5: "ask the adviser at T+n" using that step's boundary view |
| 8 | **No licence, no team contacts, no submission section in the README** | Openness; submission | Low (but required) | Low | §9: add a LICENSE (human's choice), the contacts, and a README "Submission" section |
| 9 | **No fine-tuning** with Sandbox cloud credits | Req. 4 | Low | High | §4: state that it was not done, and why (determinism, scripted baseline) |

---

## 1. Knowledge base — **partial**

**What we have**
- **Clause store:** `policies/reviewed/*.yaml` holds 42 clauses: 18 reviewed, 2 illustrative
  and 22 draft.
  - Each clause quotes the text verbatim, with `source_file`, `page`, `article`, `issuer`,
    `jurisdiction`, `document_date`, `status` and `binding`.
  - Some also carry a machine-checked `normalized` reading.
  - The loader checks every quote against the extracted page text
    (`src/cascadeguard/knowledge/loader.py`, `quote_found_on_page`; tested in
    `tests/unit/test_clause_loader.py`).
  - Approvals are pinned by digest in `policies/approvals.yaml`.
- **Retrieval for agents:** `clauses_for_role` (`src/cascadeguard/knowledge/retrieval.py`) gives
  each role exactly the loaded clauses it may cite. It uses the engine's scope rule
  (`RuleBook.concerns`), which is structured, rule-based retrieval with no similarity search.
- **Extracted text:** `policies/extracted/*.jsonl` holds 30 files. These are the 20 committed
  originals, 7 web transcriptions, 1 OCR copy and the 2 gitignored books. Each file is
  page-level text from `scripts/extract_pdf_text.py`.
- **`--extracted-context` (LLM only):** `search_extracted` scores pages by **keyword counts** and
  returns 400-character snippets labelled "context only; not citable". The books and the
  TRA-era strategy are excluded.
- **Graph:** `src/cascadeguard/engine/graph.py` (NetworkX) is the incident's causal and
  failure graph, built per run. It is not a knowledge graph of the corpus.
- **Store:** DuckDB holds audit records (`src/cascadeguard/storage/audit.py`), not the corpus.

**Against the organizers' sense**
- **RAG:** partly. Agents do consume the clause store: clause text, status label and engine
  reading are put into each LLM prompt (`src/cascadeguard/agents/llm.py:255-272`). But
  retrieval is rule-scoped (clauses) or keyword-scored (snippets).
- **Graph database:** no. The graph is the incident, not the regulations.
- **Vectorized:** no. There are no chunks and no embeddings.
- **ITU reference code:** not used. It seeds ChromaDB, embeds with `nomic-embed-text` via
  Ollama, and keeps the collections `kb_main`, `kb_framework`, `kb_usecase` and `kb_decisions`.
  It also maps use cases to the Y.3172 nodes SRC → C → PP → M → P → D → SINK. MIT licence.
- **"Cited by exact text":** covered for clauses (verbatim, page-checked, `[...]` gaps
  explained). Snippets are explicitly not citable.

**Smallest change that keeps determinism and the goldens**
1. **Chunk:** split each committed original into chunks of about one paragraph, with
   `source_file`, `page`, character span and the verbatim chunk text. Map each reviewed clause
   to the chunk that contains its quote. This is a pure function of the committed `.jsonl`,
   kept as a new generated file under `policies/extracted/` and tested to be byte-identical on
   re-run.
2. **Embed once, offline:** embed the chunks with the same embedding model the reference code
   uses (`nomic-embed-text`) and commit the vectors next to the chunks.
   - Vector search then needs no model at query time beyond embedding the query, and the
     stored corpus side is fixed.
   - Store and search in DuckDB, which is already an approved dependency. Its array or
     cosine-similarity functions need no new package (not checked yet).
   - Producing the embeddings needs either Ollama or an embedding library. Neither is on the
     AGENTS.md list, so this is **gate 3** for the human.
3. **Use it only where retrieval is already allowed:** replace the keyword scorer behind
   `--extracted-context`, an LLM-only path whose fingerprint is already in the prompt version,
   with vector top-k over the chunks.
   - Keep each snippet's label.
   - Return the chunk's `source_file`, page and span so it can be cited by exact text.
   - The engine still accepts citations only of reviewed clause IDs.
   - The default scripted path, both goldens and every cache key without the option stay
     unchanged.
4. **Reference-code compatibility:** export the chunks plus metadata as a JSONL that the ITU
   reference code's ingestion can load into ChromaDB (`kb_main`), so the knowledge base can be
   "hosted in the ITU AI for Good Lab" (requirement 3). Whether its ingester accepts this
   format is **not checked**: its source was not read.

## 2. Sources — **partial**

The mentoring rule is "official published documents; news articles and press releases are not
acceptable".

**Reviewed clauses on a non-official source**

| Clause (reviewed) | Source | Why it is not an official document | Official document exists? |
|---|---|---|---|
| `uae.mohap-smart-health.p7-liability` | `web/01_uae_smart_health_ai_policy.pdf`, a transcription of the uaelegislation.gov.ae policy page | A printed transcription of an official government page, not a published document; label "web transcription" | The page itself is on the official legislation portal (the human checked the sentence against it). Whether the portal offers a PDF of this policy: **not checked** |
| `uae.ai-charter.human-oversight` | `UAE Policy Foundation.pdf` | The inventory (#18) calls it an "unofficial compilation of UAE policy pages"; only its Charter part is attributed, by human decision. Its label now says "unofficial compilation" | The UAE Charter for the Development and Use of AI is published by the UAE AI Office; an official PDF is likely. **Not checked** (no downloads) |

**Drafts on announcement summaries (not loaded)**
- `uae.cyber-strategy-2025.governance-aim` and `uae.cyber-strategy-2025.partnership-aim` come
  from `web/03_uae_national_cybersecurity_strategy.pdf`. That file is a Cabinet news item plus
  the WAM launch report, which counts as a press release.
- Official document: the Cyber Security Council's 2025 National Cybersecurity Strategy PDF. It
  is not in the repository; an earlier attempt to download it failed.
- **Pre-submission item:** the human adds it to `policies/sources/` as an original. The two
  clauses are then re-quoted (draft), reviewed or dropped.

**Other source risks**
- **`--extracted-context`** still searches the 01–05 web transcriptions, including the 03 news
  item, and gives agents labelled snippets from them. To meet the mentoring rule strictly, add
  `web/03_…` (and any other news page) to `NOT_SEARCHED`
  (`src/cascadeguard/knowledge/retrieval.py`). 01, 02, 04 and 05 are government portal pages,
  not news; whether they count as "published documents" is for the human to decide.
- **Illustrative clauses:** `illus.telecom.incident-report` and
  `illus.telecom.regulator-information-request` are synthetic rules, labelled "illustrative".
  They fill the telecom side where no official text was available. They are honest but not
  official. Name them as such in the report.
- **Translations and consolidations:**
  - Federal Law No. 2 of 2019 is an English translation (inventory #17); whether the
    translation is official is **not checked**.
  - The GDPR PDF is the EUR-Lex consolidated text, which states it has no legal effect.
    Acceptable as an international example; noted in the clause.

## 3. Governed vs ungoverned — **missing**

- There is no switch for clause gating. The engine always enforces citations, authority,
  prohibitions and safeguards (`src/cascadeguard/engine/constraints.py`).
- A run with an empty clause set (`uv run cascadeguard run uae_health_access --clauses
  <empty dir>`, tried in this audit) is **not** an ungoverned run. Almost every decision is
  rejected as `draft_citation`, because the scripted decisions cite clauses that are not
  loaded.
- What exists that helps:
  - **Scripted vs LLM:** `docs/evaluation/llm-baseline-review.md` already compares the scripted
    and LLM agents. For example, LLM agents had 18 rejected decisions and 12 citation
    rejections, against 1 and 1 for the scripted agents.
  - **Baseline vs replay:** the comparison shows a repair's effect; in the UI and the CLI, see
    `--repair`.

**Smallest change**
1. **Engine mode:** add an engine-owned governance mode
   (`--governance off`, never the default). Agents' decisions are accepted on role
   permissions and information boundaries alone. Every check the governed engine would apply
   is still evaluated and logged as "would have been rejected: <reason>", so the ungoverned run
   lists exactly what governance prevents. The mode stays deterministic and has its own
   expected output, never a golden.
2. **Side by side:** a "governed vs ungoverned" comparison (CLI Markdown plus a UI panel)
   reusing the baseline-vs-replay comparison layout.
3. **Showing behaviour, not just enforcement:** with scripted agents the decisions are the
   same in both modes, so only the engine's reaction differs. A comparison of *agent
   behaviour* needs LLM agents prompted without the clause list. That is a paid run
   (**gate 4**), and the role instructions say what governance means.

## 4. Participant requirements 1–6

| # | Requirement (page) | Status | Evidence | Smallest change |
|---|---|---|---|---|
| 1 | Innovative AI/agentic solution in a domain (healthcare, telecom, public services) | **covered** | A cross-sector health–telecom incident with six agent roles, failure diagnosis, a closed repair grammar, ranked repairs and identical-incident replay. `uv run cascadeguard run uae_health_access`, `uv run cascadeguard repairs uae_health_access`, `uv run python -m cascadeguard.ui.app` | — |
| 2 | Map to the country's published, open documents (laws, strategies, data protection, mandates, treaties) | **partial** | Reviewed UAE clauses: FL 2/2019 (arts 2, 4, 6, 16), PDPL art 2(2), DHA PP-11, the MOHAP smart-health policy, the AI Charter. The AI 2031 strategy, the AI ethics guide and others are in the corpus but not quoted into clauses. No treaty obligations. Institutional mandates are in `scenarios/uae_health_access/roles.yaml` (synthetic). | §2 sources. Add a requirements→policy mapping table (report section f) generated from the clause store. |
| 3 | ITU reference code to build a vectorized, distributed KB hosted in the ITU Lab | **missing** | §1 | §1 steps 1–4 |
| 4 | Use Sandbox cloud credits to fine-tune models and create agents in the listed roles | **partial** | The roles exist (§5). The LLM agents use OpenRouter (`src/cascadeguard/agents/llm.py`). No fine-tuning and no Sandbox credits used. | State this in the report. Fine-tuning would break the deterministic, cached replay design and is not needed for the evaluation criteria (the page: prototype accuracy is not scored). |
| 5 | Interactive error scenarios with sequenced, chunked events released progressively; incomplete, uneven information received at different times by different agents | **covered** | `scenarios/uae_health_access/scenario.yaml`: six injects (T+00 … T+75) whose facts are released to named recipients. `src/cascadeguard/simulation/boundaries.py` builds a read-only, boundary-filtered `RoleView` per role per inject. Tests include `tests/unit/test_view_model.py::test_role_views_show_only_what_the_role_could_see` and `test_telecom_never_sees_patient_records`. The UI shows each role's view per step. | "Interactive" here means a replayed timeline, not a live participant. If the judges expect live interaction, see §5 (querying the adviser). |
| 6 | Audit logging and chain-of-thought tracing: decisions, reasoning and policy references transparent and reviewable | **partial** | Every decision, rejection, finding, obligation and fact release is in the event log with clause IDs and status labels (CLI timeline, `--export` JSON/Markdown). `--audit` writes an append-only DuckDB file (`src/cascadeguard/storage/audit.py`). LLM rationales and uncertainty are stored in the decision cache and exports. **But:** `data/` is gitignored, so no audit file or LLM trace is in the repository. There is no hidden chain-of-thought capture (only the model's stated rationale). Phoenix tracing (optional) is not implemented: `src/cascadeguard/observability/` is empty. | Commit `docs/evaluation/traces/` containing one scripted-run export and one cached LLM-run export (rationale, citations, uncertainty, engine verdict per step), plus a short "how to read a trace". Call the rationale a "reasoning trace" in the report, not "chain of thought". |

The unnumbered alignment paragraph (Y.3172 and the AI Readiness Framework) is covered in §7–§8.

## 5. Agent roles

| Role (page) | Status | Evidence | Smallest change |
|---|---|---|---|
| Innovative AI solution agent ("uses the knowledge base and demonstrates unique value") | **partial** | No single agent does this; the system's value comes from the engine and repair search (diagnosis → smallest safe repair → replay). | Present the repair ranker plus replay as the solution, with the agents as its inputs. |
| **Policy and legal adviser** ("participants can query during simulated error scenarios"; legislation, mandates, emergency powers, international obligations; gaps and global best practices) | **partial** | `policy_legal_adviser` in `scenarios/uae_health_access/roles.yaml`, as scripted and LLM agents. It sees every clause it may cite with its label, which now includes "not binding · international precedent". Gap claims must cite clauses and carry the fixed qualification. **Not queryable:** it answers only at scenario steps. | A "query the adviser at T+n" panel/CLI. It reuses that step's boundary view and the same `AgentDecision` schema, its answer is audited like any decision, and LLM answers go through the cache (gate 4 for live calls). |
| **Institutional participant** (a specific government actor) | **covered** | `telecom_regulator` and `health_data_oversight`, each with its own mandate, allowed actions and boundary (`roles.yaml`). | — |
| **Multi-agent coordination** (different information, mandates, independent assessments; inter-agent coordination protocols) | **covered** | Six roles. Facts are released per role, and actions are permitted per role. Coordination happens only through engine-mediated actions (`request_information`, `share_incident_status`, `request_determination`, `recommend_measure`), which the engine accepts or rejects (`src/cascadeguard/simulation/orchestrator.py`, `engine/constraints.py`). Diagnosed coordination failures: `information_deadlock`, `orphan_duty` and `undefined_trigger`. | In the report, describe the engine-mediated actions as the coordination protocol. |

## 6. Evaluation criteria

| Criterion (page) | Status | Evidence | Smallest change |
|---|---|---|---|
| **Knowledge base quality**: completeness, accuracy and structure of the national material; retrieval of relevant policy context under query | **partial** | Accuracy and structure are strong: verbatim quotes, page-checked, human-reviewed, provenance and SHA-256 recorded (`docs/policy-inventory.md`, `policies/sources/web/MANIFEST.md`). Completeness is narrow (18 reviewed clauses, scenario-driven). Retrieval is not semantic. | §1. Also list the corpus's 20 originals and 7 web pages with what each covers. |
| **Agent capability**: relevance and accuracy in simulated error scenarios; adherence to laws, mandates and coordination | **partial** | Scripted agents are deterministic and fully tested. The LLM baseline was reviewed step by step (`docs/evaluation/llm-baseline-review.md`, `docs/evaluation/adr-0002-golden-llm-replay.md`): 4 candidate gap claims, all supported, and the engine rejected the over-reaching actions. | Re-run the LLM baseline from the cache with the new labels (gate 4 if live) and update the review. |
| **Gap identification with global examples**: unclear responsibilities, standards, technology and legislative gaps, coordination problems, conflicting objectives; relevance of gaps and accuracy of global examples | **partial** | The engine diagnoses 4 failures: an information deadlock, two orphan duties and an undefined trigger (`expected_baseline.yaml`). Each carries "not a confirmed legal or standards gap". Global examples are reviewed: UNESCO paras 35–36, 38 and 43; OECD 1.4 b) and 1.5 c); GDPR Art 33(1). Drafts include NIST, the EU AI Act, ITU Y.3172 and the OECD incident framework. There is no single table linking them. | Generate `docs/gap-analysis.md` from a run: for each diagnosed failure, give the UAE clause evidence (or "no owner found in the reviewed corpus"), the global example clause with verbatim text, the qualification, and the repair that resolves it in replay. Gate 7 applies to any conclusion wording. |
| **Auditability**: logs, chain-of-thought traces, source attribution | **partial** | §4 row 6. Source attribution is strong: every clause shown with its qualified status label; citations are only to reviewed IDs. | §4 row 6 |
| **Alignment with ITU standards**: Y.3172 pipeline and the AI Readiness Framework in the architecture | **partial** | The architecture fits (§7, §8) but is not documented as a mapping. `itu.y3172.mlfo` and `itu.y3172.req-ml-mng-003` are draft clauses. | §7 and §8 tables, into the report (sections d, e) and `docs/architecture.md`. |

## 7. ITU-T Y.3172 mapping (draft)

Y.3172 (06/2019) defines ML pipeline nodes (clause 7):
- SRC, the data source;
- C, the collector;
- PP, the preprocessor;
- M, the model;
- P, the policy node, with rules that safeguard the underlay network;
- D, the distributor;
- SINK, the target of the ML output.

It also defines:
- the **MLFO**, which manages and orchestrates the pipeline nodes "based on ML Intent";
- the **ML sandbox**, "an isolated domain which allows the hosting of separate ML pipelines to
  train, test and evaluate them before deploying them" (p.21 of the PDF);
- the **ML underlay networks**, real or simulated.

| Y.3172 component | CascadeGuard element | Evidenced in code | Note |
|---|---|---|---|
| ML underlay network (simulated) | The synthetic incident world: the telecom network, the health portal and their two AI systems | Yes: `scenarios/uae_health_access/scenario.yaml`, `src/cascadeguard/simulation/state.py` | Simulated, synthetic only |
| SRC | Scenario injects and their facts (T+00 … T+75) | Yes: `scenario.yaml`, `src/cascadeguard/simulation/loader.py` | |
| C (collector) | Per-inject collection of the facts each role may see | Yes: `src/cascadeguard/simulation/boundaries.py` (`RoleView`) | |
| PP (preprocessor) | Boundary filtering, role-scoped clause retrieval, canonical view | Yes: `boundaries.py`, `knowledge/retrieval.py` (`clauses_for_role`), `agents/cache.py` (`canonical_view`) | |
| M (model) | The role agents (scripted or LLM) returning `AgentDecision` | Yes: `src/cascadeguard/agents/scripted.py`, `agents/llm.py` | LLM at temperature 0, cached |
| P (policy) | The deterministic engine: citation, authority, prohibition and safeguard checks, and the hard filter on repairs | Yes: `src/cascadeguard/engine/constraints.py`, `engine/repair_search.py` | The strongest correspondence: policy gates every output before it reaches the underlay |
| D (distributor) | Applies accepted actions and releases facts to recipients | Yes: `src/cascadeguard/simulation/orchestrator.py`, `state.py` | |
| SINK | Goals, obligations and diagnosed failures, shown in the CLI, UI, exports and audit | Yes: `engine/diagnosis.py`, `ui/`, `storage/export.py`, `storage/audit.py` | |
| MLFO | The deterministic orchestrator (step order, view building, decision application) and the repair search driving replays | Partly: `simulation/orchestrator.py`, `engine/repair_search.py` | There is no ML-intent input. The nearest equivalent is the scenario's critical goals plus the closed repair grammar. |
| ML sandbox | Identical-incident replay with a candidate repair, evaluated before anything is recommended | Yes: `src/cascadeguard/simulation/replay.py`, `engine/repair_search.py` | A repair is tested in replay, never applied to the baseline |
| ML intent | Scenario critical goals (`patient_access_restored`, `alert_cause_known_to_health`) | Partly: `scenario.yaml` goals | Not expressed in the Y.3172 intent format |
| Management subsystem / monitoring | Audit trail and evaluation outputs | Partly: `storage/audit.py`, `docs/evaluation/` | |

Honest limit: Y.3172 is about ML pipelines in future networks. CascadeGuard uses its
*architecture pattern* (pipeline nodes, policy node, sandbox, orchestrator) for an
institutional decision pipeline. It does not deploy ML models into a network. Say so in the
report.

## 8. AI Readiness Report 2.0, Clause 3 (13 dimensions)

Clause 3 ("Structural Approach", pp.19–36 of the PDF) defines 13 dimensions under 6 factors.
The table lists every dimension; only the first five rows can honestly be claimed.

| # | Dimension | Claim? | Evidence | Report wording |
|---|---|---|---|---|
| 10 | **AI & Policies** | **Yes (strong)** | The dimension describes "a virtual sandbox for policy and regulatory interventions with a simulated timeline". It predicts outputs from intended interventions, shows "the gaps between the target and achievement milestones", and gives "actionable recommendations". CascadeGuard has a simulated timeline (T+00 … T+75), closed repair interventions, replay against critical goals, and ranked smallest safe repairs. It also cites "Sandbox/Policy/SINK as per ITU-T Y.3172". | Core claim |
| 7 | **Strategy Alignment** | Yes (partial) | Coordination across distributed entities (telecom, health, regulators). Metrics such as "level of coordination between service providers" and "communication channel availability" correspond to the diagnosed information deadlock and the data-share repair. | Coordination failures and repairs |
| 3 | **Cross-domain correlation analysis** | Yes (partial) | Its metric "integrated workflow including prevention…, detection…, response…, and impact analysis" matches the telecom → health cascade, from detection (T+00) to response (T+75). | Two domains, one integrated incident workflow |
| 9 | **Impacts of Humans in AI Integration** | Yes (partial) | "AI decisions are referred back to domain experts to guarantee the accountability of the decision": human review gates (`approvals.yaml`), human-in-the-loop repair authorization (`requires_authorization`), and the orphan duty to review automated lockouts. | Human accountability |
| 11 | **AI for Inclusion** | Partial | The `public_access_inclusion` role assesses patients' loss of access and recommends measures. The dimension's sub-dimensions (simulations, edge AI, GenAI) only partly fit; "availability of sandbox environments" fits. | Access impact as an inclusion lens |
| 5 | Level of Integration of AI in Workflows | Weak | The scenario contains two AI systems in workflows, but we do not measure integration. | Mention only |
| 8 | Collaboration with AI | Weak | The scripted vs LLM comparison and the human review of AI outputs; no co-creation metrics. | Mention only |
| 6 | Human Interface | No | The demo UI is not an AI-ready human interface in the dimension's sense. | Do not claim |
| 1 | Data/model Marketplace | No | — | — |
| 2 | Generated Content Marketplace | No | — | — |
| 4 | Contextualization and Regional Impact | Weak | A UAE-specific clause corpus; the event page itself asks for domain gaps over country recommendations. | Mention only |
| 12 | Granular Priorities | No | — | — |
| 13 | Digital Infrastructure | No | — | — |

## 9. Technical report (FAQ a–h) and team contacts — **missing**

There is no technical report in the repository. The page requires at most 5 pages on the
official template, linked from the page; the template was not downloaded. Source material per
section:

| Section | Status | Source material in the repository |
|---|---|---|
| a. Introduction of the agentic AI solution | missing | `CascadeGuard.md` (concept), `README.md` |
| b. Use case | missing | `scenarios/uae_health_access/README.md`, `scenario.yaml` |
| c. Requirements of the use case | missing | `CascadeGuard.md`, `specs/001–006d` |
| d. Mapping to ITU-T Y.3172 | missing | §7 of this file |
| e. Mapping to the AI Readiness Report 2.0 | missing | §8 of this file |
| f. Requirements mapped to local policies | missing | `policies/reviewed/*.yaml` (reviewed clauses), `docs/policy-inventory.md`; needs a requirement → clause table |
| g. Evaluation scenario (technical and policy) | partial | `expected_baseline.yaml`, `expected_repairs.yaml`, `docs/evaluation/llm-baseline-review.md`, UI screenshots in `docs/review/phase-6*-…` |
| h. Policy/standards gaps from the mapping | partial | Diagnosed failures with qualifications; candidate findings in clause notes; §6 gap table to build |
| Team contact details | **missing** | Not in the repository. Needed from the human: names, roles, emails, affiliation, the team leader (the page caps teams at 4 and has a women's-team prize), and a mentor if any. |

Also missing for an open, emailed submission:
- a `LICENSE` file (the human's choice; the reference code is MIT);
- a README "Submission" section with the report link, run commands, how to reproduce each
  output step by step, and where the knowledge base, the policy mapping and the gap analysis
  live;
- the optional demo video (7 minutes at most), which the page requires only for shortlisted
  teams.

**Reproducibility (mentoring: "step by step")**
- **Covered** for the default path. With no API key, `uv sync` followed by
  `uv run cascadeguard run uae_health_access` and `uv run cascadeguard repairs uae_health_access`
  gives byte-identical output across processes and hash seeds
  (`tests/integration/test_cli_output.py`).
- The goldens are in `scenarios/uae_health_access/`.
- LLM runs reproduce offline from the decision cache (`--offline`). But the cache is in
  `data/`, which is gitignored, so it is not in the repository.
- The qualifier labels changed every role view. So the local cache no longer matches: an offline
  LLM run is `not_cached` on all 36 steps (phase-auditor, 2026-10-29), and the UI's
  "LLM (cached only)" mode is empty until a new recording run (paid, **gate 4**).
- **Smallest change:** one recorded LLM baseline run after the label change, its cache snapshot
  committed (it holds no secrets; check first), and the exported traces (§4 row 6). Otherwise,
  document that LLM results are illustrative and show only the scripted path.

---

### Not checked in this audit
- The ITU reference code's Python source and ingestion format.
- Whether official PDFs exist for the MOHAP policy and the AI Charter.
- Whether DuckDB's vector functions need an extension.
- The submission template's contents.
- Whether the organizers accept an emailed link (the page states no method).
