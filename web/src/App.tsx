import {
  addEdge, Background, Controls, MarkerType, MiniMap, ReactFlow, ReactFlowProvider, useEdgesState,
  useNodesState, useReactFlow, type Connection, type Edge, type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { api, type Compiled, type Experiment, type ExperimentSummary, type GraphJSON, type Health, type ModelInfo, type PromptInfo } from "./api";
import { ALLOWED, BLOCKS, ModelsContext, nodeTypes, useUpload, type BlockType } from "./nodes";
import { autoName, badgesFor, describeArm, describeEstimate, describePlan, describeProgress, dur, totalSeconds } from "./explain";
import { Leaderboard } from "./Leaderboard";
import { Results } from "./Results";

const STORAGE_KEY = "linked-pubs:graph";
const DRAG_TYPE = "application/x-linked-pubs-block";
const PREFERRED = ["ollama:qwen3:14b", "ollama:qwen3:8b"];

let counter = 0;
const newId = (type: string) => `${type}-${Date.now().toString(36)}${(counter++).toString(36)}`;

function baseline(model: string): { nodes: Node[]; edges: Edge[] } {
  // The milestone-1 experiment: verify against abstracts and against extracted statements,
  // with the same verifier, so the difference is the extraction loss.
  const nodes: Node[] = [
    { id: "dataset-1", type: "dataset", position: { x: 0, y: 120 }, data: { split: "dev", limit: 20 } },
    { id: "extractor-1", type: "extractor", position: { x: 280, y: 250 }, data: { model } },
    { id: "verifier-1", type: "verifier", position: { x: 560, y: 120 }, data: { model } },
    { id: "metrics-1", type: "metrics", position: { x: 840, y: 130 }, data: {} },
  ];
  const edges: Edge[] = [
    ["dataset-1", "verifier-1"], ["dataset-1", "extractor-1"], ["extractor-1", "verifier-1"], ["verifier-1", "metrics-1"],
  ].map(([source, target]) => ({ id: `${source}->${target}`, source, target }));
  return { nodes, edges };
}

function toGraph(nodes: Node[], edges: Edge[]): GraphJSON {
  return {
    nodes: nodes.map((n) => ({
      id: n.id, type: n.type ?? "", position: n.position,
      data: Object.fromEntries(Object.entries(n.data).filter(([k]) => !k.startsWith("_"))),
    })),
    edges: edges.map((e) => ({ source: e.source, target: e.target })),
  };
}

function fromGraph(g: GraphJSON): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: g.nodes.map((n, i) => ({
      id: n.id, type: n.type, data: n.data,
      position: n.position ?? { x: 260 * i, y: 120 },
    })),
    edges: g.edges.map((e) => ({ id: `${e.source}->${e.target}`, source: e.source, target: e.target })),
  };
}

function loadSaved(): { nodes: Node[]; edges: Edge[] } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? fromGraph(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

function Builder() {
  const rf = useReactFlow();
  const upload = useUpload();
  const initial = useMemo(() => loadSaved() ?? baseline(""), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [prompts, setPrompts] = useState<PromptInfo[]>([]);
  useEffect(() => { api.prompts().then(setPrompts).catch(() => undefined); }, []);
  const [health, setHealth] = useState<Health | null>(null);
  const [compiled, setCompiled] = useState<Compiled>({ arms: [], errors: [] });
  const [name, setName] = useState("");
  const [tab, setTab] = useState<"plan" | "runs" | "compare">("plan");
  const [runs, setRuns] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [submitError, setSubmitError] = useState("");
  const filledDefaults = useRef(false);

  const defaultModel = useMemo(() => {
    const free = models.filter((m) => m.free);
    return PREFERRED.find((p) => free.some((m) => m.spec === p)) ?? free[free.length - 1]?.spec ?? "";
  }, [models]);

  const refreshModels = useCallback(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.models().then(setModels).catch(() => setModels([])).finally(() => setModelsLoaded(true));
  }, []);
  useEffect(refreshModels, [refreshModels]);
  const ollamaUp = !!health?.ollama_version;
  useEffect(() => {
    if (ollamaUp) return;
    const t = setInterval(refreshModels, 15000);
    return () => clearInterval(t);
  }, [ollamaUp, refreshModels]);

  // Fill empty model fields once the model list is known.
  useEffect(() => {
    if (!defaultModel || filledDefaults.current) return;
    filledDefaults.current = true;
    setNodes((ns) => ns.map((n) =>
      (n.type === "extractor" || n.type === "verifier") && !n.data.model ? { ...n, data: { ...n.data, model: defaultModel } } : n));
  }, [defaultModel, setNodes]);

  const graph = useMemo(() => toGraph(nodes, edges), [nodes, edges]);
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(graph));
    const t = setTimeout(() => api.compile(graph).then(setCompiled).catch((e) => setCompiled({ arms: [], errors: [e.message] })), 250);
    return () => clearTimeout(t);
  }, [graph]);

  // Poll the experiment list, and the selected experiment while it runs.
  const selectedId = selected?.id;
  const selectedActive = selected?.status === "queued" || selected?.status === "running";
  useEffect(() => {
    const tick = () => {
      api.experiments().then(setRuns).catch(() => undefined);
      if (selectedId && selectedActive) api.experiment(selectedId).then(setSelected).catch(() => undefined);
    };
    tick();
    const t = setInterval(tick, 2500);
    return () => clearInterval(t);
  }, [selectedId, selectedActive]);

  const autoSelected = useRef(false);
  useEffect(() => {
    if (autoSelected.current || selected || !runs.length) return;
    autoSelected.current = true;
    api.experiment(runs[0].id).then(setSelected).catch(() => undefined);
  }, [runs, selected]);

  const addBlock = useCallback((type: BlockType, position?: { x: number; y: number }) => {
    const id = newId(type);
    const data = { ...BLOCKS[type].defaults };
    if ((type === "extractor" || type === "verifier") && defaultModel) data.model = defaultModel;
    const pos = position ?? rf.screenToFlowPosition({ x: window.innerWidth / 2 - 150, y: window.innerHeight / 2 });
    setNodes((ns) => [...ns, { id, type, position: pos, data }]);
    return id;
  }, [defaultModel, rf, setNodes]);

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    const position = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const type = e.dataTransfer.getData(DRAG_TYPE) as BlockType;
    if (type) {
      addBlock(type, position);
    } else if (e.dataTransfer.files.length) {
      // PDFs dropped on the empty canvas become a new documents block.
      const files = Array.from(e.dataTransfer.files);
      const id = addBlock("documents", position);
      setTimeout(() => upload(id, files), 0);
    }
  }, [addBlock, rf, upload]);

  const isValidConnection = useCallback((c: Connection | Edge) => {
    const s = rf.getNode(c.source)?.type as BlockType | undefined;
    const t = rf.getNode(c.target)?.type as BlockType | undefined;
    return !!s && !!t && c.source !== c.target && ALLOWED[s].includes(t);
  }, [rf]);

  const onConnect = useCallback((c: Connection) => setEdges((es) => addEdge(c, es)), [setEdges]);

  const run = async () => {
    setSubmitError("");
    try {
      const exp = await api.submit(name.trim() || autoName(compiled.arms), graph);
      setSelected(exp);
      setTab("runs");
      api.experiments().then(setRuns);
    } catch (e) {
      setSubmitError((e as Error).message);
    }
  };

  const loadGraph = (exp: Experiment) => {
    const g = fromGraph(exp.graph);
    setNodes(g.nodes);
    setEdges(g.edges);
    setName(`${exp.name} (copy)`);
    setTab("plan");
    setTimeout(() => rf.fitView({ padding: 0.2 }), 50);
  };

  const reset = () => {
    const g = baseline(defaultModel);
    setNodes(g.nodes);
    setEdges(g.edges);
    setTimeout(() => rf.fitView({ padding: 0.2 }), 50);
  };

  const freeCount = models.filter((m) => m.free).length;
  const active = runs.find((r) => r.status === "running");
  const queued = runs.filter((r) => r.status === "queued").length;
  const queuedAhead = queued + (active ? 1 : 0);
  const plan = describePlan(compiled.arms);

  // Re-render every few seconds so the time-left estimate stays current.
  const [, setClock] = useState(0);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setClock((c) => c + 1), 5000);
    return () => clearInterval(t);
  }, [active]);

  // Show on the canvas which block is working: highlight it and animate its path.
  const activeNode = active?.progress?.active_node;
  const activePath = active?.progress?.path ?? [];
  const badges = useMemo(() => (selected ? badgesFor(selected) : {}), [selected]);
  const viewNodes = useMemo(() => nodes.map((n) => {
    const b = badges[n.id];
    const withBadge = b ? { ...n, data: { ...n.data, _badges: b } } : n;
    return n.id === activeNode ? { ...withBadge, className: "running" } : withBadge;
  }), [nodes, activeNode, badges]);
  const viewEdges = useMemo(() => edges.map((e) => {
    const i = activePath.indexOf(e.source);
    return i >= 0 && activePath[i + 1] === e.target ? { ...e, animated: true } : e;
  }), [edges, activePath]);

  return (
    <ModelsContext.Provider value={{ models, defaultModel, prompts }}>
      <div className="app">
        <header>
          <div className="brand">linked-pubs <span>experiment builder</span></div>
          <div className={`now ${active ? "busy" : ""}`} onClick={() => active && api.experiment(active.id).then((e) => { setSelected(e); setTab("runs"); })}>
            {active
              ? <>▶ <b>{active.name}</b>: {describeProgress(active.progress)}{queued ? ` · ${queued} queued` : ""}</>
              : "Idle: build an experiment and press Run."}
          </div>
          <div className="health">
            {health?.ollama_version
              ? <span className="ok">Ollama {health.ollama_version} · {freeCount} model{freeCount === 1 ? "" : "s"}</span>
              : <span className="bad">Ollama not reachable{health ? ` at ${health.ollama_host}` : ""}</span>}
            {health && !health.scifact && <span className="bad">SciFact missing: run linked-pubs scifact-download</span>}
            {health?.allow_paid && <span className="warn">paid APIs enabled</span>}
            <button onClick={refreshModels}>Refresh models</button>
          </div>
        </header>

        <aside className="palette">
          <div className="section-title">Blocks</div>
          {(Object.keys(BLOCKS) as BlockType[]).map((type) => (
            <div key={type} className={`palette-item block-${type}`} draggable
              onDragStart={(e) => { e.dataTransfer.setData(DRAG_TYPE, type); e.dataTransfer.effectAllowed = "move"; }}
              onDoubleClick={() => addBlock(type)} title="drag onto the canvas (or double-click)">
              <b>{BLOCKS[type].title}</b>
              <span>{BLOCKS[type].hint}</span>
            </div>
          ))}
          <div className="help">
            <p>Drag blocks in, connect left → right. Each path to Metrics is one arm.</p>
            <p>Drop PDFs on the canvas to extract from them. Delete removes a selected block.</p>
          </div>
          <button onClick={reset}>Reset to baseline</button>
        </aside>

        <main onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }} onDrop={onDrop}>
          <ReactFlow nodes={viewNodes} edges={viewEdges} colorMode="system" nodeTypes={nodeTypes} onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange} onConnect={onConnect} isValidConnection={isValidConnection}
            defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }} fitView deleteKeyCode={["Delete", "Backspace"]}>
            <Background gap={20} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </main>

        <aside className="panel">
          <div className="tabs">
            <button className={tab === "plan" ? "active" : ""} onClick={() => setTab("plan")}>Plan</button>
            <button className={tab === "runs" ? "active" : ""} onClick={() => setTab("runs")}>Runs ({runs.length})</button>
            <button className={tab === "compare" ? "active" : ""} onClick={() => setTab("compare")}
              title="All finished arms side by side">Compare</button>
          </div>

          {tab === "plan" && (
            <div className="plan">
              <label className="stack">
                Experiment name
                <input value={name} placeholder={autoName(compiled.arms) || "e.g. qwen3 8b vs 14b"}
                  onChange={(e) => setName(e.target.value)} />
              </label>
              {plan.headline && <div className="plan-headline">{plan.headline}</div>}
              {compiled.arms.map((a) => (
                <div key={a.id} className="arm">
                  <b>{a.id}</b> {describeArm(a)}
                  <div className="muted small">{describeEstimate(compiled.estimates?.find((e) => e.arm === a.id))}</div>
                </div>
              ))}
              {plan.notes.map((n, i) => <div key={i} className="note small">{n}</div>)}
              {compiled.arms.length > 0 && !compiled.errors.length && (
                <div className="small">
                  {(() => {
                    const t = totalSeconds(compiled.estimates ?? []);
                    return t === null
                      ? "Total time: known after each model has run once on this machine."
                      : `Total: ~${dur(t)}${queuedAhead ? ` after ${queuedAhead} queued/running experiment(s)` : ""}.`;
                  })()}
                </div>
              )}
              {!modelsLoaded
                ? <div className="muted small">Loading models from Ollama…</div>
                : compiled.errors.map((e, i) => <div key={i} className="error small">{e}</div>)}
              <button className="primary" disabled={!compiled.arms.length || compiled.errors.length > 0} onClick={run}>
                ▶ Run experiment
              </button>
              {submitError && <div className="error small">{submitError}</div>}
              <div className="muted small">One experiment runs at a time. Extractions already done are reused.</div>
            </div>
          )}

          {tab === "runs" && (
            <div className="runs">
              {runs.length === 0 && <div className="muted small">No experiments yet.</div>}
              {runs.map((r) => (
                <div key={r.id} className={`run ${selected?.id === r.id ? "active" : ""}`}
                  onClick={() => api.experiment(r.id).then(setSelected)}>
                  <div className="row between">
                    <b className="ellipsis">{r.name}</b>
                    <span className={`status status-${r.status}`}>{r.status}</span>
                  </div>
                  <div className="muted small">
                    {new Date(r.created_at).toLocaleString()} · {r.arms} arm(s)
                    {r.progress ? ` · ${describeProgress(r.progress)}` : ""}
                  </div>
                </div>
              ))}
              {selected && <Results exp={selected} onLoadGraph={() => loadGraph(selected)} />}
            </div>
          )}

          {tab === "compare" && (
            <Leaderboard onOpen={(id) => api.experiment(id).then((e) => { setSelected(e); setTab("runs"); })} />
          )}
        </aside>
      </div>
    </ModelsContext.Provider>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Builder />
    </ReactFlowProvider>
  );
}
