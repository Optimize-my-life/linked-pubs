// Plain-language explanations shown in the UI. Keep every sentence short: attention is scarce.
import type { Arm, Estimate, Experiment, Progress } from "./api.ts";

export const model = (spec?: string | null) => (spec ?? "").replace(/^ollama:/, "").replace(/^anthropic:/, "");

export const LABEL: Record<string, string> = {
  SUPPORT: "supports",
  CONTRADICT: "contradicts",
  NOT_ENOUGH_INFO: "not enough info",
};

/** "22 pairs · 19 texts to extract (3 cached) · ~25 min" */
export function describeEstimate(e?: Estimate): string {
  if (!e) return "";
  if (e.error) return e.error;
  const parts: string[] = [];
  if (e.pairs) parts.push(`${e.pairs} claim/abstract pairs`);
  if (e.extract_calls || e.cached) {
    parts.push(e.extract_calls ? `${e.extract_calls} texts to extract` : "extraction cached");
    if (e.extract_calls && e.cached) parts[parts.length - 1] += ` (${e.cached} cached)`;
  }
  if (e.seconds != null) parts.push(e.seconds ? `~${dur(e.seconds)}` : "instant");
  else if (e.unknown?.length) parts.push(`time unknown: first run of ${e.unknown.map(model).join(", ")}`);
  return parts.join(" · ");
}

/** A readable default name, e.g. "qwen3:8b · 20 SciFact dev claims · abstracts vs statements". */
export function autoName(arms: Arm[]): string {
  if (!arms.length) return "";
  const models = [...new Set(arms.flatMap((a) => [a.extractor, a.verifier]).filter(Boolean).map(model))];
  const prompts = [...new Set(arms.filter((a) => a.extractor).map((a) => a.extractor_prompt ?? "extract-v1"))];
  const parts = [models.join(" vs ")];
  if (prompts.length > 1) parts.push("prompt " + prompts.map((p) => p.replace("extract-", "")).join(" vs "));
  const data = [...new Set(arms.map((a) => describeData(a.data)))].join(" + ");
  const modes = new Set(arms.map((a) => a.mode));
  const what = modes.has("abstract") && modes.has("statements") ? "abstracts vs statements"
    : modes.has("statements") ? "statements" : modes.has("abstract") ? "abstracts" : "extraction";
  return [...parts, data, what].join(" · ");
}

/** Short result lines per canvas block (by node id) for the selected experiment. */
export function badgesFor(exp: Experiment): Record<string, string[]> {
  const out: Record<string, Set<string>> = {};
  const add = (id: string | undefined, line: string) => { if (id) (out[id] ??= new Set()).add(line); };
  for (const r of exp.results) {
    const arm = exp.arms.find((a) => a.id === r.arm);
    const s = r.summary;
    if (!arm || !s) continue;
    if (arm.extractor && s.extraction) {
      add(arm.path[1], `${s.extraction.statements} statements · ${Math.round(s.extraction.grounded_rate * 100)}% quotes found`);
    }
    if (arm.verifier && s.label) {
      // Several arms of one mode can share a verifier block: name the arm then.
      const sameMode = exp.arms.filter((a) => a.mode === arm.mode && a.verifier).length > 1;
      const where = arm.mode === "abstract" ? "on abstracts" : "on statements";
      add(arm.path[arm.path.length - 2], `${sameMode ? `${arm.id} ` : ""}${where}: macro-F1 ${s.label.macro_f1.toFixed(2)}`);
    }
  }
  const many = exp.comparisons.length > 1;
  for (const c of exp.comparisons) {
    const arm = exp.arms.find((a) => a.id === c.statements_arm);
    const loss = c.extraction_loss_macro_f1;
    const text = loss > 0 ? `extraction loses ${loss.toFixed(2)}` : loss < 0 ? `extraction gains ${(-loss).toFixed(2)}` : "no extraction loss";
    add(arm?.path[arm.path.length - 1], many ? `${c.statements_arm}: ${text}` : text);
  }
  return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, [...v]]));
}

/** Total time for the plan, or null when some model has never run on this machine. */
export function totalSeconds(estimates: Estimate[]): number | null {
  if (!estimates.length || estimates.some((e) => e.seconds == null)) return null;
  return estimates.reduce((s, e) => s + (e.seconds ?? 0), 0);
}

const dataOf = (a: Arm) => a.data;

export function describeData(d: Arm["data"]): string {
  if (d.kind === "documents") return "your dropped documents";
  return d.limit ? `${d.limit} SciFact ${d.split} claim${d.limit === 1 ? "" : "s"}` : `all SciFact ${d.split} claims`;
}

/** "prompt v2" for non-default extraction prompts, else "". */
export const promptTag = (p?: string) => (p && p !== "extract-v1" ? ` (prompt ${p.replace("extract-", "")})` : "");

export function describeArm(a: Arm): string {
  const x = model(a.extractor) + promptTag(a.extractor_prompt), v = model(a.verifier);
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
  const extractors = [...new Set(arms.filter((a) => a.extractor).map((a) => model(a.extractor) + promptTag(a.extractor_prompt)))];
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
  const armOf = (id: string) => exp.arms.find((a) => a.id === id);
  const xName = (a?: Arm) => model(a?.extractor) + promptTag(a?.extractor_prompt);
  const f = (x: number) => x.toFixed(2);

  // Extraction loss: one sentence per abstract/statements pair of arms. With several pairs,
  // each sentence names its arm and extractor so they can be told apart.
  const many = exp.comparisons.length > 1;
  for (const c of exp.comparisons) {
    const a = res(c.abstract_arm)?.label?.macro_f1, s = res(c.statements_arm)?.label?.macro_f1;
    if (a === undefined || s === undefined) continue;
    const loss = c.extraction_loss_macro_f1;
    if (!many) {
      lines.push(loss > 0
        ? `With statements only, ${model(c.verifier)} scores ${f(s)} instead of ${f(a)}: extraction by ${model(c.extractor)} loses ${f(loss)}.`
        : `With statements only, ${model(c.verifier)} scores ${f(s)}, ${s === a ? "the same as" : "better than"} on full abstracts (${f(a)}).`);
    } else {
      const who = `${c.statements_arm}, statements from ${xName(armOf(c.statements_arm))}`;
      lines.push(loss > 0 ? `${who}: ${f(s)} vs ${f(a)} on abstracts, a loss of ${f(loss)}.`
        : loss < 0 ? `${who}: ${f(s)} vs ${f(a)} on abstracts, a gain of ${f(-loss)}.`
        : `${who}: same score as on abstracts (${f(s)}).`);
    }
  }

  // Best arm per mode, or a tie.
  for (const mode of ["abstract", "statements"] as const) {
    const scored = exp.results.filter((r) => r.mode === mode && r.summary?.label);
    if (scored.length < 2) continue;
    const top = Math.max(...scored.map((r) => r.summary!.label!.macro_f1));
    const best = scored.filter((r) => Math.abs(r.summary!.label!.macro_f1 - top) < 1e-9);
    const where = mode === "abstract" ? "on abstracts" : "on statements";
    if (best.length === scored.length) {
      lines.push(`All arms ${where} tie at ${f(top)}.`);
    } else if (best.length > 1) {
      lines.push(`${best.map((r) => r.arm).join(" and ")} tie for best ${where} at ${f(top)}.`);
    } else {
      const arm = armOf(best[0].arm);
      const setup = mode === "abstract" ? model(arm?.verifier) : `${xName(arm)} → ${model(arm?.verifier)}`;
      lines.push(`Best ${where}: ${best[0].arm} (${setup}), ${f(top)}.`);
    }
  }

  // Extraction quality, per extracting arm.
  const exArms = exp.results.filter((r) => typeof r.summary?.extraction?.rationale_coverage === "number");
  for (const r of exArms) {
    const ex = r.summary!.extraction!;
    const prefix = exArms.length > 1 ? `${r.arm}, ${xName(armOf(r.arm))}: ` : "";
    if (ex.empty_documents) {
      lines.push(`${prefix}${exArms.length > 1 ? "no" : `${xName(armOf(r.arm))} returned no`} statements for ${ex.empty_documents} of ${ex.documents} texts.`);
    }
    lines.push(`${prefix}${exArms.length > 1 ? "statements quote" : "Statements quote"} ${Math.round((ex.rationale_coverage ?? 0) * 100)}% of the gold evidence; ${Math.round(ex.grounded_rate * 100)}% of quotes are found in the source.`);
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
