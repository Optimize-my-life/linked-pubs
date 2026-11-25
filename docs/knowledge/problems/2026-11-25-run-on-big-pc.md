# Run the experiment builder on the GPU PC

Status: open
Who: mick + Claude
Opened: 2026-11-25

## Problem
Experiments should run on the big PC (RTX 4080 Super, 16 GB VRAM, larger models), not the
laptop (CPU only, ~4 min per abstract with qwen3:8b). The whole app runs there; the laptop
only opens the UI through an SSH tunnel. Not set up yet: how the PC is reached (ssh alias),
its OS, and whether Ollama runs there.

## Notes
- 2026-11-25: plan. On the big PC: clone repo, `py -3.11 -m venv .venv`, `pip install -e .`,
  `linked-pubs scifact-download`, Ollama with models pulled, `npm ci && npm run build` in
  `web/`, then `linked-pubs serve` (binds 127.0.0.1:8000, no login). From the laptop:
  `ssh -L 8000:127.0.0.1:8000 <alias>` and open http://localhost:8000. Connection details
  stay in the ssh config, not in this repo.
- 2026-11-25: models worth trying on 16 GB VRAM: qwen3:14b (~9 GB), gemma4:12b (~8 GB);
  bigger ones (~20 GB+) spill into system RAM and get much slower.
- 2026-11-25: `scripts/setup.ps1` (Windows) and `scripts/setup.sh` (Linux) do the whole setup
  and print the start and tunnel commands. Still needed from mick: OS of the big PC, ssh alias.
- 2026-11-25: if Ollama on the big PC has OLLAMA_HOST=0.0.0.0 (so other PCs can reach it), the
  app still connects via 127.0.0.1 (normalised in `ollama_base_url()`).
- 2026-11-25: `scripts/start.ps1` / `stop.ps1` (`start.sh` on Linux) run the server in the
  background so it survives the SSH session; tested on the laptop. A lock refuses a second
  server on the same data folder (it would mark running experiments as interrupted).

## Fix
