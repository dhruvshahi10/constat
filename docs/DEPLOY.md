# Deploying Constat (about 10 minutes, at a desk)

Written so it can be followed without rereading any conversation. Everything the
repo can decide for itself is already decided; what is left needs a browser and a
card.

## Before you start

You need a GitHub account with this repo, and a card for about **$7/month**.
Render's free tier will not work: it has no persistent disk, so every workspace,
run and audit log would vanish on restart, and it idles the instance out, which
kills the run queue. That is not a preference, it is why `render.yaml` pins
`plan: starter`.

## 1. Create the service

1. Go to render.com, sign up with GitHub.
2. **New** then **Blueprint**. Point it at `dhruvshahi10/constat`.
3. Render reads `render.yaml` and proposes one web service with a 1GB disk at
   `/data`. Accept it. Do not change `numInstances: 1` — the run queue, the
   review lock and SQLite are all single-process by design, and a second instance
   can fork the audit chain.
4. First build takes a while. It downloads the embedding model into the image on
   purpose, so that at runtime no customer text and no model request ever leaves
   the box.

## 2. Add the Gemini key, once

This is the step that has been going in circles, so here is why.

The key is not in this repo and never has been. `.gitignore` excludes `.env`, and
every remote working session clones the repo into a fresh container that is
reclaimed afterwards. A key pasted into a chat or into a session's `.env` is
therefore destroyed shortly after, every time. **Render's environment is the only
place it persists**, and it is also the only place it is not sitting in a
transcript.

1. Get a free key at aistudio.google.com.
2. In Render: your service, **Environment**, **Add Environment Variable**.
3. Key `GEMINI_API_KEY`, value the key. Save. The service restarts.

Without it the app still runs, but every answer comes from the deterministic
offline engine, which abstains on everything, so the demo reads **0 delivered**.
That is correct behaviour and not a bug, but it is a bad first impression.

**What this key does and does not buy.** It drafts on Google's free tier, whose
terms permit Google to use submitted content to improve their services. That is
exactly why every upload surface asks for public evidence, and why the tier table
exists. Do not quietly point it at a paid key and leave the copy unchanged: the
copy is the honest part.

## 3. Check it came up

- `https://<your-service>.onrender.com/healthz` should return
  `{"ok": true}`. If it returns `503` with `"worker": "dead"`, the run worker
  failed to start; check the logs rather than assuming the app is fine.
- Open `/` and run the demo chips. That path needs no backend, so if it works and
  signup does not, the problem is the database or the disk, not the build.
- Sign up, seed the sample pack, run it. About two minutes on a warm instance.

## 4. Then, and only then

Put the URL into `marketing/linkedin.md` (it currently says "Link in comments"
with nothing to link), and re-render the one-pager if you want the URL on it:

```
.venv/bin/python scripts/build_one_pager.py
```

## Things that will bite, in the order they are likely to

- **A run says RUN-TIMEOUT.** The free tier is rate limited to roughly ten
  requests a minute and the engine paces itself to match. Under contention a run
  can exceed its budget and is stopped deliberately rather than allowed to hold
  the queue. Retry; it does not consume quota.
- **The instance restarts mid-run.** In-flight runs are marked errored on boot
  and queued runs are re-queued. Blast radius is one run.
- **Disk fills.** 1GB, 20 documents and 60MB per tenant, run directories pruned
  to the newest five. If it still fills, tenants expire and are hard deleted at
  14 days, or raise `sizeGB` in `render.yaml`.
- **You put a CDN in front of it.** Do not, yet. The per-IP signup limit reads
  the last forwarded hop and assumes exactly one proxy; a CDN makes every visitor
  behind one edge share a single bucket of three.

## Not deployed by this

The static landing page is published separately and needs no server. This runbook
is only for the interactive workspace: signup, upload, runs, and the named review
queue.
