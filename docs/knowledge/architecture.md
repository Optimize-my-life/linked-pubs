# Architecture

```
PDFs ──► Ingest ──► Chunks ──► Extractor(s) ──► Statements ──► Linker(s) ──► Fact graph
                                                    │                          │
                                     new statement ─┴──► Verifier(s) ◄─────────┘
                                                          └─► verdict + citations
```

## Pipeline
1. **Ingest**: deduplicate by file hash, parse PDF (parser plugin) into sections and
   paragraphs with page numbers and character offsets; store metadata (title, DOI, type:
   paper / guideline).
2. **Extract** (`Extractor` plugin): chunk → list of statements. Each statement has
   the claim text, optional structure (subject, relation, object, qualifiers such as
   population, conditions, units), evidence quote, page, confidence.
   Guard: the evidence quote must be found in the source text, otherwise reject (catches
   hallucinated facts).
3. **Embed**: embedding per statement (embedder plugin) into pgvector.
4. **Link** (`Resolver` plugin, corpus mode): for each statement, retrieve candidates
   (vector + keyword search), then classify pairs: equivalent / entails / contradicts /
   related / unrelated. Equivalent statements form clusters ("facts"); other labels are
   edges.
5. **Verify** (`Resolver` plugin, query mode): the same retrieve + classify for a user
   statement, then aggregate into supported / contradicted / not enough info, with the
   evidence statements and their source quotes.

## Statement types (nutrition)
Statements feed optimisation models, so they are typed:
| Type | Example | Use in model |
|---|---|---|
| reference value | PRI iron 16 mg/day, women 19–50 | lower bound (value, unit, population, AR/PRI/AI/UL) |
| upper limit | UL vitamin D 100 µg/day, adults | upper bound |
| effect | +10 g fibre/day → −x % CVD risk | objective coefficient / soft constraint (+ study design, evidence grade) |
| recommendation | free sugars < 10 % of energy | (soft) constraint |
| food composition | 100 g lentils: 7.5 mg iron | model matrix (prefer databases over PDFs) |

## Plugin interfaces (sketch)
- `Parser.parse(pdf) -> Document`
- `Extractor.extract(chunk, context) -> list[Statement]`
- `Embedder.embed(texts) -> vectors`
- `Resolver.classify(pairs) -> list[Relation]`, with implementations such as
  embedding threshold, NLI cross-encoder, LLM judge (any LLM provider).
- `LLMProvider.complete(prompt, schema)`: Claude API, OpenAI-compatible local endpoint.

Every run stores plugin name, version, model, prompt hash and config (`runs` table), and
every statement/relation points to its run.

## Data model (core tables)
`sources`, `chunks`, `runs`, `statements`, `facts` (clusters), `relations`
(statement–statement edges with label and score), `verifications`, `annotations`
(human labels for evaluation).

## Web UI
Sources (upload, status of processing), statement browser per source with highlighted
evidence, fact graph view, "check a statement" page, and a review/annotation view that
produces gold data for evaluating extractors and resolvers.
