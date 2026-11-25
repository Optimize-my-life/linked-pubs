import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { createContext, useContext, useState, type DragEvent, type ReactNode } from "react";
import { api, type ModelInfo, type PromptInfo } from "./api";

export type BlockType = "dataset" | "documents" | "extractor" | "verifier" | "metrics";

export const BLOCKS: Record<BlockType, { title: string; hint: string; defaults: Record<string, unknown> }> = {
  dataset: { title: "SciFact", hint: "claims + abstracts with gold labels", defaults: { split: "dev", limit: 20 } },
  documents: { title: "Documents", hint: "drop PDFs here", defaults: {} },
  extractor: { title: "Extractor", hint: "text → typed statements", defaults: { model: "", prompt: "extract-v1" } },
  verifier: { title: "Verifier", hint: "claim + evidence → label", defaults: { model: "" } },
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

function ModelSelect({ id, value }: { id: string; value: string }) {
  const { models } = useContext(ModelsContext);
  const { updateNodeData } = useReactFlow();
  const known = models.some((m) => m.spec === value);
  return (
    <select className="nodrag" value={value} onChange={(e) => updateNodeData(id, { model: e.target.value })}>
      <option value="">choose a model…</option>
      {!known && value && <option value={value}>{value} (not available)</option>}
      {models.map((m) => (
        <option key={m.spec} value={m.spec}>
          {m.name}
          {m.params ? ` · ${m.params}` : ""}
          {m.size_gb ? ` · ${m.size_gb} GB` : ""}
          {m.free ? "" : " · paid"}
        </option>
      ))}
    </select>
  );
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

function PromptSelect({ id, value }: { id: string; value: string }) {
  const { prompts } = useContext(ModelsContext);
  const { updateNodeData } = useReactFlow();
  const current = prompts.find((p) => p.id === value);
  return (
    <select className="nodrag" value={value} title={current?.note}
      onChange={(e) => updateNodeData(id, { prompt: e.target.value })}>
      {!current && <option value={value}>{value}</option>}
      {prompts.map((p) => <option key={p.id} value={p.id}>{p.id.replace("extract-", "prompt ")}: {p.note}</option>)}
    </select>
  );
}

export function ExtractorNode({ id, data }: NodeProps) {
  const d = data as { model: string; prompt?: string };
  return (
    <Shell type="extractor" data={data}>
      <ModelSelect id={id} value={d.model} />
      <PromptSelect id={id} value={d.prompt ?? "extract-v1"} />
      <div className="muted">statements with verbatim quotes</div>
    </Shell>
  );
}

export function VerifierNode({ id, data }: NodeProps) {
  return (
    <Shell type="verifier" data={data}>
      <ModelSelect id={id} value={(data as { model: string }).model} />
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
