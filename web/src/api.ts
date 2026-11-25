export type ModelInfo = {
  spec: string;
  name: string;
  free: boolean;
  size_gb?: number;
  params?: string;
  quant?: string;
};

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
  verifier: string | null;
  path: string[];
  label?: string;
};

export type Compiled = { arms: Arm[]; errors: string[] };

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
  summary: null | {
    pairs?: number;
    errors?: number;
    error_messages?: string[];
    label?: { accuracy: number; macro_f1: number; per_class: Record<string, { f1: number }> };
    rationale?: { precision: number; recall: number; f1: number };
    extraction?: { documents: number; statements: number; grounded_rate: number; rationale_coverage?: number | null };
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
    extraction_loss_macro_f1: number }[];
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
  compile: (graph: GraphJSON) => call<Compiled>("/api/compile", post(graph)),
  submit: (name: string, graph: GraphJSON) => call<Experiment>("/api/experiments", post({ name, graph })),
  experiments: () => call<ExperimentSummary[]>("/api/experiments"),
  experiment: (id: string) => call<Experiment>(`/api/experiments/${id}`),
  cancel: (id: string) => call<Experiment>(`/api/experiments/${id}/cancel`, { method: "POST" }),
  rows: (id: string, arm: string) => call<Record<string, unknown>[]>(`/api/experiments/${id}/arms/${arm}/rows`),
  createDocset: () => call<DocsetSummary>("/api/docsets", { method: "POST" }),
  upload: (docset: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return call<DocsetSummary>(`/api/docsets/${docset}/files`, { method: "POST", body: form });
  },
};
