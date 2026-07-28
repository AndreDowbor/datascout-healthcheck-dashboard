# `profiles.staging.app.datascout.ai` — 500 on `/profile/{id}`

Date: 2026-07-24
Environment: staging

## Symptom

`GET https://profiles.staging.app.datascout.ai/{client_id}/profile/{contact_id}` returns
500. Reproduced across 3 independent runs today against 26 staging/demo
environments.

**Exact error (captured via a `page.on("response")` listener):**

```
Failed to load resource: the server responded with a status of 500 ()
  → https://profiles.staging.app.datascout.ai/{client}/profile/{id}
```

No client-side stack trace — this is a raw 500 from the server, not a JS
exception (0 `pageerror` events across every capture).

**Cascading effect observed (demo42, non-headless run):**

```
[EnvironmentIndicator] Gateway /environment call error: Failed to fetch
Error fetching AI Brief: TypeError: Failed to fetch
  → /api/environment-test, /api/ai-brief aborted (net::ERR_ABORTED)
```

The initial profile call fails, and subsequent calls in the same session
(environment check, AI Brief) abort in cascade.

**Second error, correlated but on a different host (iMIS, not Datascout):**

```
GET https://{client}.imiscloud.com/api/notificationsetresults?... → 500
```

Shows up alongside the main error in roughly 60% of cases, but not always —
could be dependent or coincidental.

## Reproduction across 3 runs, per environment

- **10 environments hit the 500 consistently** on every run they were tested
  in: `demo42` (confirmed across 4 separate executions), `isgdemo106`,
  `demo83`, `armdemo96`, `imis36`, `atsdemo89`, `imisdemo11`, `ibcdemo80`,
  `atdemo2`, `bsidemo27`, `demosales33`
- **3 environments never fail**, in any run: `oasw`, `cpanb`, `aboncle` — all
  three use the **production** login flow, not staging
- **2 staging environments pass consistently**: `apimisdemo25`, `i8vdemo13`
- **~7 environments are inconsistent** between runs — sometimes hit the 500,
  sometimes fail earlier (session redirected back to login before the button
  ever loads): `imis87`, `atdemo81`, `ensyncdemo13`, `demosales3`,
  `demosales44`, `atsdemo90`, `isgdemo14`. This second failure mode has no
  captured error signature yet — could be the same issue under load, or
  unrelated noise.

## Ruled out

- Not an auth/login issue on our side — login always succeeds before the
  error appears.
- Not a client-side JS exception — 0 `pageerror` events captured.
- Not 100% of staging — 2 staging clients (`apimisdemo25`, `i8vdemo13`)
  never fail.

## Possibilities (unconfirmed — for the dev team to check)

- Per-client data/record that the `/profile/{id}` endpoint doesn't handle
  (not uniform — some staging clients pass, others don't)
- A downstream dependency of the profiles service degraded/down in staging
  (Supabase, gateway, cache)
- Correlation with another 500 found this week on `workflow.datascout.ai`
  and `gateway.staging.app.datascout.ai` (concierge chat) — same staging
  infra, could be a shared root cause or coincidence
- The inconsistent group (session drops) might indicate rate-limiting or
  timeouts under load, since all 26 were run back-to-back in sequence

## Not yet checked

Server-side execution/error logs for `profiles.staging.app.datascout.ai` —
we only have client-side visibility so far.
