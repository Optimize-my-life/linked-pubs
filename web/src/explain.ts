// Plain-language explanations shown in the UI. Keep every sentence short: attention is scarce.
import type { Arm, Experiment, Progress } from "./api";

export const model = (spec?: string | null) => (spec ?? "").replace(/^ollama:/, "").replace(/^anthropic:/, "");

const dataOf = (a: Arm) => a.data;

export function describeData(d: Arm["data"]): string {
  if (d.kind === "documents") return "your dropped documents";
  return d.limit ? `${d.limit} SciFact ${d.split} claim${d.limit === 1 ? "" : "s"}` : `all SciFact ${d.split} claims`;
}

export function describeArm(a: Arm): string {
  const x = model(a.extractor), v = model(a.verifier);
  if (a.mode === "abstract") return `${v} judges each claim against the full abstract.`;
  if (a.mode === "statements") return `${x} extracts statements; ${v} judges claims against those only.`;
  if (dataOf(a).kind === "documents") return `${x} extracts statements from the documents.`;
  return `${x} extracts statements; scored on quote accuracy and evidence coverage.`;
}

/** One headline plus short notes on what the comparison will show. */
export function describePlan(arms: Arm[]): { headline: string; notes: string[] } {
  if (!arms.length) return { headline: "", notes: [] };
  const datasets = [...new Set(arms.map((a) => describeData(dataOf(a))))];
  const headline = `Runs ${arms.length} arm${arms.length > 1 ? "s" : ""} on ${datasets.join(" and ")}.`;
  const notes: string[] = [];
  for (const s of arms.filter((a) => a.mode === "statements")) {
    const a = arms.find((b) => b.mode === "abstract" && b.verifier === s.verifier &&
      JSON.stringify(dataOf(b)) === JSON.stringify(dataOf(s)));
    if (a) notes.push(`${a.id} vs ${s.id} shows what extraction loses.`);
  }
  const verifiers = [...new Set(arms.filter((a) => a.verifier).map((a) => model(a.verifier)))];
  const extractors = [...new Set(arms.filter((a) => a.extractor).map((a) => model(a.extractor)))];
  if (verifiers.length > 1) notes.push(`Compares verifiers: ${verifiers.join(", ")}.`);
  if (extractors.length > 1) notes.push(`Compares extractors: ${extractors.join(", ")}.`);
  return { headline, notes };
}

const dur = (s: number) => (s < 60 ? `${Math.max(1, Math.round(s))} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
export { dur };

/** "Extracting statements with qwen3:8b · abstract 7 of 19 · ~12 min left" */
export function describeProgress(p: Progress, nowSec = Date.now() / 1000): string {
  if (!p) return "";
  const arm = p.arms > 1 ? `arm ${p.arm_index} of ${p.arms} · ` : "";
  if (!p.step) return `${arm}preparing…`;
  const what = p.step === "extract"
    ? `Extracting statements with ${model(p.model)}`
    : `${model(p.model)} judging claims against ${p.mode === "abstract" ? "abstracts" : "statements"}`;
  if (p.total === 0) return `${arm}${what} · all cached`;
  const unit = p.step === "extract" ? "text" : "pair";
  let eta = "";
  if (p.step_started && p.done > 0) {
    const perItem = (nowSec - p.step_started) / p.done;
    eta = ` · ~${dur(perItem * (p.total - p.done))} left`;
  } else if (p.done === 0) {
    eta = " · first one is slowest (model loading)";
  }
  return `${arm}${what} · ${unit} ${Math.min(p.done + 1, p.total)} of ${p.total}${eta}`;
}

/** Short verdict lines for a finished (or partly finished) experiment. */
export function describeResults(exp: Experiment): string[] {
  const lines: string[] = [];
  const res = (id: string) => exp.results.find((r) => r.arm === id)?.summary;
  for (const c of exp.comparisons) {
    const a = res(c.abstract_arm)?.label?.macro_f1, s = res(c.statements_arm)?.label?.macro_f1;
    if (a === undefined || s === undefined) continue;
    lines.push(c.extraction_loss_macro_f1 > 0
      ? `With statements only, ${model(c.verifier)} scores ${s.toFixed(2)} instead of ${a.toFixed(2)}: extraction by ${model(c.extractor)} loses ${c.extraction_loss_macro_f1.toFixed(2)}.`
      : `With statements only, ${model(c.verifier)} scores ${s.toFixed(2)}, ${s === a ? "the same as" : "better than"} on full abstracts (${a.toFixed(2)}).`);
  }
  for (const mode of ["abstract", "statements"] as const) {
    const scored = exp.results.filter((r) => r.mode === mode && r.summary?.label);
    if (scored.length > 1) {
      const best = scored.reduce((x, y) => (y.summary!.label!.macro_f1 > x.summary!.label!.macro_f1 ? y : x));
      const arm = exp.arms.find((a) => a.id === best.arm);
      lines.push(`Best ${mode === "abstract" ? "on abstracts" : "on statements"}: ${best.arm} (${model(arm?.verifier)}), ${best.summary!.label!.macro_f1.toFixed(2)}.`);
    }
  }
  const ex = exp.results.find((r) => typeof r.summary?.extraction?.rationale_coverage === "number")?.summary?.extraction;
  if (ex) {
    lines.push(`Statements quote ${Math.round((ex.rationale_coverage ?? 0) * 100)}% of the gold evidence; ${Math.round(ex.grounded_rate * 100)}% of quotes are found in the source.`);
  }
  const pairs = Math.max(0, ...exp.results.map((r) => r.summary?.pairs ?? 0));
  if (pairs > 0 && pairs < 100) lines.push(`Only ${pairs} pair${pairs === 1 ? "" : "s"}: differences below ~0.1 can be chance.`);
  const failed = exp.results.reduce((n, r) => n + (r.summary?.errors ?? 0) + (r.error ? 1 : 0), 0);
  if (failed) lines.push(`${failed} item(s) failed; open the arm rows for details.`);
  return lines;
}

export const METRIC_HELP: Record<string, string> = {
  "macro-F1": "Label score averaged over SUPPORT, CONTRADICT and NOT ENOUGH INFO. 0–1, higher is better.",
  acc: "Share of claim/abstract pairs labelled correctly.",
  "rat. F1": "Did the verifier point to the right evidence sentences? 0–1.",
  stmts: "Statements extracted.",
  "quote ok": "Share of statements whose quote was found word for word in the source.",
  cover: "Share of gold evidence sentences that some statement quotes.",
  time: "Wall-clock time for this arm.",
};
