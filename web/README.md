# Constat web

The product surface for Constat: an evidence-gated security questionnaire engine where every answer rests on an owned, expiring, exception-carrying claim, or it is refused and routed to the person who can fix it.

Next.js 15 (App Router), TypeScript, Tailwind v4, shadcn/ui, TanStack Table, `diff` for word diffs, `@xyflow/react` for the provenance chain.

## Run it

```bash
npm install
npm run dev
```

Open http://localhost:3000. With no API configured every screen renders from the mock tenant in `lib/mock.ts` (Northwind Data, three questionnaires, nine claims).

### Against the live API

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

`lib/api.ts` is the only place that knows about HTTP. It calls `/v1/...` on that base, sends the handshake JWT as a bearer token when embedded, and throws `ApiRequestError` with the API's `{error, code}` on non-2xx. Routes it expects, from the plan's contract: questionnaires, questionnaire items and quarantine, `GET /questions/{id}`, `POST /questions/ask`, `POST /review/{item}/approve|edit|route|send`, claims, proposals, freshness, degradation, metrics, trust preview, eval records. One route is not in the contract table and is assumed here: `GET /v1/review/queue` returning the ranked `QuestionItem[]` (rank is `value_rank*3 + blocks_deal*5 + age_days`). If the API exposes the queue elsewhere, change the one line in `lib/api.ts`.

## Themes

One component set, two themes selected by `data-theme` on `<html>`:

- `constat` (default): dark; the ink, bone and signal hex values copied from `constat/brand.py`, with Newsreader, Archivo and Fragment Mono loaded through `next/font/local` from `app/fonts/` (synced from `constat/assets/fonts` by `npm run sync-fonts`).
- `native`: light; Atlan's published neutral scale, primary blue, cyan only for focus rings and indicators, system type.

Pick with `?theme=native` on any URL, the toggle in the top bar, or the `atlan:theme` message when embedded. The choice persists in localStorage; a `?theme=` in the URL always wins. Both themes pass WCAG AA for body text (muted text is the brand's `--bone-2` on dark and Atlan neutral 500 on white).

## Embedding inside Atlan

- `/embed/<view>[/<id>]` renders any screen without chrome: `inbox`, `review`, `review/<id>`, `claims`, `claims/<id>`, `claims/proposals`, `claims/freshness`, `provenance`, `questions/<id>/provenance`, `metrics`, `trust`, `evals`.
- `lib/atlan/handshake.ts` implements the host protocol. Messages from an origin not in the allowlist are ignored before they are parsed; every `postMessage` names an explicit target origin; the JWT lives in memory only. Allowed origins are the page's own origin, `https://*.atlan.com`, and anything in `NEXT_PUBLIC_ATLAN_ORIGINS` (space or comma separated). Unit tests in `tests/unit/handshake.test.ts`.
- `next.config.ts` sends `Content-Security-Policy: frame-ancestors 'self' https://*.atlan.com <NEXT_PUBLIC_ATLAN_ORIGINS>` on `/embed/*` and `frame-ancestors 'none'` plus `X-Frame-Options: DENY` everywhere else.
- `/dev/atlan-shell` is the shell simulator: it iframes `/embed/review`, signs a dev HS256 JWT through `/api/dev/token` (secret `CONSTAT_DEV_JWT_SECRET`, default `constat-dev-secret`, the API accepts it only when `CONSTAT_ENV=dev`), posts `atlan:init` with a fake user and page context, toggles the theme, and logs the messages. It exists in development, or in a production build when `NEXT_PUBLIC_DEV_SHELL=1`.

## Checks

```bash
npm run lint        # eslint, then the copy gate (no em or en dashes under app/ and components/)
npm run typecheck
npm run test        # vitest: handshake origin rules
npm run build
npm run test:e2e    # Playwright smoke: /review and /review/[id] at 1440 and 390 wide, zero console errors, themes, palette, handshake, CSP
npm run screenshots # every screen in both themes into screenshots/<theme>/
```

Playwright builds and starts the app on port 3100 by itself. First run: `npx playwright install chromium`.

## Keyboard

Review queue and question page: `j` / `k` move, `Enter` opens, `a` approves, `e` edits, `r` routes. `cmd K` (or `ctrl K`) opens the palette; type a question and press Enter for a dry-run verdict that answers or refuses without touching the queue.

## Notes

- Copy rule: no em dashes or en dashes anywhere in rendered copy; `scripts/copy-gate.mjs` fails the lint on any.
- 21st.dev was searched for MIT stat tiles (konsstepnov, redrob-labs). They ship only through an API-key install, so the tile is composed from shadcn Card in `components/stat-tile.tsx`.
- The repository root `.gitignore` ignores `public/`, which also hides `web/public`. Nothing in `web/public` is needed today, so this only matters once a static asset is added there.
