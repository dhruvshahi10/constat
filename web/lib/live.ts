/**
 * The live API adapter: maps the Constat API's response shapes onto the view
 * types the screens use. This is the only file that knows both sides.
 */
import type {
  Api,
  Audience,
  Claim,
  ClaimProposal,
  DegradationState,
  Difficulty,
  EvalRecord,
  FreshnessGroup,
  ItemState,
  Metrics,
  QuestionDetail,
  QuestionItem,
  Questionnaire,
  TrustPreviewEntry,
  Verdict,
} from "./api";

type Json = Record<string, unknown>;
type Requester = <T>(method: string, path: string, body?: unknown) => Promise<T>;

function s(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function n(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function mapVerdict(v: unknown): Verdict | null {
  if (!v || typeof v !== "object" || !("outcome" in (v as Json))) return null;
  const j = v as Json;
  return {
    outcome: j.outcome as Verdict["outcome"],
    difficulty: (s(j.difficulty, "covered") as Difficulty),
    answer: (j.answer as string | null) ?? null,
    claim_id: (j.claim_id as string | null) ?? null,
    claim_version_hash: (j.claim_version_hash as string | null) ?? null,
    route: (j.route as string | null) ?? null,
    flags: Array.isArray(j.flags) ? (j.flags as string[]) : [],
    gaps: Array.isArray(j.gaps) ? (j.gaps as string[]) : [],
    reused: Boolean(j.reused),
  };
}

function mapItem(j: Json): QuestionItem {
  return {
    id: s(j.id),
    questionnaire_id: s(j.questionnaire_id),
    ordinal: n(j.ordinal),
    text: s(j.text) || s(j.raw_text),
    domain: s(j.domain),
    state: s(j.state, "RECEIVED") as ItemState,
    difficulty: (s(j.difficulty) || null) as Difficulty | null,
    verdict: mapVerdict(j.verdict ?? j.verdict_json),
    draft_answer: (j.draft_answer as string | null) ?? null,
    final_answer: (j.final_answer as string | null) ?? null,
    claim_id: (j.claim_id as string | null) ?? null,
    claim_version_hash: (j.claim_version_hash as string | null) ?? null,
    route: (j.route as string | null) ?? null,
    blocks_deal: Boolean(j.blocks_deal),
    value_rank: n(j.value_rank),
    age_days: n(j.age_days),
    customer: s(j.customer),
    deal_id: s(j.deal_id),
    received_at: s(j.received_at) || s(j.created_at),
    updated_at: s(j.updated_at),
  };
}

function mapQuestionnaire(j: Json): Questionnaire {
  const counts = (j.counts as Partial<Record<ItemState, number>>) ?? {};
  return {
    id: s(j.id),
    customer: s(j.customer),
    deal_id: s(j.deal_id),
    audience: s(j.audience, "nda") as Audience,
    filename: s(j.filename),
    received_at: s(j.received_at),
    total: n(j.total),
    counts,
    quarantined: counts.QUARANTINED ?? 0,
  };
}

function lastVerified(j: Json): string {
  const refs = (j.evidence_refs as Json[] | undefined) ?? [];
  const checked = refs.map((r) => s(r.checked_on)).filter(Boolean).sort();
  return checked.length ? checked[checked.length - 1] : s(j.updated_on) || s(j.valid_from);
}

function mapClaim(j: Json): Claim {
  const refs = (j.evidence_refs as Json[] | undefined) ?? [];
  return {
    id: s(j.claim_id),
    statement: s(j.statement),
    scope: s(j.scope),
    owner: s(j.owner),
    owner_email: s(j.owner),
    status: s(j.status, "draft") as Claim["status"],
    audience: s(j.audience, "nda") as Audience,
    exceptions: Array.isArray(j.exceptions) ? (j.exceptions as string[]) : [],
    evidence: refs.map((r) => ({
      kind: s(r.kind, "statement") as Claim["evidence"][number]["kind"],
      ref: s(r.ref),
      checked_on: (r.checked_on as string | null) ?? null,
    })),
    valid_until: s(j.valid_until),
    version_hash: s(j.version_hash),
    last_verified: lastVerified(j),
    approved_answers: Array.isArray(j.approved_answers) ? (j.approved_answers as unknown[]).length : 0,
  };
}

function mapProposal(j: Json): ClaimProposal {
  const claim = (j.claim as Json) ?? {};
  return {
    id: s(j.proposal_id),
    kind: s(j.previous_version_hash) ? "change" : "new",
    claim_id: s(claim.claim_id) || null,
    statement: s(claim.statement),
    previous_statement: null,
    proposed_by: s(j.actor),
    proposed_at: s(j.created_on),
    reason: s(j.reason),
    source_question_id: null,
    status: s(j.status, "pending") as ClaimProposal["status"],
  };
}

function daysLeft(validUntil: string): number {
  const ms = new Date(validUntil).getTime() - Date.now();
  return Math.round(ms / 86_400_000);
}

export function liveApi(request: Requester): Api {
  const items = async (path: string): Promise<QuestionItem[]> => {
    const r = await request<{ items: Json[] }>("GET", path);
    return (r.items ?? []).map(mapItem);
  };
  return {
    listQuestionnaires: async () => {
      const r = await request<{ questionnaires: Json[] }>("GET", "/questionnaires");
      return (r.questionnaires ?? []).map(mapQuestionnaire);
    },
    getQuestionnaire: async (id) => mapQuestionnaire(await request<Json>("GET", `/questionnaires/${id}`)),
    listItems: (id) => items(`/questionnaires/${id}/items`),
    listQuarantine: (id) => items(`/questionnaires/${id}/quarantine`),
    reviewQueue: () => items("/review/queue"),
    getQuestion: async (id): Promise<QuestionDetail> => {
      const r = await request<Json>("GET", `/questions/${id}`);
      const item = mapItem(r.item as Json);
      const claims = ((r.claims as Json[] | undefined) ?? []).map(mapClaim);
      return {
        item,
        verdict: mapVerdict(r.verdict) ?? item.verdict ?? {
          outcome: "HOLD_HUMAN", difficulty: "covered", answer: null, claim_id: null,
          claim_version_hash: null, route: null, flags: [], gaps: [], reused: false,
        },
        draft: s(r.draft),
        last_approved_answer: (r.last_approved_answer as string | null) ?? null,
        last_approved_meta: (r.last_approved_meta as QuestionDetail["last_approved_meta"]) ?? null,
        claims,
      };
    },
    ask: async (text, audience = "nda") => {
      const r = await request<{ verdict: Json }>("POST", "/questions/ask", { question: text, audience });
      return mapVerdict(r.verdict) as Verdict;
    },
    approve: async (id) => mapItem(await request<Json>("POST", `/review/${id}/approve`)),
    edit: async (id, answer) => {
      const r = await request<{ item: Json; proposal: Json | null }>("POST", `/review/${id}/edit`, { answer });
      return { item: mapItem(r.item), proposal: r.proposal ? mapProposal(r.proposal) : null };
    },
    route: async (id, to, deadline) => mapItem(await request<Json>("POST", `/review/${id}/route`, { to, deadline })),
    send: async (id) => mapItem(await request<Json>("POST", `/review/${id}/send`)),
    listClaims: async () => {
      const r = await request<{ claims: Json[] }>("GET", "/claims");
      return (r.claims ?? []).map(mapClaim);
    },
    getClaim: async (id) => mapClaim(await request<Json>("GET", `/claims/${id}`)),
    listProposals: async () => {
      const r = await request<{ proposals: Json[] }>("GET", "/claims/proposals");
      return (r.proposals ?? []).map(mapProposal);
    },
    approveProposal: async (id) => {
      const claim = await request<Json>("POST", `/claims/proposals/${id}/approve`);
      return { ...mapProposal({ proposal_id: id, claim, status: "approved" }), status: "approved" };
    },
    rejectProposal: async (id) => mapProposal(await request<Json>("POST", `/claims/proposals/${id}/reject`, { reason: "" })),
    freshness: async (): Promise<FreshnessGroup[]> => {
      const [fr, claims] = await Promise.all([
        request<{ by_owner: Record<string, { expired: string[]; expiring: string[]; draft: string[] }> }>("GET", "/claims/freshness"),
        request<{ claims: Json[] }>("GET", "/claims"),
      ]);
      const byId = new Map((claims.claims ?? []).map((c) => [s(c.claim_id), c] as const));
      return Object.entries(fr.by_owner ?? {}).map(([owner, buckets]) => ({
        owner,
        owner_email: owner,
        claims: [...buckets.expired, ...buckets.expiring, ...buckets.draft].map((id) => {
          const c = byId.get(id);
          return {
            id,
            statement: s(c?.statement),
            valid_until: s(c?.valid_until),
            days_left: c ? daysLeft(s(c.valid_until)) : 0,
            status: s(c?.status, "verified") as Claim["status"],
          };
        }),
      }));
    },
    degradation: async (): Promise<DegradationState> => {
      const r = await request<Json>("GET", "/degradation");
      return {
        state: s(r.mode, "normal") as DegradationState["state"],
        reviewer: s(r.primary_reviewer),
        reviewer_idle_hours: n(r.idle_hours),
        backup: s(r.backup_reviewer) || null,
        since: (r.entered_at as string | null) ?? null,
        flowing: n(r.flowing_count),
        held: n(r.held_count),
      };
    },
    metrics: async (): Promise<Metrics> => {
      const r = await request<Json>("GET", "/metrics");
      const oldestAll = (r.oldest_open_hard as Record<string, Json>) ?? {};
      const oldest = Object.values(oldestAll).sort((a, b) => n(b.age_days) - n(a.age_days))[0];
      const byClassRaw = (r.by_class as Record<string, Json>) ?? {};
      const byClass = {} as Metrics["by_class"];
      for (const cls of ["reused", "covered", "parameter_missing", "novel", "contractual"] as Difficulty[]) {
        const row = byClassRaw[cls] ?? {};
        byClass[cls] = {
          open: n(row.review) + n(row.held) + n(row.refused) + n(row.approved),
          sent: n(row.sent),
          median_hours: 0,
        };
      }
      const novel = Object.values((r.novel_per_month as Record<string, number>) ?? {}).reduce((a, b) => a + b, 0);
      return {
        oldest_open_hard: oldest
          ? { question_id: s(oldest.item_id), text: s(oldest.question), difficulty: s(oldest.difficulty, "novel") as Difficulty,
              customer: "", age_days: n(oldest.age_days) }
          : null,
        by_class: byClass,
        human_edit_rate: n(r.human_edit_rate),
        follow_ups_per_questionnaire: n(r.follow_ups_per_questionnaire),
        novel_per_month: novel,
        shipped_wrong: n(r.shipped_wrong),
        p95_latency_ms: n(r.p95_draft_latency_ms),
        cost_per_100_usd: n(r.cost_per_100_usd),
        claim_fresh_share: n(r.claim_fresh_share),
      };
    },
    trustPreview: async (): Promise<TrustPreviewEntry[]> => {
      const r = await request<{ entries: Json[] }>("GET", "/trust/preview");
      return (r.entries ?? []).map((e) => ({
        claim_id: s(e.claim_id), statement: s(e.statement),
        evidence: Array.isArray(e.evidence) ? (e.evidence as string[]) : [], last_verified: s(e.last_verified),
      }));
    },
    evalRecords: async (): Promise<EvalRecord[]> => {
      const r = await request<{ records: Json[] }>("GET", "/evals/records");
      return (r.records ?? []).map((e) => {
        const art = (e.artefact_json as Json) ?? {};
        return {
          id: s(e.id), model_id: s(e.model_id), prompt_version: s(e.prompt_version), run_at: s(e.run_at),
          dangerous_failures: n(e.dangerous_failures), weighted_score: n(e.golden_pass_rate),
          holdout_score: n(art.holdout_score), judge: (art.judge as string | null) ?? null, notes: s(art.notes),
        };
      });
    },
  };
}
