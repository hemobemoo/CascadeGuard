# Recorded adviser answers (preset questions)

`cache/` holds the configured chat model's answers to the six preset questions of
`scenarios/uae_health_access/adviser_questions.yaml`, recorded on 2026-11-06 with
`scripts/record_adviser_presets.py --run` (human approval in the chat, gate 4): 6 chat requests,
all succeeded, keyword retrieval (the preset embedding had failed with HTTP 502).

Each file holds the cache key (SHA-256 of the request and the adviser's view), the prompt
version, the model's payload and token usage. Checked before committing: no API key, base URL,
model id or local path.

Result: the engine check (`engine/adviser_check.py`) rejected all six answers, so a replay shows
the deterministic template with the reasons:

| Step | Question | Rejected for |
|---|---|---|
| T+30 | telecom status sharing | gap_wording, status_claim, authority_wording |
| T+60 | who activates the fallback channel | gap_wording, abstention |
| T+45 | reviewing and reversing the lockouts | gap_wording |
| T+45 | notifying health-data oversight | gap_wording |
| T+45 | reporting to the telecom regulator | status_claim |
| T+15 | international frameworks on human oversight | gap_wording, status_claim, authority_wording |

Replay (no call): `uv run cascadeguard ask uae_health_access --at T+60 "Who must activate the
fallback channel?" --cache docs/evaluation/adviser/cache`.
