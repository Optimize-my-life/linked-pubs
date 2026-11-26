// Word-level diff for prompt texts: shows what a new prompt version changes.
export type Piece = { op: "same" | "add" | "del"; text: string };

const tokens = (s: string) => s.split(/(\s+)/).filter((t) => t !== "");

export function diffWords(a: string, b: string): Piece[] {
  const x = tokens(a), y = tokens(b);
  // Edits are usually local: strip the shared start and end before the quadratic part.
  let pre = 0;
  while (pre < x.length && pre < y.length && x[pre] === y[pre]) pre++;
  let post = 0;
  while (post < x.length - pre && post < y.length - pre && x[x.length - 1 - post] === y[y.length - 1 - post]) post++;
  const xm = x.slice(pre, x.length - post), ym = y.slice(pre, y.length - post);
  const out: Piece[] = [];
  const push = (op: Piece["op"], text: string) => {
    if (!text) return;
    const last = out[out.length - 1];
    if (last && last.op === op) last.text += text;
    else out.push({ op, text });
  };
  push("same", x.slice(0, pre).join(""));
  if (xm.length * ym.length > 4_000_000) {
    push("del", xm.join(""));
    push("add", ym.join(""));
  } else {
    // Longest common subsequence table, filled from the end.
    const w = ym.length + 1;
    const t = new Uint32Array((xm.length + 1) * w);
    for (let i = xm.length - 1; i >= 0; i--) {
      for (let j = ym.length - 1; j >= 0; j--) {
        t[i * w + j] = xm[i] === ym[j] ? t[(i + 1) * w + j + 1] + 1 : Math.max(t[(i + 1) * w + j], t[i * w + j + 1]);
      }
    }
    let i = 0, j = 0;
    while (i < xm.length || j < ym.length) {
      if (i < xm.length && j < ym.length && xm[i] === ym[j]) { push("same", xm[i]); i++; j++; }
      else if (j < ym.length && (i === xm.length || t[i * w + j + 1] >= t[(i + 1) * w + j])) { push("add", ym[j]); j++; }
      else { push("del", xm[i]); i++; }
    }
  }
  push("same", x.slice(x.length - post).join(""));
  return out;
}

/** "adds 12 words, removes 3" */
export function describeDiff(pieces: Piece[]): string {
  const words = (op: Piece["op"]) => pieces.filter((p) => p.op === op).reduce((n, p) => n + tokens(p.text).filter((t) => t.trim()).length, 0);
  const add = words("add"), del = words("del");
  if (!add && !del) return "no changes yet";
  return [add && `adds ${add} word${add === 1 ? "" : "s"}`, del && `removes ${del}`].filter(Boolean).join(", ");
}
