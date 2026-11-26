import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { createContext, useContext, useState, type DragEvent, type ReactNode } from "react";
import { api, type ModelInfo, type PromptInfo, type PromptKind } from "./api";

export type BlockType = "dataset" | "documents" | "extractor" | "verifier" | "metrics";

export const BLOCKS: Record<BlockType, { title: string; hint: string; defaults: Record<string, unknown> }> = {
  dataset: { title: "SciFact", hint: "claims + abstracts with gold labels", defaults: { split: "dev", limit: 20 } },
  documents: { title: "Documents", hint: "drop PDFs here", defaults: {} },
  extractor: { title: "Extractor", hint: "text → typed statements", defaults: { models: [], prompts: ["extract-v1"] } },
  verifier: { title: "Verifier", hint: "claim + evidence → label", defaults: { models: [], prompts: ["verify-v1"] } },
  metrics: { title: "Metrics", hint: "scores every path ending here", defaults: {} },
};

// Which block may feed which: mirrors the arm shapes the server accepts.
export const ALLOWED: Record<BlockType, BlockType[]> = {
  dataset: ["extractor", "verifier"],
  documents: ["extractor"],
  extractor: ["verifier", "metrics"],
  verifier: ["metrics"],
  metrics: [],
};

type Ctx = { models: ModelInfo[]; defaultModel: string; prompts: PromptInfo[] };
export const ModelsContext = createContext<Ctx>({ models: [], defaultModel: "", prompts: [] });

function Shell({ type, data, children, inputs = true, outputs = true }: {
  type: BlockType; data?: Record<string, unknown>; children?: ReactNode; inputs?: boolean; outputs?: boolean;
}) {
  // _badges: results of the selected experiment for this block (set by the canvas, not saved).
  const badges = (data?._badges as string[] | undefined) ?? [];
  return (
    <div className={`block block-${type}`}>
      {inputs && <Handle type="target" position={Position.Left} />}
      <div className="block-title">{BLOCKS[type].title}</div>
      <div className="block-body">
        {children}
        {badges.map((b) => <div key={b} className="badge">{b}</div>)}
      </div>
      {outputs && <Handle type="source" position={Position.Right} />}
    </div>
  );
}

/** Models chosen on a block. Older graphs stored a single `model`. */
export function blockModels(data: Record<string, unknown>): string[] {
  if (Array.isArray(data.models)) return data.models as string[];
  return typeof data.model === "string" && data.model ? [data.model] : [];
}

export function blockPrompts(data: Record<string, unknown>, kind: PromptKind): string[] {
  if (Array.isArray(data.prompts) && data.prompts.length) return data.prompts as string[];
  if (typeof data.prompt === "string" && data.prompt) return [data.prompt];
  return [kind === "extract" ? "extract-v1" : "verify-v1"];
}

/** Chips for the chosen items plus a dropdown to add one more. Each extra choice is an extra arm. */
function Picker({ values, options, placeholder, onChange, minOne }: {
  values: string[]; options: { value: string; label: string; title?: string }[]; placeholder: string;
  onChange: (v: string[]) => void; minOne?: boolean;
}) {
  const find = (v: string) => options.find((o) => o.value === v);
  const rest = options.filter((o) => !values.includes(o.value));
  return (
    <div className="picker nodrag">
      {values.map((v) => (
        <span key={v} className={`chip ${find(v) ? "" : "missing"}`} title={find(v)?.title ?? "not available here"}>
          {find(v)?.label ?? `${v.replace(/^ollama:/, "")} (missing)`}
          {!(minOne && values.length === 1) && (
            <button title="remove" onClick={() => onChange(values.filter((x) => x !== v))}>×</button>
          )}
        </span>
      ))}
      {rest.length > 0 && (
        <select value="" onChange={(e) => e.target.value && onChange([...values, e.target.value])}>
          <option value="">{values.length ? "+ add" : placeholder}</option>
          {rest.map((o) => <option key={o.value} value={o.value} title={o.title}>{o.label}</option>)}
        </select>
      )}
    </div>
  );
}

function ModelPicker({ id, data }: { id: string; data: Record<string, unknown> }) {
  const { models } = useContext(ModelsContext);
  const { updateNodeData } = useReactFlow();
  const options = models.map((m) => ({
    value: m.spec,
    label: m.name + (m.free ? "" : " · paid"),
    title: [m.params, m.size_gb ? `${m.size_gb} GB` : "", m.quant].filter(Boolean).join(" · "),
  }));
  return <Picker values={blockModels(data)} options={options} placeholder="choose a model…"
    onChange={(v) => updateNodeData(id, { models: v, model: undefined })} />;
}

function PromptPicker({ id, data, kind }: { id: string; data: Record<string, unknown>; kind: PromptKind }) {
  const { prompts } = useContext(ModelsContext);
  const { updateNodeData } = useReactFlow();
  const options = prompts.filter((p) => p.kind === kind).map((p) => ({ value: p.id, label: p.name, title: p.note }));
  const values = blockPrompts(data, kind);
  const note = values.length === 1 ? prompts.find((p) => p.id === values[0])?.note : "";
  return (
    <>
      <Picker values={values} options={options} placeholder="prompt…" minOne
        onChange={(v) => updateNodeData(id, { prompts: v, prompt: undefined })} />
      {note && <div className="muted">{note}</div>}
    </>
  );
}

/** "2 models × 2 prompts: 4 variants" when a block holds more than one choice. */
function Variants({ data, kind }: { data: Record<string, unknown>; kind: PromptKind }) {
  const m = blockModels(data).length, p = blockPrompts(data, kind).length;
  if (m * p < 2) return null;
  return <div className="variants">{m} model{m === 1 ? "" : "s"} × {p} prompt{p === 1 ? "" : "s"}: {m * p} variants</div>;
}

export function DatasetNode({ id, data }: NodeProps) {
  const { updateNodeData } = useReactFlow();
  const d = data as { split: string; limit: number };
  return (
    <Shell type="dataset" data={data} inputs={false}>
      <label>
        split
        <select className="nodrag" value={d.split} onChange={(e) => updateNodeData(id, { split: e.target.value })}>
          <option value="dev">dev (300 claims)</option>
          <option value="train">train (809 claims)</option>
        </select>
      </label>
      <label>
        claims
        <input className="nodrag" type="number" min={0} value={d.limit}
          onChange={(e) => updateNodeData(id, { limit: Math.max(0, Number(e.target.value) || 0) })} />
      </label>
      <div className="muted">{d.limit ? `first ${d.limit}` : "all claims"}</div>
    </Shell>
  );
}

export function useUpload() {
  const { updateNodeData, getNode } = useReactFlow();
  return async (nodeId: string, files: File[]) => {
    const node = getNode(nodeId);
    const data = (node?.data ?? {}) as { docset_id?: string };
    updateNodeData(nodeId, { uploading: true, upload_errors: [] });
    try {
      const docset = data.docset_id ?? (await api.createDocset()).id;
      const res = await api.upload(docset, files);
      updateNodeData(nodeId, { docset_id: docset, docs: res.documents, upload_errors: res.errors ?? [], uploading: false });
    } catch (e) {
      updateNodeData(nodeId, { uploading: false, upload_errors: [String((e as Error).message)] });
    }
  };
}

export function DocumentsNode({ id, data }: NodeProps) {
  const upload = useUpload();
  const [over, setOver] = useState(false);
  const d = data as { docs?: { id: string; title: string }[]; uploading?: boolean; upload_errors?: string[] };
  const onDrop = (e: DragEvent) => {
    if (!e.dataTransfer.files.length) return;
    e.preventDefault();
    e.stopPropagation();
    setOver(false);
    upload(id, Array.from(e.dataTransfer.files));
  };
  const docs = d.docs ?? [];
  return (
    <Shell type="documents" data={data} inputs={false}>
      <div className={`dropzone nodrag ${over ? "over" : ""}`}
        onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setOver(true); } }}
        onDragLeave={() => setOver(false)} onDrop={onDrop}>
        {d.uploading ? "uploading…" : docs.length ? `${docs.length} document${docs.length > 1 ? "s" : ""}` : "drop PDFs / .txt here"}
      </div>
      {docs.slice(0, 4).map((doc) => <div key={doc.id} className="muted ellipsis">{doc.title}</div>)}
      {docs.length > 4 && <div className="muted">+{docs.length - 4} more</div>}
      {(d.upload_errors ?? []).map((e, i) => <div key={i} className="error small">{e}</div>)}
    </Shell>
  );
}

export function ExtractorNode({ id, data }: NodeProps) {
  return (
    <Shell type="extractor" data={data}>
      <ModelPicker id={id} data={data} />
      <PromptPicker id={id} data={data} kind="extract" />
      <Variants data={data} kind="extract" />
    </Shell>
  );
}

export function VerifierNode({ id, data }: NodeProps) {
  return (
    <Shell type="verifier" data={data}>
      <ModelPicker id={id} data={data} />
      <PromptPicker id={id} data={data} kind="verify" />
      <Variants data={data} kind="verify" />
      <div className="muted">SUPPORT / CONTRADICT / NEI</div>
    </Shell>
  );
}

export function MetricsNode({ data }: NodeProps) {
  return (
    <Shell type="metrics" data={data} outputs={false}>
      <div className="muted">macro-F1 · rationale F1 · extraction loss · time</div>
    </Shell>
  );
}

export const nodeTypes = {
  dataset: DatasetNode,
  documents: DocumentsNode,
  extractor: ExtractorNode,
  verifier: VerifierNode,
  metrics: MetricsNode,
};
