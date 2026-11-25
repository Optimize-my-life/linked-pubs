# Experiment builder: visual pipeline UI, run on the GPU PC

Status: accepted
Date: 2026-11-25

## Context
We compare extraction and verification setups (models, with/without extraction) and want
to set experiments up without editing CLI flags. There is no AI budget: models run locally,
and the laptop is CPU-only, so runs belong on the GPU PC (RTX 4080 Super).

## Decision
- A visual pipeline builder: blocks (SciFact dataset, documents, extractor, verifier,
  metrics) dragged onto a canvas and connected. Each path data → … → metrics is one arm;
  several model blocks on one dataset compare models; an abstract path and a statements
  path with the same verifier give the extraction loss. PDFs are dropped onto the canvas.
- Frontend React + TypeScript (Vite) with React Flow (`@xyflow/react`); backend FastAPI,
  one process. This confirms the UI/API part of `2026-11-25-stack.md`; the database and
  worker-queue parts are still open (experiments are JSON files, one runner thread).
- The whole app runs on the GPU PC, bound to 127.0.0.1 with no login; the laptop reaches it
  through an SSH tunnel. Long runs keep going when the laptop sleeps.
- Paid APIs are rejected unless the server is started with `LINKED_PUBS_ALLOW_PAID=1`.

## Alternatives
- Form with dropdowns: quicker to build, but comparing many model combinations means many
  forms; the graph shows the experiment design directly.
- App on the laptop, only model calls through the tunnel: the laptop must stay awake.
- Node-RED / generic workflow tools: another runtime to install, and they don't know our
  arms, caching or metrics.
