import { useEffect, useState } from "react";
import { api } from "../api";
import type { Project } from "../types";
import { Modal } from "./common";

export function ProjectList({ onOpen }: { onOpen: (id: number) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [showNew, setShowNew] = useState(false);

  const refresh = () => api.listProjects().then(setProjects);
  useEffect(() => { refresh(); }, []);

  return (
    <div className="container">
      <div className="btn-row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Projects</h1>
          <div className="muted small">One SCP story per project (a series of shorts).</div>
        </div>
        <button className="primary" onClick={() => setShowNew(true)}>+ New project</button>
      </div>

      {projects.length === 0 ? (
        <div className="empty">No projects yet. Create one to get started.</div>
      ) : (
        <div className="card-list" style={{ marginTop: 20 }}>
          {projects.map((p) => (
            <div key={p.id} className="card" onClick={() => onOpen(p.id)}>
              <div className="scp">{p.scp_number}</div>
              <h3 style={{ margin: "6px 0" }}>{p.title || "(untitled)"}</h3>
              <div className="muted small">{p.authors || "no author set"}</div>
              <div className="muted small" style={{ marginTop: 8 }}>
                Target {p.target_episode_length}s · {p.license}
              </div>
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <NewProjectModal
          onClose={() => setShowNew(false)}
          onCreated={(p) => { setShowNew(false); refresh(); onOpen(p.id); }}
        />
      )}
    </div>
  );
}

function NewProjectModal({
  onClose, onCreated,
}: {
  onClose: () => void;
  onCreated: (p: Project) => void;
}) {
  const [form, setForm] = useState({
    scp_number: "", title: "", authors: "", source_url: "",
    license: "CC BY-SA 3.0", target_episode_length: 61,
  });
  const [err, setErr] = useState("");
  const set = (k: string, v: string | number) => setForm({ ...form, [k]: v });

  const submit = async () => {
    if (!form.scp_number.trim()) { setErr("SCP number is required."); return; }
    try {
      onCreated(await api.createProject(form));
    } catch (e) { setErr(String(e)); }
  };

  return (
    <Modal title="New project" onClose={onClose}>
      <div className="grid-2">
        <div className="field">
          <label>SCP number *</label>
          <input value={form.scp_number} placeholder="SCP-049"
            onChange={(e) => set("scp_number", e.target.value)} />
        </div>
        <div className="field">
          <label>Target length (s)</label>
          <input type="number" value={form.target_episode_length}
            onChange={(e) => set("target_episode_length", Number(e.target.value))} />
        </div>
      </div>
      <div className="field">
        <label>Title</label>
        <input value={form.title} placeholder="The Plague Doctor"
          onChange={(e) => set("title", e.target.value)} />
      </div>
      <div className="field">
        <label>Original author(s)</label>
        <input value={form.authors} placeholder="Josh Wilson (Gabriel Jade)"
          onChange={(e) => set("authors", e.target.value)} />
      </div>
      <div className="field">
        <label>Source URL</label>
        <input value={form.source_url} placeholder="https://scp-wiki.wikidot.com/scp-049"
          onChange={(e) => set("source_url", e.target.value)} />
      </div>
      <div className="field">
        <label>License</label>
        <input value={form.license} onChange={(e) => set("license", e.target.value)} />
      </div>
      {err && <div className="banner err">{err}</div>}
      <div className="btn-row">
        <button className="primary" onClick={submit}>Create</button>
        <button className="ghost" onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  );
}
