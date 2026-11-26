import { useEffect, useState, type ReactNode } from "react";
import { api, type Arm, type ArmResult, type Comparison, type Experiment, type Rows as RowsData } from "./api";
import { describeArm, describeProgress, describeResults, dur, LABEL, METRIC_HELP, model, promptTag } from "./explain";

const pct = (x?: number | null) => (x === undefined || x === null ? "–" : `${Math.round(x * 100)}%`);
const num = (x?: number | null) => (x === undefined || x === null ? "–" : x.toFixed(2));
const MODE_LABEL = { abstract: "vs. abstracts", statements: "vs. statements", extraction: "extraction only" };

type View = { kind: "rows"; arm: string } | { kind: "compare"; a: string; s: string } | null;

export function Results({ exp, onLoadGraph }: { exp: Experiment; onLoadGraph: () => void }) {
  const [view, setView] = useState<View>(null);
  const p = exp.progress;
  const verdict = describeResults(exp);
  const active = exp.status === "running" || exp.status === "queued";
  return (
    <div className="results">
      <div className="row between">
        <h3 className="ellipsis" title={exp.name}>{exp.name}</h3>
        <span className={`status status-${exp.status}`}>{exp.status}</span>
      </div>
      <div className="muted small">{new Date(exp.created_at).toLocaleString()}</div>
      {p && (
        <div className="progress">
          <div className="small">{describeProgress(p)}</div>
          <div className="bar"><div style={{ width: `${p.total ? (100 * p.done) / p.total : 0}%` }} /></div>
        </div>
      )}
      {exp.error && <div className="error small">{exp.error}</div>}

      {verdict.length > 0 && (
        <div className="card verdict">
          {verdict.map((line, i) => <div key={i}>{line}</div>)}
        </div>
      )}

      {exp.comparisons.length > 1 && <ComparisonTable exp={exp} />}

      {exp.comparisons.map((c) => (
        <button key={c.statements_arm} className="link-button"
          onClick={() => setView({ kind: "compare", a: c.abstract_arm, s: c.statements_arm })}>
          Why? Show the pairs where {c.abstract_arm} and {c.statements_arm} disagree →
        </button>
      ))}

      {exp.arms.map((arm) => (
        <ArmCard key={arm.id} arm={arm} r={exp.results.find((x) => x.arm === arm.id)}
          onRows={() => setView({ kind: "rows", arm: arm.id })} />
      ))}

      <div className="row gap">
        <button onClick={onLoadGraph} title="Put this experiment's blocks back on the canvas to rerun or vary it">
          Load into canvas
        </button>
        {active && <button className="danger" onClick={() => api.cancel(exp.id)}>Cancel</button>}
      </div>

      {view?.kind === "rows" && <Rows expId={exp.id} armId={view.arm} key={view.arm} onClose={() => setView(null)} />}
      {view?.kind === "compare" && (
        <CompareView expId={exp.id} a={view.a} s={view.s} key={view.s} onClose={() => setView(null)} />
      )}
    </div>
  );
}

/** One row per extractor setup, best score on statements first. */
function ComparisonTable({ exp }: { exp: Experiment }) {
  const f1 = (arm: string) => exp.results.find((r) => r.arm === arm)?.summary?.label?.macro_f1;
  const rows = exp.comparisons
    .map((c) => ({ c, arm: exp.arms.find((a) => a.id === c.statements_arm), s: f1(c.statements_arm), a: f1(c.abstract_arm) }))
    .sort((x, y) => (y.s ?? -1) - (x.s ?? -1));
  const best = rows[0]?.s;
  return (
    <div className="card">
      <div className="card-title">All setups, best first</div>
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "46%" }} title="extractor (prompt) → judge">setup</th>
            <th title={METRIC_HELP["macro-F1"]}>statements</th>
            <th title="Same judge on the full abstracts">abstracts</th>
            <th title="abstracts minus statements: what extraction loses">loss</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, arm, s, a }) => (
            <tr key={c.statements_arm} className={s !== undefined && s === best ? "best" : ""}>
              <td className="ellipsis" title={arm ? describeArm(arm) : ""}>
                {c.statements_arm} · {model(arm?.extractor)}{promptTag(arm?.extractor_prompt)} → {model(arm?.verifier)}{promptTag(arm?.verifier_prompt)}
              </td>
              <td>{num(s)}</td>
              <td>{num(a)}</td>
              <td>{num(c.extraction_loss_macro_f1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ name, value }: { name: keyof typeof METRIC_HELP; value: string }) {
  return <span className="metric" title={METRIC_HELP[name]}><span>{name}</span> <b>{value}</b></span>;
}

function ArmCard({ arm, r, onRows }: { arm: Arm; r?: ArmResult; onRows: () => void }) {
  const s = r?.summary;
  const errs = s?.error_messages ?? [];
  return (
    <div className={`card arm-card ${r ? "" : "pending"}`}>
      <div className="row between">
        <span><b>{arm.id}</b> <span className="tag">{MODE_LABEL[arm.mode]}</span></span>
        <span className="muted small">{r ? dur(r.seconds) : "not run yet"}</span>
      </div>
      <div className="muted small">{describeArm(arm)}</div>
      {s && (
        <div className="metrics">
          {s.label && <Metric name="macro-F1" value={num(s.label.macro_f1)} />}
          {s.label && <Metric name="acc" value={pct(s.label.accuracy)} />}
          {s.rationale && arm.mode !== "extraction" && <Metric name="rat. F1" value={num(s.rationale.f1)} />}
          {s.extraction && <Metric name="stmts" value={String(s.extraction.statements)} />}
          {s.extraction && <Metric name="quote ok" value={pct(s.extraction.grounded_rate)} />}
          {s.extraction?.rationale_coverage != null && <Metric name="cover" value={pct(s.extraction.rationale_coverage)} />}
        </div>
      )}
      {r?.error && <div className="error small">{r.error}</div>}
      {errs.length > 0 && <div className="error small">{errs.length} item(s) failed, e.g. {errs[0]}</div>}
      {s && (
        <button className="link-button" onClick={onRows}>
          Show {arm.mode === "extraction" ? "statements" : "predictions"} →
        </button>
      )}
    </div>
  );
}

function Panel({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="card rows">
      <div className="row between">
        <div className="card-title">{title}</div>
        <button className="close" onClick={onClose} title="Close">×</button>
      </div>
      {children}
    </div>
  );
}

function Rows({ expId, armId, onClose }: { expId: string; armId: string; onClose: () => void }) {
  const [rows, setRows] = useState<RowsData | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.rows(expId, armId).then(setRows).catch((e) => setErr(e.message));
  }, [expId, armId]);
  if (err) return <div className="error small">{err}</div>;
  if (!rows) return <div className="muted small">loading…</div>;
  if (rows.predictions.length) {
    const wrong = rows.predictions.filter((r) => r.pred !== r.gold).length;
    return (
      <Panel title={`${armId}: ${rows.predictions.length} predictions, ${wrong} wrong (marked)`} onClose={onClose}>
        {rows.predictions.map((r, i) => (
          <div key={i} className={`rowitem ${r.gold === r.pred ? "" : "wrong"}`}>
            <div>{r.claim ?? `claim ${r.claim_id}`}</div>
            <div className="small">
              gold <b>{LABEL[r.gold] ?? r.gold}</b> · predicted <b>{r.pred ? LABEL[r.pred] ?? r.pred : "error"}</b>
            </div>
            <div className="muted small">{r.error || r.explanation}</div>
          </div>
        ))}
      </Panel>
    );
  }
  const bad = rows.statements.filter((s) => !s.grounded).length;
  return (
    <Panel title={`${armId}: ${rows.statements.length} statements, ${bad} with a quote not found (marked)`} onClose={onClose}>
      {rows.statements.map((s, i) => (
        <div key={i} className={`rowitem ${s.grounded ? "" : "wrong"}`}>
          <div><span className="tag">{s.type}</span> {s.text}</div>
          <div className="muted small">“{s.evidence_quote}”</div>
        </div>
      ))}
    </Panel>
  );
}

const KIND = {
  lost: "right on the abstract, wrong on statements",
  both_wrong: "wrong both ways, differently",
  gained: "wrong on the abstract, right on statements",
};

function CompareView({ expId, a, s, onClose }: { expId: string; a: string; s: string; onClose: () => void }) {
  const [data, setData] = useState<Comparison | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.compare(expId, a, s).then(setData).catch((e) => setErr(e.message));
  }, [expId, a, s]);
  if (err) return <div className="error small">{err}</div>;
  if (!data) return <div className="muted small">loading…</div>;
  const c = data.counts;
  const lost = data.items.filter((i) => i.kind === "lost" && i.gold_evidence.length);
  const empty = lost.filter((i) => i.statements.length === 0).length;
  const missed = lost.filter((i) => i.statements.length > 0 && !i.gold_evidence_quoted).length;
  const quoted = lost.length - empty - missed;
  const why = [
    empty && `${empty} had no statements at all (extractor returned nothing)`,
    missed && `${missed} had statements that skip the gold evidence`,
    quoted && `${quoted} quoted the evidence but lost a detail the verdict needed`,
  ].filter(Boolean);
  return (
    <Panel title={`${a} vs ${s}`} onClose={onClose}>
      <div className="verdict-inline">
        Extraction cost {c.lost} pair{c.lost === 1 ? "" : "s"} and won {c.gained}; {c.same} came out the same.
        {why.length > 0 && ` Of the lost pairs, ${why.join("; ")}.`}
      </div>
      {data.items.map((it) => (
        <div key={`${it.claim_id}-${it.doc_id}`}
          className={`rowitem ${it.kind === "lost" ? "wrong" : it.kind === "gained" ? "right" : ""}`}>
          <div className="small muted">{KIND[it.kind]}</div>
          <div><b>Claim:</b> {it.claim}</div>
          <div className="small">
            gold <b>{LABEL[it.gold]}</b> · abstract → <b>{LABEL[it.abstract_pred ?? ""] ?? "error"}</b>
            {" "}· statements → <b>{LABEL[it.statements_pred ?? ""] ?? "error"}</b>
          </div>
          {it.gold_evidence.length > 0 && (
            <div className="small evidence">
              <b>Gold evidence</b> ({it.statements.length === 0 ? "no statements extracted from this abstract"
                : it.gold_evidence_quoted ? "quoted by a statement" : "not quoted by any statement"}):
              {it.gold_evidence.map((g, i) => <div key={i} className="quote">“{g}”</div>)}
            </div>
          )}
          <details className="small">
            <summary>{it.statements.length} statements the verifier saw · its reasoning</summary>
            {it.statements.map((st, i) => <div key={i} className="stmt"><span className="tag">{st.type}</span> {st.text}</div>)}
            <div className="muted">On statements: {it.statements_explanation}</div>
            <div className="muted">On the abstract: {it.abstract_explanation}</div>
          </details>
        </div>
      ))}
      {data.items.length === 0 && <div className="muted small">No disagreements.</div>}
    </Panel>
  );
}
