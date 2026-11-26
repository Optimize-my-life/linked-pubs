import { useCallback, useEffect, useState } from "react";
import { api, type CatalogEntry, type GraphJSON, type ModelInfo, type PromptInfo } from "./api";
import { model } from "./explain";
import { comparisonGraph, quickArmCount, type Role } from "./templates";

const GPU_GB = 16; // the big PC's RTX 4080 Super
const ROLE_TEXT: Record<Role, (fixed: string) => string> = {
  extractor: (f) => `Each model extracts statements; ${f} judges them all. Shows which model extracts best.`,
  verifier: (f) => `Each model judges claims, on abstracts and on statements extracted by ${f}. Shows which judge is best.`,
  both: () => "Each model extracts, then judges its own statements. Shows which model works best end to end.",
};

export function ModelsTab({ models, prompts, defaultModel, onChanged, onBuild }: {
  models: ModelInfo[]; prompts: PromptInfo[]; defaultModel: string;
  onChanged: () => void; onBuild: (g: GraphJSON) => void;
}) {
  return (
    <div className="models-tab">
      <QuickCompare models={models} prompts={prompts} defaultModel={defaultModel} onBuild={onBuild} />
      <Catalog onChanged={onChanged} />
    </div>
  );
}

function QuickCompare({ models, prompts, defaultModel, onBuild }: {
  models: ModelInfo[]; prompts: PromptInfo[]; defaultModel: string; onBuild: (g: GraphJSON) => void;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const [role, setRole] = useState<Role>("extractor");
  const [fixed, setFixed] = useState("");
  const [chosenPrompts, setChosenPrompts] = useState<string[]>(["extract-v1"]);
  const [limit, setLimit] = useState(20);
  const judge = fixed || defaultModel;
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const spec = { models: picked, role, fixed: judge, prompts: chosenPrompts, split: "dev", limit };
  const arms = quickArmCount(spec);
  const extractPrompts = prompts.filter((p) => p.kind === "extract");

  return (
    <div className="card">
      <div className="card-title">Compare models</div>
      <div className="muted small">Tick models; this builds the canvas for you.</div>
      <div className="checks">
        {models.length === 0 && <div className="muted small">No models installed yet: download some below.</div>}
        {models.map((m) => (
          <label key={m.spec} className="check">
            <input type="checkbox" checked={picked.includes(m.spec)} onChange={() => setPicked(toggle(picked, m.spec))} />
            {m.name} <span className="muted">{m.size_gb ? `${m.size_gb} GB` : ""}{m.free ? "" : " · paid"}</span>
          </label>
        ))}
      </div>
      <div className="row gap wrap small">
        {(["extractor", "verifier", "both"] as Role[]).map((r) => (
          <label key={r} className="check">
            <input type="radio" name="role" checked={role === r} onChange={() => setRole(r)} />
            {r === "extractor" ? "as extractors" : r === "verifier" ? "as judges" : "end to end"}
          </label>
        ))}
      </div>
      {role !== "both" && (
        <label className="stack small">
          {role === "extractor" ? "Fixed judge" : "Fixed extractor"}
          <select value={judge} onChange={(e) => setFixed(e.target.value)}>
            {models.map((m) => <option key={m.spec} value={m.spec}>{m.name}</option>)}
          </select>
        </label>
      )}
      <div className="small">Extraction prompts:</div>
      <div className="checks">
        {extractPrompts.map((p) => (
          <label key={p.id} className="check" title={p.note}>
            <input type="checkbox" checked={chosenPrompts.includes(p.id)}
              onChange={() => { const next = toggle(chosenPrompts, p.id); if (next.length) setChosenPrompts(next); }} />
            {p.name} <span className="muted">{p.note}</span>
          </label>
        ))}
      </div>
      <label className="stack small">
        SciFact dev claims
        <input type="number" min={1} value={limit} onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))} />
      </label>
      {picked.length > 0 && <div className="note small">{ROLE_TEXT[role](model(judge))}</div>}
      <button className="primary" disabled={!picked.length || !judge} onClick={() => onBuild(comparisonGraph(spec))}>
        {picked.length ? `Put on canvas: ${arms} arm${arms === 1 ? "" : "s"}` : "Tick at least one model"}
      </button>
      <div className="muted small">Replaces the current canvas (undo in Plan). Check the plan, then press Run.</div>
    </div>
  );
}

function Catalog({ onChanged }: { onChanged: () => void }) {
  const [rows, setRows] = useState<CatalogEntry[] | null>(null);
  const [custom, setCustom] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.catalog().then(setRows).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const busy = rows?.some((r) => r.pull && !["done", "failed"].includes(r.pull.status));
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [busy, load]);
  // When a download finishes, the new model should appear in every model picker.
  const doneCount = rows?.filter((r) => r.pull?.status === "done").length ?? 0;
  useEffect(() => { if (doneCount) onChanged(); }, [doneCount, onChanged]);

  const pull = (name: string) => {
    setErr("");
    api.pull(name).then(load).catch((e) => setErr(e.message));
  };

  return (
    <div className="card">
      <div className="card-title">Download free models</div>
      <div className="muted small">
        Downloads run on the machine with Ollama. Up to ~{GPU_GB - 2} GB runs fully on a {GPU_GB} GB GPU; bigger ones are much slower.
      </div>
      {err && <div className="error small">{err}</div>}
      {!rows && <div className="muted small">loading…</div>}
      {rows?.map((r) => (
        <div key={r.name} className="catalog-row">
          <div>
            <b>{r.name}</b> {r.gb != null && <span className={`muted ${r.gb > GPU_GB - 2 ? "warn" : ""}`}>{r.gb} GB</span>}
            {r.note && <div className="muted small">{r.note}</div>}
            {r.pull?.error && <div className="error small">{r.pull.error}</div>}
          </div>
          <PullButton entry={r} onPull={() => pull(r.name)} />
        </div>
      ))}
      <div className="row gap">
        <input placeholder="other model, e.g. mistral:7b" value={custom} onChange={(e) => setCustom(e.target.value)} />
        <button disabled={!custom.trim()} onClick={() => { pull(custom.trim()); setCustom(""); }}>Download</button>
      </div>
      <div className="muted small">Names as on ollama.com/library.</div>
    </div>
  );
}

function PullButton({ entry, onPull }: { entry: CatalogEntry; onPull: () => void }) {
  const p = entry.pull;
  if (entry.installed || p?.status === "done") return <span className="ok small">installed</span>;
  if (p && p.status !== "failed") {
    const pct = p.total ? Math.round((100 * p.completed) / p.total) : 0;
    return (
      <div className="pull">
        <div className="small">{p.total ? `${pct}%` : p.status}</div>
        <div className="bar"><div style={{ width: `${pct}%` }} /></div>
      </div>
    );
  }
  return <button onClick={onPull}>{p?.status === "failed" ? "Retry" : "Download"}</button>;
}
