# Golden repair, LLM replay (prompt phase5-v4): why the lockouts were not reversed

Repair: `owner.reverse_automated_lockouts.health_service_operator.30m` +
`share.network_incident_status.telecom_operator.health_service_operator`. Free model,
`json_object` mode, run once on 2026-10-26 (28 requests, cost 0). This diagnosis uses the
decision cache and the engine log only: no LLM call and no prompt change.

## Finding

**Model behaviour, not mechanical.** The repair resolves the scripted replay. On the free LLM,
the owner obligation was in the agent's view with its deadline, but the agent did not act
within it: it never proposed `reverse_automated_lockouts`, and its statements do not mention the
obligation or the owner rule. The engine recorded `obligation_overdue` at T+60, and
`orphan_duty:reverse_automated_lockouts` stays a remaining blocker (outcome: partial).

The human's suggested wording was "the agent acknowledged the obligation but did not act within
its deadline". The stored statements do not acknowledge it in words, so the finding above says
"was in the agent's view" instead.

## Checks (health_service_operator at T+30, T+45, T+60)

1. **Allowed action:** `reverse_automated_lockouts` is in `allowed_actions` in all three views.
2. **Preconditions:** it requires authority, `network_incident_status` and a prior accepted
   `review_automated_lockouts`. The operator held `network_incident_status` from T+30, and its
   review had been accepted at T+15 (and again at T+30, T+45, T+60). Authority comes from the
   owner rule. Counterfactual from the cache (no call): adding the reversal to the agent's own
   T+30 decision makes the engine **accept** it (clause
   `repair.owner.reverse_automated_lockouts.health_service_operator.30m`) and fulfil the
   obligation at T+30. Nothing in the engine, view or preconditions blocked it.
3. **Owner rule and obligation in view:** in all three views, the rule is in `role_clauses`
   labelled "hypothetical repair rule (not a source clause; not citable)", and
   `open_obligations` lists `reverse_automated_lockouts`, source labelled "hypothetical repair
   rule (not a source clause)", opened T+30, due T+60, status open.
4. **What it said** (stored agent statements, labelled as the engine stores them):
   - T+30: "agent statement (unverified; not a finding or a legal conclusion): ... I will
     maintain the fallback channel so patients can keep accessing care despite OTP SMS
     degradation, continue human review of the automated lockouts per the AI oversight
     principle, and request network_incident_status from the telecom operator to understand the
     OTP delivery failure. ..."
   - T+45: "agent statement (unverified; not a finding or a legal conclusion): The fraud-model
     alert is suspected, not proven, and no successful unauthorised login has been confirmed. I
     will review the automated lockouts under human oversight, notify health-data oversight of
     the suspected incident within the reporting period, and maintain the fallback plan ..."
   - T+60: "agent statement (unverified; not a finding or a legal conclusion): ... The
     fraud-model alert is suspected, not proven, and no successful unauthorised login has been
     confirmed, so automated lockouts should be reviewed before reversal. ... I do not know
     whether the lockouts are erroneous, whether SMS degradation is confirmed as network-side,
     or whether a fallback channel can be activated on the operator's own authority."

At T+30 it asked the telecom operator for `network_incident_status`, although it already held
that status in its view. At T+60 it still wrote "reviewed before reversal", although its own
review had been accepted three times. It treated the suspected alert as reason to keep
reviewing, not to reverse.

## Not changed

The prompt is not changed to force the action (human decision). An LLM replay understates a
repair that only works if an agent takes up a new duty; the engine now reports that explicitly
(`obligation_overdue`, remaining blocker) instead of leaving it implicit.
