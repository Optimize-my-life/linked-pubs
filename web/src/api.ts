export type ModelInfo = {
  spec: string;
  name: string;
  free: boolean;
  size_gb?: number;
  params?: string;
  quant?: string;
};

export type PromptKind = "extract" | "verify";
export type PromptInfo = {
  id: string; kind: PromptKind; name: string; note: string; text: string;
  base: string | null; builtin: boolean; created_at: string | null;
};

export type PullState = { name: string; status: string; completed: number; total: number; error: string | null };
export type CatalogEntry = { name: string; gb: number | null; note: string; installed: boolean; pull: PullState | null };

export type Health = {
  ollama_host: string;
  ollama_version: string | null;
  allow_paid: boolean;
  scifact: boolean;
};

export type GraphJSON = {
  nodes: { id: string; type: string; data: Record<string, unknown>; position?: { x: number; y: number } }[];
  edges: { source: string; target: string }[];
};

export type Arm = {
  id: string;
  mode: "abstract" | "statements" | "extraction";
  data: { kind: "scifact" | "documents"; split: string; limit: number; docset_id: string | null };
  extractor: string | null;
  extractor_prompt?: string;
  verifier: string | null;
  verifier_prompt?: string;
  path: string[];
  auto?: boolean;
  label?: string;
};

export type Estimate = {
  arm: string;
  pairs?: number;
  texts?: number;
  cached?: number;
  extract_calls?: number;
  verify_calls?: number;
  seconds?: number | null;
  unknown?: string[];
  error?: string;
};

export type Compiled = { arms: Arm[]; errors: string[]; estimates?: Estimate[] };

export type Prediction = {
  claim_id: number; doc_id: string; claim?: string; gold: string; pred: string | null;
  explanation: string; error: string; gold_rationale: number[]; pred_rationale: number[];
};
export type StatementRow = { id: string; source_id: string; text: string; type: string; evidence_quote: string; grounded: boolean };
export type Rows = { predictions: Prediction[]; statements: StatementRow[] };

export type CompareItem = {
  kind: "lost" | "gained" | "both_wrong";
  claim_id: number; doc_id: string; claim: string; title: string;
  gold: string; abstract_pred: string | null; statements_pred: string | null;
  abstract_explanation: string; statements_explanation: string;
  gold_evidence: string[]; gold_evidence_quoted: boolean;
  statements: { text: string; type: string }[];
};
export type Comparison = { counts: Record<"lost" | "gained" | "both_wrong" | "same", number>; items: CompareItem[] };

export type BoardRow = {
  experiment: string; experiment_name: string; date: string; arm: string; data: string;
  mode: Arm["mode"]; extractor: string | null; extractor_prompt?: string; verifier: string | null; verifier_prompt?: string; pairs: number | null;
  macro_f1: number | null; accuracy: number | null; rationale_f1: number | null;
  statements: number | null; grounded_rate: number | null; rationale_coverage: number | null; seconds: number | null;
};

export type Progress = {
  arm: string;
  arm_index: number;
  arms: number;
  mode: "abstract" | "statements" | "extraction";
  step: "extract" | "verify" | "";
  done: number;
  total: number;
  model: string | null;
  active_node: string | null;
  path: string[];
  step_started: number | null;
} | null;

export type ArmResult = {
  arm: string;
  label: string;
  mode: Arm["mode"];
  seconds: number;
  error: string | null;
  timings?: Record<string, { model: string; calls: number; seconds: number }>;
  summary: null | {
    pairs?: number;
    errors?: number;
    error_messages?: string[];
    label?: { accuracy: number; macro_f1: number; per_class: Record<string, { f1: number }> };
    rationale?: { precision: number; recall: number; f1: number };
    extraction?: { documents: number; empty_documents?: number; statements: number; grounded_rate: number; rationale_coverage?: number | null };
  };
};

export type Experiment = {
  id: string;
  name: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
  created_at: string;
  graph: GraphJSON;
  arms: Arm[];
  progress: Progress;
  results: ArmResult[];
  comparisons: { abstract_arm: string; statements_arm: string; verifier: string; extractor: string;
    extractor_prompt?: string; verifier_prompt?: string; extraction_loss_macro_f1: number }[];
  error: string | null;
};

export type ExperimentSummary = Pick<Experiment, "id" | "name" | "status" | "created_at" | "progress" | "error"> & {
  arms: number;
};

export type DocsetSummary = { id: string; documents: { id: string; title: string; chars: number }[]; errors?: string[] };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => call<Health>("/api/health"),
  models: () => call<ModelInfo[]>("/api/models"),
  prompts: () => call<PromptInfo[]>("/api/prompts"),
  createPrompt: (p: { kind: PromptKind; name: string; text: string; note: string; base: string | null }) =>
    call<PromptInfo>("/api/prompts", post(p)),
  deletePrompt: (id: string) => call<{ deleted: string }>(`/api/prompts/${id}`, { method: "DELETE" }),
  catalog: () => call<CatalogEntry[]>("/api/models/catalog"),
  pull: (name: string) => call<PullState>("/api/models/pull", post({ name })),
  compile: (graph: GraphJSON) => call<Compiled>("/api/compile", post(graph)),
  submit: (name: string, graph: GraphJSON) => call<Experiment>("/api/experiments", post({ name, graph })),
  experiments: () => call<ExperimentSummary[]>("/api/experiments"),
  experiment: (id: string) => call<Experiment>(`/api/experiments/${id}`),
  cancel: (id: string) => call<Experiment>(`/api/experiments/${id}/cancel`, { method: "POST" }),
  rows: (id: string, arm: string) => call<Rows>(`/api/experiments/${id}/arms/${arm}/rows`),
  compare: (id: string, a: string, s: string) => call<Comparison>(`/api/experiments/${id}/compare/${a}/${s}`),
  leaderboard: () => call<BoardRow[]>("/api/leaderboard"),
  createDocset: () => call<DocsetSummary>("/api/docsets", { method: "POST" }),
  upload: (docset: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return call<DocsetSummary>(`/api/docsets/${docset}/files`, { method: "POST", body: form });
  },
};
