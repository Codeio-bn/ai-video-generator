import { useEffect, useState } from "react";
import { api } from "../api";
import type { CostStatus, Episode, Job, Project, SystemStatus } from "../types";
import { Banner, ProviderPicker, useInterval } from "./common";

export function ProjectView({
  projectId, onOpenEpisode, onBack,
}: {
  projectId: number;
  onOpenEpisode: (eid: number) => void;
  onBack: () => void;
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [saved, setSaved] = useState(false);
  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [cost, setCost] = useState<CostStatus | null>(null);

  const loadEpisodes = () => api.listEpisodes(projectId).then(setEpisodes);
  const loadCost = () => api.projectCost(projectId).then(setCost).catch(() => setCost(null));
  const load = () => {
    api.getProject(projectId).then(setProject);
    loadEpisodes();
    loadCost();
  };
  const loadSys = () => api.system().then(setSys).catch(() => setSys(null));
  useEffect(load, [projectId]);
  useEffect(() => { loadSys(); }, []);

  if (!project) return <div className="container">Loading…</div>;
  const set = (k: keyof Project, v: string | number) =>
    setProject({ ...project, [k]: v });

  const save = async () => {
    await api.updateProject(projectId, project);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const addEpisode = async () => {
    const part = episodes.length + 1;
    const ep = await api.createEpisode(projectId, {
      part_number: part, title: `Part ${part}`,
    });
    onOpenEpisode(ep.id);
  };

  return (
    <div className="container">
      <div className="crumbs"><a onClick={onBack}>Projects</a> / {project.scp_number}</div>
      <h1>{project.title || project.scp_number}</h1>

      <AutoGenPanel
        project={project}
        episodeCount={episodes.length}
        sys={sys}
        onProviderChange={loadSys}
        onDone={load}
      />

      <div className="panel">
        <h3>Project metadata & attribution</h3>
        <div className="grid-2">
          <div className="field"><label>SCP number</label>
            <input value={project.scp_number} onChange={(e) => set("scp_number", e.target.value)} /></div>
          <div className="field"><label>Title</label>
            <input value={project.title} onChange={(e) => set("title", e.target.value)} /></div>
          <div className="field"><label>Original author(s)</label>
            <input value={project.authors} onChange={(e) => set("authors", e.target.value)} /></div>
          <div className="field"><label>Source URL</label>
            <input value={project.source_url} onChange={(e) => set("source_url", e.target.value)} /></div>
          <div className="field"><label>License</label>
            <input value={project.license} onChange={(e) => set("license", e.target.value)} /></div>
          <div className="field"><label>Target episode length (s)</label>
            <input type="number" value={project.target_episode_length}
              onChange={(e) => set("target_episode_length", Number(e.target.value))} /></div>
          <div className="field"><label>Narrator voice</label>
            <input value={project.narrator_voice} placeholder="e.g. Kokoro: am_adam"
              onChange={(e) => set("narrator_voice", e.target.value)} /></div>
          <div className="field"><label>Language</label>
            <input value={project.language} onChange={(e) => set("language", e.target.value)} /></div>
          <div className="field"><label>Monthly budget cap (USD, 0 = no cap)</label>
            <input type="number" step="0.01" min="0" value={project.monthly_budget_cap}
              onChange={(e) => set("monthly_budget_cap", Number(e.target.value))} /></div>
        </div>
        <div className="field"><label>Style bible (prepended to every shot prompt)</label>
          <textarea value={project.style_bible} rows={4}
            placeholder="Desaturated cold grade, heavy film grain, 1990s VHS archive look, low-key lighting, slow handheld camera, anamorphic..."
            onChange={(e) => set("style_bible", e.target.value)} /></div>
        <div className="btn-row">
          <button className="primary" onClick={save}>Save</button>
          {saved && <span style={{ color: "var(--ok)" }}>Saved ✓</span>}
          {cost && (
            <span className="muted small">
              Spent: ${cost.spent.toFixed(2)}
              {cost.cap > 0
                ? <> / ${cost.cap.toFixed(2)} cap
                    {cost.over
                      ? <strong style={{ color: "var(--bad, #c0392b)" }}> · cap reached</strong>
                      : <> · ${(cost.remaining ?? 0).toFixed(2)} left</>}
                  </>
                : " (no cap)"}
            </span>
          )}
          {(!project.authors || !project.source_url) && (
            <span className="muted small">
              ⚠ Author and source URL are required before export (license rule).
            </span>
          )}
        </div>
      </div>

      <ScriptGenPanel
        project={project}
        episodeCount={episodes.length}
        sys={sys}
        onProviderChange={loadSys}
        onChangeSource={(v) => set("source_text", v)}
        onGenerated={load}
      />

      <div className="btn-row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ border: "none" }}>Episodes</h2>
        <button className="primary" onClick={addEpisode}>+ Add episode</button>
      </div>
      {episodes.length === 0 ? (
        <div className="empty">No episodes yet. Add Part 1 to begin.</div>
      ) : (
        <div className="card-list">
          {episodes.map((ep) => (
            <div key={ep.id} className="card" onClick={() => onOpenEpisode(ep.id)}>
              <div className="scp">PART {ep.part_number}</div>
              <h3 style={{ margin: "6px 0" }}>{ep.title || "(untitled)"}</h3>
              <span className={`tag ${ep.status}`}>{ep.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AutoGenPanel({
  project, episodeCount, sys, onProviderChange, onDone,
}: {
  project: Project;
  episodeCount: number;
  sys: SystemStatus | null;
  onProviderChange: () => void;
  onDone: () => void;
}) {
  const geminiReady = !!sys?.llm_key_set;
  const [scpRef, setScpRef] = useState(project.scp_number);
  const [numParts, setNumParts] = useState(0);
  const [withShots, setWithShots] = useState(true);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setScpRef(project.scp_number), [project.scp_number]);

  const running = job?.status === "queued" || job?.status === "running";

  // Poll the job while it runs; refresh the project view when it finishes.
  useInterval(() => {
    if (!job) return;
    api.getJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "done" || j.status === "error") onDone();
    }).catch(() => { /* keep last state */ });
  }, 1200, running);

  const start = async () => {
    if (episodeCount > 0 &&
        !window.confirm(`This replaces the ${episodeCount} existing episode(s) and their shots. Continue?`)) {
      return;
    }
    setError(null);
    try {
      const j = await api.autogenerate(project.id, {
        scp_ref: scpRef, num_parts: numParts,
        generate_shots: withShots, replace: true,
      });
      setJob(j);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="panel" style={{ borderColor: "var(--accent)" }}>
      <h3>✨ Auto-generate from a real SCP</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        One click: fetch the SCP article (with its author credit), retell it into
        episodes, and build each episode's shot list. Hands-off — just review the
        result. Everything stays editable afterwards.
      </p>
      <div className="grid-2">
        <div className="field"><label>SCP number or URL</label>
          <input value={scpRef} placeholder="e.g. SCP-173 or 173"
            onChange={(e) => setScpRef(e.target.value)} /></div>
        <div className="field"><label>Episodes</label>
          <select value={numParts} onChange={(e) => setNumParts(Number(e.target.value))}>
            <option value={0}>Auto (let the AI decide)</option>
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </select></div>
      </div>
      <ProviderPicker sys={sys} onChange={onProviderChange} disabled={running} />
      <div className="btn-row" style={{ alignItems: "center" }}>
        <button className="primary" onClick={start}
          disabled={running || !geminiReady || !scpRef.trim()}>
          {running ? <span className="spin" /> : "✨ Auto-generate"}
        </button>
        <label className="small" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={withShots}
            disabled={running}
            onChange={(e) => setWithShots(e.target.checked)} />
          also generate shot lists
        </label>
      </div>

      {!geminiReady && (
        <div style={{ marginTop: 10 }}>
          <Banner kind="warn">
            No API key saved for the selected AI. Pick a provider above and add
            its key under <strong>Settings</strong> first.
          </Banner>
        </div>
      )}
      {running && job && (
        <div style={{ marginTop: 12 }}>
          <div className="progress"><div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div>
          <div className="small muted" style={{ marginTop: 6 }}>
            {job.message || "Working…"}
          </div>
        </div>
      )}
      {job?.status === "done" && (
        <div style={{ marginTop: 10 }}>
          <Banner kind="ok">{job.message || "Done."} Scroll down to review the episodes.</Banner>
        </div>
      )}
      {job?.status === "error" && (
        <div style={{ marginTop: 10 }}><Banner kind="err">{job.error || "Generation failed."}</Banner></div>
      )}
      {error && <div style={{ marginTop: 10 }}><Banner kind="err">{error}</Banner></div>}
    </div>
  );
}

function ScriptGenPanel({
  project, episodeCount, sys, onProviderChange,
  onChangeSource, onGenerated,
}: {
  project: Project;
  episodeCount: number;
  sys: SystemStatus | null;
  onProviderChange: () => void;
  onChangeSource: (v: string) => void;
  onGenerated: () => void;
}) {
  const geminiReady = !!sys?.llm_key_set;
  const model = sys?.llm_model ?? "";
  const [numParts, setNumParts] = useState(0);   // 0 = auto
  const [guidance, setGuidance] = useState("");
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const hasSource = !!project.source_text.trim();

  const generate = async () => {
    if (replace && episodeCount > 0) {
      const ok = window.confirm(
        `This will delete the ${episodeCount} existing episode(s) and their ` +
        `shots/audio, then create a fresh set. Continue?`,
      );
      if (!ok) return;
    }
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await api.generateScript(project.id, {
        source_text: project.source_text,
        num_parts: numParts,
        guidance,
        replace,
      });
      const cost = res.cost > 0 ? ` · ~$${res.cost.toFixed(4)}` : "";
      setResult(
        `Generated ${res.episodes.length} episode(s) with ${res.model}${cost}. ` +
        `Review and edit each one before producing audio.`,
      );
      onGenerated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h3>Generate episodes from the story</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        Paste the full SCP story below. The AI splits it into episode drafts —
        each with a hook, narration and cliffhanger — which you then review and
        edit. Nothing is produced until you approve it.
      </p>

      <div className="field">
        <label>Source story</label>
        <textarea
          rows={8}
          value={project.source_text}
          placeholder="Paste the SCP article / story text here…"
          onChange={(e) => onChangeSource(e.target.value)}
        />
      </div>

      <div className="grid-2">
        <div className="field">
          <label>Number of parts</label>
          <select value={numParts} onChange={(e) => setNumParts(Number(e.target.value))}>
            <option value={0}>Auto (let the AI decide)</option>
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Extra guidance (optional)</label>
          <input
            value={guidance}
            placeholder="e.g. keep it under 60s, emphasize the containment breach"
            onChange={(e) => setGuidance(e.target.value)}
          />
        </div>
      </div>

      <ProviderPicker sys={sys} onChange={onProviderChange} disabled={busy} />

      <div className="btn-row" style={{ alignItems: "center" }}>
        <button className="primary" onClick={generate}
          disabled={busy || !geminiReady || !hasSource}>
          {busy ? <span className="spin" /> : "Generate episodes"}
        </button>
        <label className="small" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={replace}
            onChange={(e) => setReplace(e.target.checked)} />
          Replace existing episodes
        </label>
        {model && <span className="muted small">model: {model}</span>}
      </div>

      {!geminiReady && (
        <div style={{ marginTop: 10 }}>
          <Banner kind="warn">
            No API key saved for the selected AI. Pick a provider above and add
            its key under <strong>Settings</strong> to enable generation.
          </Banner>
        </div>
      )}
      {!replace && episodeCount > 0 && geminiReady && (
        <p className="muted small" style={{ marginTop: 8 }}>
          New episodes will be appended after Part {episodeCount}. Tick
          “Replace” to start over.
        </p>
      )}
      {error && <div style={{ marginTop: 10 }}><Banner kind="err">{error}</Banner></div>}
      {result && (
        <div style={{ marginTop: 10 }}>
          <Banner kind="ok">{result}</Banner>
        </div>
      )}
    </div>
  );
}
