# Recorded adviser answers (preset questions)

`cache/` holds the configured chat model's answers to the six preset questions of
`scenarios/uae_health_access/adviser_questions.yaml`, recorded with
`scripts/record_adviser_presets.py --run` (human approval in the chat, gate 4), on keyword
retrieval (the preset embedding had failed with HTTP 502).

Each file holds the cache key (SHA-256 of the request and the adviser's view), the prompt
version, the model's payload and token usage. Checked before committing: no API key, base URL,
model id or local path.

## Current recording: prompt adviser-v2, 2026-11-06

6 chat requests, all succeeded (one per question; no retry). The engine check
(`engine/adviser_check.py`, per-sentence since the human decision of 2026-11-06) accepted the
structure of all six answers, so every replay shows the model's commentary block after the
engine's seven sections, without the withheld sentences:

| Step | Question | Commentary lines shown | Sentences withheld (reasons) |
|---|---|---|---|
| T+30 | telecom status sharing | 8 | 8 (authority_wording 6, gap_wording 3, status_claim 1) |
| T+60 | who activates the fallback channel | 3 | 2 (gap_wording 2) |
| T+45 | reviewing and reversing the lockouts | 4 | 2 (gap_wording 2) |
| T+45 | notifying health-data oversight | 7 | 1 (gap_wording 1) |
| T+45 | reporting to the telecom regulator | 6 | 0 |
| T+15 | international frameworks on human oversight | 11 | 2 (gap_wording 2) |

A sentence can have more than one reason. Most withheld sentences describe what a clause
restricts or "permits" (authority wording) or say that "no listed clause" does something (gap
wording); the withheld text is never shown.

## Earlier recording: prompt adviser-v1, 2026-11-06 (replaced)

6 chat requests. The check then ran on whole answers and rejected all six (a replay showed the
template). Those six answers are kept as test fixtures in `tests/fixtures/adviser_v1_answers/`
(`test_the_six_recorded_v1_answers`): under the per-sentence check, five would now be shown with
1 to 9 sentences withheld; the sixth (T+60) abstains while citing a clause, so its structure
still fails.

Replay (no call): `uv run cascadeguard ask uae_health_access --at T+60 "Who must activate the
fallback channel?" --cache docs/evaluation/adviser/cache` (the key includes the model id, so the
same `CASCADEGUARD_MODEL` must be in `.env`).
