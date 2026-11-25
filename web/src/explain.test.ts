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
