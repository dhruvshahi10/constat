/**
 * Typed client for the Constat API (api/, all routes under /v1).
 *
 * Types mirror the plan's API contract. With NEXT_PUBLIC_API_BASE unset the
 * client answers from lib/mock.ts so every screen renders without a server;
 * set it (for example http://localhost:8000) to talk to the live FastAPI.
 */

export type Outcome = "ANSWER" | "HOLD_HUMAN" | "REFUSE";

export type Difficulty =
  | "reused"
  | "covered"
  | "parameter_missing"
  | "novel"
  | "contractual";

export const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  reused: "Reused",
  covered: "Covered",
  parameter_missing: "Parameter missing",
  novel: "Novel",
  contractual: "Contractual",
};

export type ItemState =
  | "RECEIVED"
  | "NORMALISED"
  | "MATCHED"
  | "DRAFTED"
  | "REVIEW"
  | "APPROVED"
  | "SENT"
  | "HELD"
  | "REFUSED"
  | "QUARANTINED";

export const ITEM_STATES: readonly ItemState[] = [
  "RECEIVED",
  "NORMALISED",
  "MATCHED",
  "DRAFTED",
  "REVIEW",
  "APPROVED",
  "SENT",
  "HELD",
  "REFUSED",
  "QUARANTINED",
] as const;

/** Main line of the state machine; side states are HELD, REFUSED, QUARANTINED. */
export const MAIN_LINE_STATES: readonly ItemState[] = [
  "RECEIVED",
  "NORMALISED",
  "MATCHED",
  "DRAFTED",
  "REVIEW",
  "APPROVED",
  "SENT",
] as const;

export type Audience = "public" | "nda" | "internal";

export type ClaimStatus = "draft" | "verified" | "deprecated";

export type EvidenceKind =
  | "vanta_test"
  | "policy"
  | "standard"
  | "report"
  | "certificate"
  | "attestation"
  | "config"
  | "statement";

export interface EvidenceRef {
  kind: EvidenceKind;
  ref: string;
  checked_on: string | null; // ISO date
}

export interface Verdict {
  outcome: Outcome;
  difficulty: Difficulty;
  answer: string | null;
  claim_id: string | null;
  claim_version_hash: string | null;
  route: string | null; // owner email or team the question goes to
  flags: string[]; // gate flags, e.g. EXCEPTION_DROPPED, NEW_VALUE_INTRODUCED
  gaps: string[]; // plain sentences describing what is missing
  reused: boolean;
}

export interface QuestionItem {
  id: string;
  questionnaire_id: string;
  ordinal: number;
  text: string;
  domain: string;
  state: ItemState;
  difficulty: Difficulty | null;
  verdict: Verdict | null;
  draft_answer: string | null;
  final_answer: string | null;
  claim_id: string | null;
  claim_version_hash: string | null;
  route: string | null;
  blocks_deal: boolean;
  value_rank: number; // 1 (small) to 5 (strategic)
  age_days: number;
  customer: string;
  deal_id: string;
  received_at: string;
  updated_at: string;
}

export interface Questionnaire {
  id: string;
  customer: string;
  deal_id: string;
  audience: Audience;
  filename: string;
  received_at: string;
  total: number;
  counts: Partial<Record<ItemState, number>>;
  quarantined: number;
}

export interface Claim {
  id: string;
  statement: string;
  scope: string;
  owner: string;
  owner_email: string;
  status: ClaimStatus;
  audience: Audience;
  exceptions: string[];
  evidence: EvidenceRef[];
  valid_until: string; // ISO date
  version_hash: string;
  last_verified: string; // ISO date
  approved_answers: number;
}

export interface ClaimProposal {
  id: string;
  kind: "new" | "change";
  claim_id: string | null;
  statement: string;
  previous_statement: string | null;
  proposed_by: string;
  proposed_at: string;
  reason: string;
  source_question_id: string | null;
  status: "pending" | "approved" | "rejected";
}

export interface FreshnessClaim {
  id: string;
  statement: string;
  valid_until: string;
  days_left: number; // negative when expired
  status: ClaimStatus;
}

export interface FreshnessGroup {
  owner: string;
  owner_email: string;
  claims: FreshnessClaim[];
}

export interface QuestionDetail {
  item: QuestionItem;
  verdict: Verdict;
  draft: string;
  last_approved_answer: string | null;
  last_approved_meta: { customer: string; sent_on: string } | null;
  claims: Claim[];
}

export interface DegradationState {
  state: "normal" | "degraded";
  reviewer: string;
  reviewer_idle_hours: number;
  backup: string | null;
  since: string | null;
  flowing: number; // approved-and-unchanged answers continuing
  held: number; // novel or changed answers held
}

export interface Metrics {
  oldest_open_hard: {
    question_id: string;
    text: string;
    difficulty: Difficulty;
    customer: string;
    age_days: number;
  } | null;
  by_class: Record<Difficulty, { open: number; sent: number; median_hours: number }>;
  human_edit_rate: number;
  follow_ups_per_questionnaire: number;
  novel_per_month: number;
  shipped_wrong: number;
  p95_latency_ms: number;
  cost_per_100_usd: number;
  claim_fresh_share: number;
}

export interface EvalRecord {
  id: string;
  model_id: string;
  prompt_version: string;
  run_at: string;
  dangerous_failures: number;
  weighted_score: number;
  holdout_score: number;
  judge: string | null;
  notes: string;
}

export interface TrustPreviewEntry {
  claim_id: string;
  statement: string;
  evidence: string[];
  last_verified: string;
}

/** One answered row from a completed questionnaire being imported. */
export interface ImportRow {
  ordinal: number;
  question: string;
  answer: string;
  domain: string;
  /** Rows that say the same thing share a cluster; one claim per cluster. */
  cluster: string;
  confidence: number; // 0..1, how sure the matcher is about the cluster
  existing_claim_id: string | null; // a verified claim already covers it
  action: "new_claim" | "attach_answer" | "skip";
  suggested_owner: string | null;
  reason: string;
}

export interface ImportPreview {
  id: string;
  filename: string;
  customer: string;
  rows: ImportRow[];
  counts: { new_claim: number; attach_answer: number; skip: number };
  /** People who own claims today; the owner picker offers them. Live API only. */
  owners?: string[];
}

export interface ImportCommitResult {
  proposals: number; // draft claims opened as proposals
  attached: number; // approved answers attached to existing claims
  skipped: number;
}

export interface ApiError {
  error: string;
  code: string;
}

export const API_BASE: string | null =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
    ? process.env.NEXT_PUBLIC_API_BASE.replace(/\/+$/, "")
    : null;

export const IS_MOCK = API_BASE === null;

let bearer: string | null = null;
/** The embedded handshake hands us a JWT; it lives in memory only. */
// Dev only: a bearer for standalone runs against a local API. Never set in a
// deployed build; embedded views get their token from the Atlan handshake.
if (process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_DEV_TOKEN) {
  // dead code in a production build: NODE_ENV is inlined and the branch is removed
  bearer = process.env.NEXT_PUBLIC_DEV_TOKEN;
}

export function setAuthToken(token: string | null) {
  bearer = token;
}

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  const res = await fetch(`${API_BASE}/v1${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit",
  });
  if (!res.ok) {
    let err: ApiError = { error: res.statusText, code: `HTTP_${res.status}` };
    try {
      err = (await res.json()) as ApiError;
    } catch {
      // not JSON; keep the status text
    }
    throw new ApiRequestError(res.status, err.code, err.error);
  }
  return (await res.json()) as T;
}

export interface Api {
  listQuestionnaires(): Promise<Questionnaire[]>;
  getQuestionnaire(id: string): Promise<Questionnaire>;
  listItems(questionnaireId: string): Promise<QuestionItem[]>;
  listQuarantine(questionnaireId: string): Promise<QuestionItem[]>;
  /** Ranked queue: value_rank*3 + blocks_deal*5 + age_days, highest first. */
  reviewQueue(): Promise<QuestionItem[]>;
  getQuestion(id: string): Promise<QuestionDetail>;
  ask(text: string, audience?: Audience): Promise<Verdict>;
  approve(itemId: string): Promise<QuestionItem>;
  edit(itemId: string, answer: string): Promise<{ item: QuestionItem; proposal: ClaimProposal | null }>;
  route(itemId: string, to: string, deadline: string): Promise<QuestionItem>;
  send(itemId: string): Promise<QuestionItem>;
  listClaims(): Promise<Claim[]>;
  getClaim(id: string): Promise<Claim>;
  listProposals(): Promise<ClaimProposal[]>;
  approveProposal(id: string): Promise<ClaimProposal>;
  rejectProposal(id: string): Promise<ClaimProposal>;
  freshness(): Promise<FreshnessGroup[]>;
  /** Upload a completed questionnaire; returns a preview, commits nothing. */
  importAnswers(file: File, meta: { customer: string; audience: Audience }): Promise<ImportPreview>;
  /** Commit the preview: every new_claim becomes a proposal, never a verified claim. */
  commitImport(previewId: string, rows: Array<{ ordinal: number; action: ImportRow["action"]; owner: string | null }>): Promise<ImportCommitResult>;
  degradation(): Promise<DegradationState>;
  metrics(): Promise<Metrics>;
  trustPreview(): Promise<TrustPreviewEntry[]>;
  evalRecords(): Promise<EvalRecord[]>;
}

import { liveApi } from "./live";

async function upload<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  const res = await fetch(`${API_BASE}/v1${path}`, { method: "POST", headers, body: form, credentials: "omit" });
  if (!res.ok) {
    let err: ApiError = { error: res.statusText, code: `HTTP_${res.status}` };
    try {
      err = (await res.json()) as ApiError;
    } catch {
      // not JSON; keep the status text
    }
    throw new ApiRequestError(res.status, err.code, err.error);
  }
  return (await res.json()) as T;
}

const live: Api = liveApi(request, upload);

// The mock is loaded lazily so the live bundle does not carry fixture data.
let mockPromise: Promise<Api> | null = null;
function mock(): Promise<Api> {
  if (!mockPromise) mockPromise = import("./mock").then((m) => m.mockApi);
  return mockPromise;
}

function viaMock<K extends keyof Api>(key: K): Api[K] {
  return ((...args: unknown[]) =>
    mock().then((m) => (m[key] as (...a: unknown[]) => unknown)(...args))) as Api[K];
}

export const api: Api = IS_MOCK
  ? {
      listQuestionnaires: viaMock("listQuestionnaires"),
      getQuestionnaire: viaMock("getQuestionnaire"),
      listItems: viaMock("listItems"),
      listQuarantine: viaMock("listQuarantine"),
      reviewQueue: viaMock("reviewQueue"),
      getQuestion: viaMock("getQuestion"),
      ask: viaMock("ask"),
      approve: viaMock("approve"),
      edit: viaMock("edit"),
      route: viaMock("route"),
      send: viaMock("send"),
      listClaims: viaMock("listClaims"),
      getClaim: viaMock("getClaim"),
      listProposals: viaMock("listProposals"),
      approveProposal: viaMock("approveProposal"),
      rejectProposal: viaMock("rejectProposal"),
      freshness: viaMock("freshness"),
      importAnswers: viaMock("importAnswers"),
      commitImport: viaMock("commitImport"),
      degradation: viaMock("degradation"),
      metrics: viaMock("metrics"),
      trustPreview: viaMock("trustPreview"),
      evalRecords: viaMock("evalRecords"),
    }
  : live;

/** Ranking used by the review queue, mirrored from workflow/ranking.py. */
export function rankScore(item: QuestionItem): number {
  return item.value_rank * 3 + (item.blocks_deal ? 5 : 0) + item.age_days;
}
