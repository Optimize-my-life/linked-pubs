import { useMemo, useState } from "react";
import { api, type PromptInfo, type PromptKind } from "./api";
import { describeDiff, diffWords } from "./diff";

const KIND_TITLE: Record<PromptKind, string> = { extract: "Extraction prompts", verify: "Judge prompts" };
const KIND_HINT: Record<PromptKind, string> = {
  extract: "Tells the extractor what to pull out of a text. The JSON format is added automatically.",
  verify: "Tells the judge how to label a claim against evidence. The labels and JSON format are enforced automatically.",
};

type Draft = { kind: PromptKind; base: PromptInfo; name: string; note: string; text: string };

/** Prompt library: read the built-in prompts, copy one, change it, save it as a new version. */
export function PromptsTab({ prompts, onSaved, onUse }: {
  prompts: PromptInfo[]; onSaved: () => void; onUse: (p: PromptInfo) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const startFrom = (p: PromptInfo) => {
    setErr("");
    setMsg("");
    setDraft({ kind: p.kind, base: p, name: "", note: "", text: p.text });
  };
  const save = async () => {
    if (!draft) return;
    setErr("");
    try {
      const p = await api.createPrompt({ kind: draft.kind, name: draft.name, note: draft.note, text: draft.text, base: draft.base.id });
      setDraft(null);
      setOpen(p.id);
      setMsg(`Saved "${p.name}". Add it to the ${draft.kind === "extract" ? "extractor" : "verifier"} blocks to test it.`);
      onSaved();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const remove = async (p: PromptInfo) => {
    if (!confirm(`Delete "${p.name}"? Finished experiments keep their copy of the text.`)) return;
    try {
      await api.deletePrompt(p.id);
      onSaved();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  if (draft) return <Editor draft={draft} setDraft={setDraft} err={err} onSave={save} onCancel={() => setDraft(null)} />;

  return (
    <div className="prompts-tab">
      <div className="muted small">A saved prompt never changes, so results stay tied to the exact text. To change one, copy it and save a new version.</div>
      {msg && <div className="note small">{msg}</div>}
      {err && <div className="error small">{err}</div>}
      {(["extract", "verify"] as PromptKind[]).map((kind) => (
        <div key={kind} className="card">
          <div className="card-title">{KIND_TITLE[kind]}</div>
          <div className="muted small">{KIND_HINT[kind]}</div>
          {prompts.filter((p) => p.kind === kind).map((p) => (
            <div key={p.id} className="prompt-row">
              <div className="row between">
                <span className="clickable" onClick={() => setOpen(open === p.id ? null : p.id)}>
                  {open === p.id ? "▾" : "▸"} <b>{p.name}</b> {p.builtin && <span className="tag">built-in</span>}
                </span>
                <span className="row gap">
                  <button onClick={() => onUse(p)} title={`Add to every ${kind === "extract" ? "extractor" : "verifier"} block on the canvas`}>Use</button>
                  <button onClick={() => startFrom(p)}>Copy & edit</button>
                  {!p.builtin && <button className="danger" onClick={() => remove(p)}>Delete</button>}
                </span>
              </div>
              {(p.note || p.base) && (
                <div className="muted small">
                  {p.note}{p.note && p.base ? " · " : ""}{p.base ? `based on ${prompts.find((b) => b.id === p.base)?.name ?? p.base}` : ""}
                </div>
              )}
              {open === p.id && <PromptText p={p} base={prompts.find((b) => b.id === p.base)} />}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function PromptText({ p, base }: { p: PromptInfo; base?: PromptInfo }) {
  const [showDiff, setShowDiff] = useState(!!base);
  return (
    <div>
      {base && (
        <label className="check small">
          <input type="checkbox" checked={showDiff} onChange={() => setShowDiff(!showDiff)} /> show changes from {base.name}
        </label>
      )}
      {showDiff && base ? <Diff a={base.text} b={p.text} /> : <pre className="prompt-text">{p.text}</pre>}
    </div>
  );
}

function Diff({ a, b }: { a: string; b: string }) {
  const pieces = useMemo(() => diffWords(a, b), [a, b]);
  return (
    <>
      <div className="muted small">{describeDiff(pieces)}</div>
      <pre className="prompt-text">
        {pieces.map((x, i) => (
          <span key={i} className={x.op === "same" ? "" : `diff-${x.op}`}>
            {x.op === "same" ? shorten(x.text, i === 0, i === pieces.length - 1) : x.text}
          </span>
        ))}
      </pre>
    </>
  );
}

/** Long unchanged text between edits: keep some context around the changes, elide the rest. */
function shorten(text: string, first: boolean, last: boolean): string {
  const keep = 120;
  if (text.length <= 2 * keep + 20) return text;
  if (first && last) return text;
  if (first) return "… " + text.slice(-keep);
  if (last) return text.slice(0, keep) + " …";
  return text.slice(0, keep) + " … " + text.slice(-keep);
}

function Editor({ draft, setDraft, err, onSave, onCancel }: {
  draft: Draft; setDraft: (d: Draft) => void; err: string; onSave: () => void; onCancel: () => void;
}) {
  const changed = draft.text.trim() !== draft.base.text.trim();
  return (
    <div className="card prompt-editor">
      <div className="card-title">New {draft.kind === "extract" ? "extraction" : "judge"} prompt, from {draft.base.name}</div>
      <div className="muted small">{KIND_HINT[draft.kind]}</div>
      <label className="stack small">
        Name
        <input value={draft.name} placeholder="e.g. keep doses" onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label className="stack small">
        What it changes (one line, shown in the blocks)
        <input value={draft.note} placeholder="e.g. asks to keep every dose and unit"
          onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
      </label>
      <textarea className="prompt-input" value={draft.text} spellCheck={false}
        onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
      <details open={changed}>
        <summary className="small">Changes from {draft.base.name}</summary>
        <Diff a={draft.base.text} b={draft.text} />
      </details>
      {err && <div className="error small">{err}</div>}
      <div className="row gap">
        <button className="primary" disabled={!changed || !draft.name.trim()} onClick={onSave}>Save as new prompt</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
      {!changed && <div className="muted small">Change the text to save a new version.</div>}
    </div>
  );
}
