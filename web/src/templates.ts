// Builds a ready-to-run canvas for comparing several models, so nobody has to wire it by hand.
import type { GraphJSON } from "./api.ts";

/** What the compared models do:
 * extractor: each model extracts statements, one fixed judge scores them all.
 * verifier:  each model judges claims (on abstracts and on one fixed extractor's statements).
 * both:      each model extracts and then judges its own statements (end to end). */
export type Role = "extractor" | "verifier" | "both";

export type QuickSpec = {
  models: string[]; role: Role; fixed: string; prompts: string[]; split: string; limit: number;
};

export function comparisonGraph(q: QuickSpec): GraphJSON {
  const nodes: GraphJSON["nodes"] = [
    { id: "dataset-1", type: "dataset", position: { x: 0, y: 160 }, data: { split: q.split, limit: q.limit } },
  ];
  const edges: GraphJSON["edges"] = [];
  const link = (source: string, target: string) => edges.push({ source, target });
  const metricsY = 160;
  if (q.role === "both") {
    q.models.forEach((m, i) => {
      const y = i * 190;
      nodes.push({ id: `extractor-${i + 1}`, type: "extractor", position: { x: 300, y }, data: { models: [m], prompts: q.prompts } });
      nodes.push({ id: `verifier-${i + 1}`, type: "verifier", position: { x: 600, y }, data: { models: [m], prompts: ["verify-v1"] } });
      link("dataset-1", `extractor-${i + 1}`);
      link(`extractor-${i + 1}`, `verifier-${i + 1}`);
      link(`verifier-${i + 1}`, "metrics-1");
    });
    nodes.push({ id: "metrics-1", type: "metrics", position: { x: 900, y: ((q.models.length - 1) * 190) / 2 }, data: {} });
    return { nodes, edges };
  }
  const extractors = q.role === "extractor" ? q.models : [q.fixed];
  const verifiers = q.role === "verifier" ? q.models : [q.fixed];
  nodes.push({ id: "extractor-1", type: "extractor", position: { x: 300, y: 300 }, data: { models: extractors, prompts: q.prompts } });
  nodes.push({ id: "verifier-1", type: "verifier", position: { x: 600, y: 140 }, data: { models: verifiers, prompts: ["verify-v1"] } });
  nodes.push({ id: "metrics-1", type: "metrics", position: { x: 900, y: metricsY }, data: {} });
  link("dataset-1", "extractor-1");
  link("extractor-1", "verifier-1");
  link("verifier-1", "metrics-1");
  return { nodes, edges };
}

/** Arms the quick comparison will create, for the button label ("Build 6 arms"). */
export function quickArmCount(q: QuickSpec): number {
  const p = Math.max(1, q.prompts.length), n = q.models.length;
  if (!n) return 0;
  if (q.role === "both") return n * p + n;          // statements arms + one baseline per judge
  if (q.role === "extractor") return n * p + 1;     // + one baseline for the fixed judge
  return n * p + n;                                 // each judge: statements arms + baseline
}
