// Run: npm test   (Node's built-in test runner; strips the TypeScript types)
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Arm, Experiment } from "./api.ts";
import { autoName, badgesFor, describeEstimate, describePlan, describeProgress, describeResults, totalSeconds } from "./explain.ts";

const data = { kind: "scifact" as const, split: "dev", limit: 20, docset_id: null };
const A: Arm = { id: "arm1", mode: "abstract", data, extractor: null, verifier: "ollama:qwen3:8b", path: ["d", "v", "m"] };
const S: Arm = { id: "arm2", mode: "statements", data, extractor: "ollama:qwen3:8b", verifier: "ollama:qwen3:8b",
  path: ["d", "x", "v", "m"] };

test("plan names the comparison it sets up", () => {
  const p = describePlan([A, S]);
  assert.equal(p.headline, "Runs 2 arms on 20 SciFact dev claims.");
  assert.deepEqual(p.notes, ["arm1 vs arm2 shows what extraction loses."]);
  assert.equal(autoName([A, S]), "qwen3:8b · 20 SciFact dev claims · abstracts vs statements");
});

test("progress says what runs, where, and how long is left", () => {
  const now = 1000;
  const text = describeProgress({ arm: "arm2", arm_index: 2, arms: 2, mode: "statements", step: "extract", done: 5,
    total: 15, model: "ollama:qwen3:14b", active_node: "x", path: [], step_started: now - 5 * 60 }, now);
  assert.equal(text, "arm 2 of 2 · Extracting statements with qwen3:14b · text 6 of 15 · ~10 min left");
});

test("estimate and total time", () => {
  assert.equal(describeEstimate({ arm: "arm2", pairs: 22, extract_calls: 3, cached: 16, verify_calls: 22, seconds: 1500, unknown: [] }),
    "22 claim/abstract pairs · 3 texts to extract (16 cached) · ~25 min");
  assert.equal(describeEstimate({ arm: "arm1", pairs: 22, verify_calls: 22, seconds: null, unknown: ["ollama:gemma4:12b"] }),
    "22 claim/abstract pairs · time unknown: first run of gemma4:12b");
  assert.equal(totalSeconds([{ arm: "a", seconds: 60 }, { arm: "b", seconds: 30 }]), 90);
  assert.equal(totalSeconds([{ arm: "a", seconds: 60 }, { arm: "b", seconds: null }]), null);
});

const exp: Experiment = {
  id: "e1", name: "x", status: "done", created_at: "2026-11-25T00:00:00Z", graph: { nodes: [], edges: [] },
  arms: [A, S], progress: null, error: null,
  results: [
    { arm: "arm1", label: "", mode: "abstract", seconds: 540, error: null,
      summary: { pairs: 22, errors: 0, label: { accuracy: 0.82, macro_f1: 0.8, per_class: {} } } },
    { arm: "arm2", label: "", mode: "statements", seconds: 420, error: null,
      summary: { pairs: 22, errors: 0, label: { accuracy: 0.64, macro_f1: 0.61, per_class: {} },
        extraction: { documents: 19, empty_documents: 2, statements: 116, grounded_rate: 0.97, rationale_coverage: 0.86 } } },
  ],
  comparisons: [{ abstract_arm: "arm1", statements_arm: "arm2", verifier: "ollama:qwen3:8b", extractor: "ollama:qwen3:8b",
    extraction_loss_macro_f1: 0.19 }],
};

test("results read as plain verdicts", () => {
  assert.deepEqual(describeResults(exp), [
    "With statements only, qwen3:8b scores 0.61 instead of 0.80: extraction by qwen3:8b loses 0.19.",
    "qwen3:8b returned no statements for 2 of 19 texts.",
    "Statements quote 86% of the gold evidence; 97% of quotes are found in the source.",
    "Only 22 pairs: differences below ~0.1 can be chance.",
  ]);
});

test("badges land on the blocks that produced them", () => {
  assert.deepEqual(badgesFor(exp), {
    v: ["on abstracts: macro-F1 0.80", "on statements: macro-F1 0.61"],
    x: ["116 statements · 97% quotes found"],
    m: ["extraction loses 0.19"],
  });
});

test("several extractors: verdicts name their arm and prompt, ties are called ties", () => {
  const S2: Arm = { ...S, id: "arm3", extractor_prompt: "extract-v2", path: ["d", "x2", "v", "m"] };
  const label = { accuracy: 0.67, macro_f1: 0.27, per_class: {} };
  const ext = { documents: 3, empty_documents: 0, statements: 22, grounded_rate: 1, rationale_coverage: 1 };
  const e: Experiment = { ...exp, arms: [A, S, S2],
    results: [
      { arm: "arm1", label: "", mode: "abstract", seconds: 1, error: null, summary: { pairs: 3, label } },
      { arm: "arm2", label: "", mode: "statements", seconds: 1, error: null, summary: { pairs: 3, label, extraction: ext } },
      { arm: "arm3", label: "", mode: "statements", seconds: 1, error: null, summary: { pairs: 3, label, extraction: { ...ext, grounded_rate: 0.95 } } },
    ],
    comparisons: [
      { abstract_arm: "arm1", statements_arm: "arm2", verifier: "ollama:qwen3:8b", extractor: "ollama:qwen3:8b", extraction_loss_macro_f1: 0 },
      { abstract_arm: "arm1", statements_arm: "arm3", verifier: "ollama:qwen3:8b", extractor: "ollama:qwen3:8b", extraction_loss_macro_f1: 0 },
    ] };
  assert.deepEqual(describeResults(e), [
    "arm2, statements from qwen3:8b: same score as on abstracts (0.27).",
    "arm3, statements from qwen3:8b (prompt v2): same score as on abstracts (0.27).",
    "All arms on statements tie at 0.27.",
    "arm2, qwen3:8b: statements quote 100% of the gold evidence; 100% of quotes are found in the source.",
    "arm3, qwen3:8b (prompt v2): statements quote 100% of the gold evidence; 95% of quotes are found in the source.",
    "Only 3 pairs: differences below ~0.1 can be chance.",
  ]);
  const b = badgesFor(e);
  assert.deepEqual(b.v, ["on abstracts: macro-F1 0.27", "arm2 on statements: macro-F1 0.27", "arm3 on statements: macro-F1 0.27"]);
  assert.deepEqual(b.m, ["arm2: no extraction loss", "arm3: no extraction loss"]);
});

test("many arms: plan stays short and names the automatic baselines", async () => {
  const xs: Arm[] = ["a", "b", "c"].map((m, i) => ({ ...S, id: `arm${i + 1}`, extractor: `ollama:${m}` }));
  const base: Arm = { ...A, id: "arm4", auto: true };
  const p = describePlan([...xs, base]);
  assert.deepEqual(p.notes.slice(0, 2), [
    "Each of the 3 statements arms is compared with its abstract baseline: that difference is what extraction loses.",
    "arm4 was added automatically, so every extractor gets its loss measured.",
  ]);
  const { describeArm, promptTag } = await import("./explain.ts");
  assert.match(describeArm(base), /Added automatically/);
  assert.equal(promptTag("verify-strict"), " (prompt strict)");
  assert.equal(promptTag("verify-v1"), "");
});

test("quick comparison graph: arm count matches the shape", async () => {
  const { comparisonGraph, quickArmCount } = await import("./templates.ts");
  const q = { models: ["ollama:a", "ollama:b"], role: "both" as const, fixed: "ollama:a", prompts: ["extract-v1"], split: "dev", limit: 5 };
  const g = comparisonGraph(q);
  assert.equal(g.nodes.filter((n) => n.type === "extractor").length, 2);
  assert.equal(quickArmCount(q), 4);
  const e = comparisonGraph({ ...q, role: "extractor", prompts: ["extract-v1", "extract-v2"] });
  assert.deepEqual(e.nodes.find((n) => n.type === "extractor")?.data.models, ["ollama:a", "ollama:b"]);
  assert.equal(quickArmCount({ ...q, role: "extractor", prompts: ["extract-v1", "extract-v2"] }), 5);
});

test("prompt diff shows added and removed words", async () => {
  const { diffWords, describeDiff } = await import("./diff.ts");
  const d = diffWords("Keep the numbers exactly.", "Keep all numbers and CIs exactly.");
  assert.deepEqual(d.filter((x) => x.op !== "same").map((x) => [x.op, x.text.trim()]),
    [["add", "all"], ["del", "the"], ["add", "and CIs"]]);
  assert.equal(d.map((x) => (x.op === "del" ? "" : x.text)).join(""), "Keep all numbers and CIs exactly.");
  assert.equal(d.map((x) => (x.op === "add" ? "" : x.text)).join(""), "Keep the numbers exactly.");
  assert.equal(describeDiff(d), "adds 3 words, removes 1");
});
