import { useEffect, useMemo, useState } from "react";
import { api, type BoardRow } from "./api";
import { dur, model, promptTag } from "./explain";

const MODE = { abstract: "on abstracts", statements: "on statements", extraction: "extraction only" };

/** All finished arms, grouped by dataset and mode, best first: which model setup works best so far. */
export function Leaderboard({ onOpen }: { onOpen: (experimentId: string) => void }) {
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.leaderboard().then(setRows).catch((e) => setErr(e.message));
  }, []);

  const groups = useMemo(() => {
    const g = new Map<string, BoardRow[]>();
    for (const r of rows ?? []) {
      const key = `${r.data} · ${MODE[r.mode]}`;
      g.set(key, [...(g.get(key) ?? []), r]);
    }
    for (const list of g.values()) {
      list.sort((a, b) => (b.macro_f1 ?? b.rationale_coverage ?? 0) - (a.macro_f1 ?? a.rationale_coverage ?? 0));
    }
    return [...g.entries()];
  }, [rows]);

  if (err) return <div className="error small">{err}</div>;
  if (!rows) return <div className="muted small">loading…</div>;
  if (!rows.length) return <div className="muted small">No finished experiments yet.</div>;
  return (
    <div className="board">
      <div className="muted small">Every finished arm, best first. Only rows in the same group are comparable.</div>
      {groups.map(([key, list]) => {
        const best = list[0];
        return (
          <div key={key} className="card">
            <div className="card-title">{key}</div>
            {best.macro_f1 != null && list.length > 1 && (
              <div className="small verdict-inline">
                Best: {setup(best)} with {best.macro_f1.toFixed(2)}.
              </div>
            )}
            {list.map((r) => (
              <div key={`${r.experiment}-${r.arm}`} className="board-row" onClick={() => onOpen(r.experiment)}
                title={`${r.experiment_name} · ${new Date(r.date).toLocaleString()} · click to open`}>
                <span className="ellipsis">{setup(r)}</span>
                <span>
                  {r.macro_f1 != null
                    ? <b>{r.macro_f1.toFixed(2)}</b>
                    : <b>{Math.round((r.rationale_coverage ?? r.grounded_rate ?? 0) * 100)}%</b>}
                </span>
                <span className="muted">{r.pairs ? `${r.pairs} pair${r.pairs === 1 ? "" : "s"}` : r.statements != null ? `${r.statements} stmts` : ""}</span>
                <span className="muted">{r.seconds != null ? dur(r.seconds) : ""}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function setup(r: BoardRow): string {
  if (r.mode === "abstract") return model(r.verifier);
  if (r.mode === "statements") return `${model(r.extractor)}${promptTag(r.extractor_prompt)} → ${model(r.verifier)}`;
  return model(r.extractor) + promptTag(r.extractor_prompt);
}
