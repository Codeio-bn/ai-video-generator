import { useEffect, useState } from "react";
import { api } from "../api";
import type { Episode, Project } from "../types";

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

  const load = () => {
    api.getProject(projectId).then(setProject);
    api.listEpisodes(projectId).then(setEpisodes);
  };
  useEffect(load, [projectId]);

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
