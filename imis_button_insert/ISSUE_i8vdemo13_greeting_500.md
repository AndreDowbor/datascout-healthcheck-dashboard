# i8vdemo13 — Concierge greeting fails with HTTP 500 (staging)

Date: 2026-07-22
Environment: staging
Client: `i8vdemo13`

## Symptom

Opening the Concierge chat for `i8vdemo13` (`/i8vdemo13/chat`) loads correctly
(config fetch, widget render, auth all succeed), but the initial greeting
never appears. Browser console shows:

1. `client_config` and `concierge_config` fetch from Supabase — succeeds (200,
   data present, no error).
2. Greeting request to
   `https://workflow.datascout.ai/webhook/staging-portal-concierge-greeting`
   — succeeds (200), returns a `resumeUrl` (n8n's wait-node resume pattern),
   e.g. `https://workflow.datascout.ai/webhook-waiting/555769`.
3. Frontend follows that `resumeUrl` with a `POST` — **fails with HTTP 500**.
   Reproduced twice, on two separate conversation IDs (webhook-waiting IDs
   `555769` and `555787`) — same failure both times.

The frontend has no further detail beyond "resumeUrl returned non-OK status:
500" — the actual error/stack trace would only be visible in n8n's own
execution log for that workflow run, which was not accessible from this
side.

## What was checked and ruled out

- **`concierge_config` row for `i8vdemo13`** (Supabase, staging) — compared
  field-by-field against two known-working clients (`armdemo96`,
  `atsdemo89`). Structurally identical (same shape, same nulls in
  `concierge_title`/`greeting_instruction`). No difference found here.
- **`client_config.config_json.credentials.imis.imis_base_url`** — this
  field had a trailing slash (`https://apdemoaisp13.imiscloud.com/`) where
  the working comparison clients did not
  (`https://demoaisp96.imiscloud.com`). This looked like a strong candidate
  (matches a real bug class fixed elsewhere in this codebase today —
  `common/imis_client.py` had a URL-concatenation bug caused by exactly this
  kind of trailing-slash mismatch). The trailing slash was removed via a
  Supabase `UPDATE`, the chat was retested, and **the same 500 still
  occurred** (same failure point, new webhook-waiting ID `555787`). The
  change was then reverted (trailing slash restored) to keep the data back
  to its original state, since it did not resolve the issue.

## What is NOT yet known

- The actual server-side error from the n8n workflow run — not visible from
  the browser or from Supabase; needs the n8n execution log for the
  `staging-portal-concierge-greeting` workflow, specifically the runs tied
  to webhook-waiting IDs `555769` and `555787`.
- Whether this reproduces for other recently-onboarded clients or is
  specific to `i8vdemo13`'s data.
- Whether the greeting workflow depends on any other per-client data source
  (IMIS API call, Algolia, LLM prompt construction, etc.) that could be
  malformed or missing specifically for `i8vdemo13`. Not checked: whether
  the workflow can successfully reach `i8vdemo13`'s IMIS instance directly,
  or whether the specific contact/member record it may be looking up
  exists and is well-formed.

## Possible causes (unconfirmed — for the dev team to check against the n8n execution log)

- Something inside the greeting workflow's logic errors out on data specific
  to `i8vdemo13` (e.g. a null/missing field the workflow doesn't guard
  against, given `concierge_title` and `greeting_instruction` are null here
  — though the same nulls exist on working clients, so this is a weak lead).
  This is a hypothesis, not a difference confirmed to exist only here.
- An outbound call the workflow makes on `i8vdemo13`'s behalf (IMIS REST
  API, Algolia, or an LLM call) fails or times out for this client
  specifically.
- Some other per-client config field (outside the two tables inspected
  here) that the greeting workflow reads and that hasn't been checked yet.

## Not the cause (tested directly)

- Trailing slash on `imis_base_url` in `client_config` — fixed and reverted,
  had no effect on the 500.
- **Access context (inside vs. outside iMIS)** — tested the chat both from
  within iMIS (embedded button on the Member Home page) and from outside
  iMIS directly. Same HTTP 500 result in both cases. This rules out
  anything specific to the iMIS-embedded session/iframe context (SSO
  session state, cookies, embedding) as the cause — the failure is
  consistent regardless of how the chat is accessed.
