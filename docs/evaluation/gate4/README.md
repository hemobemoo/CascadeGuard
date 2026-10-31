# Gate 4 recording: governed LLM baseline and ungoverned variant (2026-10-31)

Hypothetical scenario with synthetic data only. These are recorded results, not conclusions:
any statement comparing governed and ungoverned agents in the README or demo text goes through
human gate 7 first. Governance off is a comparison mode, never the result.

**Runs** (approved by the human, gate 4, 2026-10-31). The model is the one used for the v3
baseline (set in `.env`, `CASCADEGUARD_OUTPUT_MODE=json_object`; the id is not printed or
exported). The model was prompted with `--kb-context` (vector knowledge-base chunks, context only;
not citable).

1. Governed baseline: `cascadeguard run uae_health_access --agents llm --kb-context --cap 54`
   (code at 02a7a16). Dry run before: 36 of 36 steps uncached.
2. Ungoverned variant: `cascadeguard run uae_health_access --governance off --agents llm
   --kb-context --cap 6` (code at 4e1a642). Dry run before, on the cache filled by run 1:
   4 of 72 steps uncached (the health service operator at T+30, T+45, T+60, T+75), so cap
   4 + 50% = 6. The runner stopped a run on a fourth failed request (human rule); it did not
   trigger.

Method: the ungoverned variant reused the 32 governed steps whose agent view did not change,
and only the 4 health service operator steps (T+30 to T+75) were sent live.

## Files

| File | What |
|---|---|
| `llm_cache/` | The 40 decision-cache entries both runs used (36 baseline, 4 variant). Checked for the `.env` key, base URL and model id, key-shaped strings, auth headers and local paths: none. |
| `baseline.json`, `baseline.md` | Run 1 export (`--export`). |
| `governance-off.json`, `governance-off.md` | Run 2 export: the comparison plus both full runs. |
| `baseline.log`, `variant.log` | Console output of each run, with the runner's request, embedding and time line. |

Replay without any API call (72 of 72 steps from the cache; output identical except the agents
label, live vs offline):

```bash
uv run cascadeguard run uae_health_access --governance off --agents llm --offline --kb-context --cache docs/evaluation/gate4/llm_cache
```

`CASCADEGUARD_MODEL` must name the same model: it is part of the cache key.

## Results

| | Governed baseline | Ungoverned variant |
|---|---|---|
| Requests sent (cap) | 37 (54) | 4 (6) |
| Failed requests by kind | 1, retried and recovered; kind not recorded by that code (the human accepted the run as complete and not rate-limited; a 429 cannot be ruled out) | none |
| Query embeddings sent | 37 | 4 |
| Steps decided | 36 of 36 | 36 of 36 (32 reused from the baseline, 4 live) |
| Time taken | 235 s | 45 s |
| Tokens, cost | 120.5k prompt / 11.9k completion, 0 | 15.3k prompt / 2.6k completion (the 4 live steps), 0 |
| Actions proposed | 64: 56 accepted, 8 rejected | 60: 57 accepted, 3 rejected |
| Rejection reasons | 5 `authority_uncertain` (all `activate_fallback_channel`), 3 `outside_recipient_boundary` | 3 `outside_recipient_boundary` |
| Applied only because governance was off | — | 3 `activate_fallback_channel` (T+15, T+60, T+75), each `authority_uncertain`, clause `dha.pp11.4-18-1` [reviewed (interpreted) · binding unknown] |
| Rejected decisions | 1 `citation_out_of_scope` (telecom_operator at T+75 citing `uae.fl2-2019.art4` [reviewed (interpreted) · binding · English translation]) | the same one (that step was reused from the baseline) |
| Goals | `network_incident_reported` met at T+0 (via the illustrative clause `illus.telecom.incident-report`); `patient_access_restored` and `alert_cause_known_to_health` unmet | `network_incident_reported` met at T+0; `patient_access_restored` met at T+15; `alert_cause_known_to_health` unmet |
| Diagnosed failures | information deadlock (network status to the health operator); orphan duties `activate_fallback_channel` and `reverse_automated_lockouts`; undefined trigger `review_automated_lockouts` | the information deadlock; the other three listed as "goal met but the cause is still present" |

Every diagnosed failure keeps its qualification: not a confirmed legal or standards gap; it needs
expert review. For `orphan_duty:activate_fallback_channel` only uncertain authority was found
(`dha.pp11.4-18-1`, binding unknown; it requires a determination); for the other three nothing
was found in the loaded clause set.

**Actions whose verdict changed** (all the health service operator's; its view differed from
T+30 on, since its T+15 action was applied in the ungoverned run):

- T+15 `activate_fallback_channel`: rejected -> accepted (waived `authority_uncertain`).
- Governed only (not proposed ungoverned): T+30 `activate_fallback_channel` (rejected) and
  `review_automated_lockouts` (accepted); T+45 `activate_fallback_channel` (rejected); T+60
  `activate_fallback_channel` to public_access_inclusion (rejected) and `share_incident_status`
  to public_access_inclusion (accepted); T+75 `activate_fallback_channel` (rejected) and
  `request_information` to telecom_operator (accepted).
- Ungoverned only (not proposed governed): T+60 `activate_fallback_channel` and
  `maintain_fallback_plan` (accepted); T+75 `activate_fallback_channel`,
  `maintain_fallback_plan`, `notify_health_data_oversight` and `review_automated_lockouts`
  (accepted).
- At T+75 the governed run proposed `maintain_fallback_plan`, `notify_health_data_oversight` and
  `review_automated_lockouts` with a target and the ungoverned run without one; the comparison
  keys on the target, so it lists them as different actions.

The full list is `changed_actions` in `governance-off.json`.
