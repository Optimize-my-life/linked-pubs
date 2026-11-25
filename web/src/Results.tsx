import { useEffect, useState } from "react";
import { api, type ArmResult, type Experiment } from "./api";

const pct = (x?: number) => (x === undefined ? "–" : `${Math.round(x * 100)}%`);
const num = (x?: number) => (x === undefined ? "–" : x.toFixed(2));
const dur = (s: number) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

const MODE_LABEL = { abstract: "vs. abstracts", statements: "vs. statements", extraction: "extraction only" };

export function Results({ exp, onLoadGraph }: { exp: Experiment; onLoadGraph: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const p = exp.progress;
  return (
    <div className="results">
      <div className="row between">
        <h3>{exp.name}</h3>
        <span className={`status status-${exp.status}`}>{exp.status}</span>
      </div>
      <div className="muted small">{new Date(exp.created_at).toLocaleString()} · {exp.arms.length} arm(s)</div>
      {p && (
        <div className="progress">
          <div className="small">
            arm {p.arm_index}/{p.arms} · {p.step} {p.done}/{p.total}
          </div>
          <div className="bar"><div style={{ width: `${p.total ? (100 * p.done) / p.total : 0}%` }} /></div>
        </div>
      )}
      {exp.error && <div className="error small">{exp.error}</div>}
      <div className="row gap">
        <button onClick={onLoadGraph}>Load into canvas</button>
        {(exp.status === "running" || exp.status === "queued") && (
          <button className="danger" onClick={() => api.cancel(exp.id)}>Cancel</button>
        )}
      </div>

      {exp.comparisons.length > 0 && (
        <div className="card">
          <div className="card-title">Extraction loss (macro-F1 abstracts − statements)</div>
          {exp.comparisons.map((c) => (
            <div key={c.statements_arm} className="row between small">
              <span className="ellipsis">extract {c.extractor} · verify {c.verifier}</span>
              <b>{c.extraction_loss_macro_f1 >= 0 ? "−" : "+"}{Math.abs(c.extraction_loss_macro_f1).toFixed(2)}</b>
            </div>
          ))}
        </div>
      )}

      <table className="table">
        <thead>
          <tr><th>arm</th><th>macro-F1</th><th>acc</th><th>rat. F1</th><th>stmts</th><th>quote ok</th><th>cover</th><th>time</th></tr>
        </thead>
        <tbody>
          {exp.arms.map((arm) => {
            const r = exp.results.find((x) => x.arm === arm.id);
            return <ArmRow key={arm.id} armId={arm.id} label={r?.label ?? arm.label ?? arm.id} mode={arm.mode} r={r}
              onToggle={() => setOpen(open === arm.id ? null : arm.id)} />;
          })}
        </tbody>
      </table>
      {open && <Rows expId={exp.id} armId={open} key={open} />}
    </div>
  );
}

function ArmRow({ armId, label, mode, r, onToggle }: {
  armId: string; label: string; mode: ArmResult["mode"]; r?: ArmResult; onToggle: () => void;
}) {
  const s = r?.summary;
  const errs = (s?.error_messages ?? []).length;
  return (
    <>
      <tr className={r ? "clickable" : "pending"} onClick={r?.summary ? onToggle : undefined}>
        <td>
          <div className="ellipsis" title={label}><b>{armId}</b> {MODE_LABEL[mode]}</div>
          <div className="muted small ellipsis" title={label}>{label}</div>
        </td>
        <td><b>{num(s?.label?.macro_f1)}</b></td>
        <td>{pct(s?.label?.accuracy)}</td>
        <td>{num(s?.rationale?.f1)}</td>
        <td>{s?.extraction?.statements ?? "–"}</td>
        <td>{pct(s?.extraction?.grounded_rate)}</td>
        <td>{pct(s?.extraction?.rationale_coverage)}</td>
        <td>{r ? dur(r.seconds) : "–"}</td>
      </tr>
      {(r?.error || errs > 0) && (
        <tr><td colSpan={8} className="error small">
          {r?.error ?? `${errs} item error(s), e.g. ${s?.error_messages?.[0]}`}
        </td></tr>
      )}
    </>
  );
}

function Rows({ expId, armId }: { expId: string; armId: string }) {
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.rows(expId, armId).then(setRows).catch((e) => setErr(e.message));
  }, [expId, armId]);
  if (err) return <div className="error small">{err}</div>;
  if (!rows) return <div className="muted small">loading…</div>;
  const isStatements = rows.length > 0 && "evidence_quote" in rows[0];
  return (
    <div className="card rows">
      <div className="card-title">{armId}: {rows.length} {isStatements ? "statements" : "predictions"}</div>
      {rows.slice(0, 300).map((row, i) => isStatements ? (
        <div key={i} className={`rowitem ${row.grounded ? "" : "bad"}`}>
          <div><span className="tag">{String(row.type)}</span> {String(row.text)}</div>
          <div className="muted small">“{String(row.evidence_quote)}”{row.grounded ? "" : " · quote not found in source"}</div>
        </div>
      ) : (
        <div key={i} className={`rowitem ${row.gold === row.pred ? "" : "bad"}`}>
          <div className="small">claim {String(row.claim_id)} · doc {String(row.doc_id)} · gold <b>{String(row.gold)}</b> · pred <b>{String(row.pred ?? "error")}</b></div>
          <div className="muted small">{String(row.error || row.explanation || "")}</div>
        </div>
      ))}
    </div>
  );
}
