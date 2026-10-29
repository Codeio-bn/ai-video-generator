import { useEffect, useState } from "react";
import { api } from "../api";
import type { Episode, Project, SystemStatus } from "../types";
import { Banner } from "./common";

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

  const loadEpisodes = () => api.listEpisodes(projectId).then(setEpisodes);
  const load = () => {
    api.getProject(projectId).then(setProject);
    loadEpisodes();
  };
  useEffect(load, [projectId]);
  useEffect(() => { api.system().then(setSys).catch(() => setSys(null)); }, []);

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
        </div>
        <div className="field"><label>Style bible (prepended to every shot prompt)</label>
          <textarea value={project.style_bible} rows={4}
            placeholder="Desaturated cold grade, heavy film grain, 1990s VHS archive look, low-key lighting, slow handheld camera, anamorphic..."
            onChange={(e) => set("style_bible", e.target.value)} /></div>
        <div className="btn-row">
          <button className="primary" onClick={save}>Save</button>
          {saved && <span style={{ color: "var(--ok)" }}>Saved ✓</span>}
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
        geminiReady={!!sys?.gemini_key_set}
        model={sys?.gemini_model ?? ""}
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

function ScriptGenPanel({
  project, episodeCount, geminiReady, model,
  onChangeSource, onGenerated,
}: {
  project: Project;
  episodeCount: number;
  geminiReady: boolean;
  model: string;
  onChangeSource: (v: string) => void;
  onGenerated: () => void;
}) {
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
      <h3>Generate episodes from the story (Gemini)</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        Paste the full SCP story below. Gemini splits it into episode drafts —
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
            <option value={0}>Auto (let Gemini decide)</option>
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
            No Gemini API key saved. Add one under <strong>Settings</strong> to
            enable generation.
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
