# Evaluation plan

Goal: validate AI-based factual statement extraction and resolution, and compare
models/approaches (frontier APIs, local open models, fine-tuned small models, non-LLM
baselines such as NLI cross-encoders and MiniCheck). Application field: human
nutrition (see `decisions/2026-11-25-domain-nutrition-optimisation.md`).

State of research (checked 2026-11-25): there is **no gold benchmark for exhaustive
atomic claim extraction from scientific text** (PaperTrail, arXiv 2602.21045), and no
dataset pairing diet claims with nutrition-science verdicts. Both gaps are possible
thesis contributions.

## Layers
1. **Extraction**
   - Numeric statements: precision/recall of (nutrient, value, unit, population,
     value type AR/PRI/AI/UL) tuples extracted from reference-value PDFs, scored
     against the published tables (US DRIs / NASEM, EFSA DRVs, D-A-CH/DGE).
     EFSA DRV Finder export format unconfirmed: check terms of use before scraping.
   - Effect/recommendation statements: Claimify criteria (entailment, coverage,
     decontextualization; Metropolitansky & Larson, ACL 2025) on our own gold set
     (30–50 documents, two annotators, report agreement).
2. **Grounding**: is each statement supported by its evidence quote? MiniCheck /
   Bespoke-MiniCheck-7B (LLM-AggreFact) or an LLM judge.
3. **Resolution**
   - Verification: SciFact, SciFact-Open, HealthVer, FoodVitals (CIKM '26).
   - Linking/contradictions: own gold set; BioDivergence (2026) for hidden
     contradictions.
4. **Downstream solvability**: see the open question below.

Report every model × layer, plus cost and runtime.

## Milestone 1: SciFact
First benchmark to build against: small, standard, covers extract → link → verify.
- Use the dev split (300 claims, 340 claim-abstract pairs: 138 SUPPORT, 71 CONTRADICT,
  131 NOT_ENOUGH_INFO) with the **corrected labels** from the BioNLP 2026 audit
  (aclanthology.org/2026.bionlp-1.9); corrections not applied yet. The test split has no
  public labels.
- SciFact-Open (~500K abstracts) for retrieval at scale.
- Metrics: label F1 and rationale F1, comparable with published work.
- **Extraction-loss test**: verify claims against (a) raw abstracts and (b) only our
  extracted statements. The drop from (a) to (b) measures what extraction loses or
  distorts. Rationale sentences give a partial coverage check.
- Limits: abstracts only (no PDFs/tables), biomedical not nutrition, no numeric
  constraints, refuted claims are annotator-negated (wording artifacts), possible
  training-data contamination for frontier models. So also report HealthVer.
- Checked against the downloaded release: 5,183 abstracts; 809 train / 300 dev / 300 test claims.
- Implemented (milestone 1): `linked-pubs scifact-eval`, oracle-abstract setting (claims judged
  against the abstracts they cite; retrieval not tested yet). Reports label macro-F1, rationale
  F1, grounded rate, rationale coverage and the extraction loss (macro-F1 abstract − statements).

## Open: what "solvability" means (next session)
Agreed so far:
- Feasibility of the optimisation model built from extracted facts, per person or
  population (solvability rate, gap to a gold-constraint model).
- Infeasible models: the solver's irreducible infeasible subset (IIS) traces back to
  the conflicting source statements, so it doubles as a contradiction detector.
Still to define: the optimisation approaches themselves. They must scale to n users,
so **time per solution** has to be small; solvability includes solve time, not only
feasibility.

## Sources
- PaperTrail: arxiv.org/abs/2602.21045
- Claimify: aclanthology.org/2025.acl-long.348
- SciFact label audit: aclanthology.org/2026.bionlp-1.9
- Small LLMs for biomedical claim verification: aclanthology.org/2026.bionlp-1.57
- Hybrid retrieval/NLI/open LLMs on SciFact+CliniFact: arxiv.org/abs/2611.03093
- MiniCheck / LLM-AggreFact: arxiv.org/abs/2404.10774, llm-aggrefact.github.io
- FoodVitals: doi.org/10.1145/3799682.3840204
- BioDivergence: arxiv.org/abs/2606.11208
- GLEN-Bench, NGQA (ACL 2025), NutriBench (arXiv 2407.12843), Swiss Food KG
  (arXiv 2507.10156): structured nutrition resources

## Results

- 2026-11-25, first baseline, free local run: `ollama:qwen3:8b` (thinking off) for extraction
  and verification, SciFact dev, first 20 claims = 22 claim/abstract pairs (19 abstracts).
  Too small for conclusions; a pipeline check.
  - Against raw abstracts: macro-F1 0.80, accuracy 0.82, rationale F1 0.59.
  - Against extracted statements only: macro-F1 0.61, accuracy 0.64, rationale F1 0.67.
  - Extraction loss: about 0.19 macro-F1. 116 statements, 97% with the quote found in the
    source; they cover 86% of the gold evidence sentences.
  - With statements only, the losses are SUPPORT/CONTRADICT pairs that turn into NEI (5 of 22):
    the statements lose detail the verdict needs, even when they cover the right sentence.
  - Run folder: `data/runs/20261125-144054-scifact-dev/` (local, not committed).
