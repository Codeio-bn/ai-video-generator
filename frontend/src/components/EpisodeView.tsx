import { useEffect, useRef, useState } from "react";
import { api, fileUrl, upload } from "../api";
import type { Episode, Project, Shot, ShotType } from "../types";
import { RenderPanel } from "./RenderPanel";

const KB_DIRECTIONS = ["in", "out", "left", "right", "up", "down"];

export function EpisodeView({
  episodeId, onBack, onBackProject,
}: {
  episodeId: number;
  onBack: () => void;
  onBackProject: (pid: number) => void;
}) {
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [whisperOk, setWhisperOk] = useState(false);
  const [saved, setSaved] = useState(false);

  const loadShots = () => api.listShots(episodeId).then(setShots);
  const loadEpisode = () => api.getEpisode(episodeId).then((ep) => {
    setEpisode(ep);
    api.getProject(ep.project_id).then(setProject);
  });
  useEffect(() => {
    loadEpisode(); loadShots();
    api.system().then((s) => setWhisperOk(s.whisper_ok));
  }, [episodeId]);

  if (!episode || !project) return <div className="container">Loading…</div>;
  const set = (k: keyof Episode, v: string | number) =>
    setEpisode({ ...episode, [k]: v });

  const saveEpisode = async () => {
    await api.updateEpisode(episodeId, episode);
    setSaved(true); setTimeout(() => setSaved(false), 1500);
  };

  const addShot = async (shot_type: ShotType) => {
    await api.createShot(episodeId, { shot_type, duration: 6 });
    loadShots();
  };

  const uploadNarration = async (f: File) => {
    await upload(`/api/episodes/${episodeId}/narration`, f);
    loadEpisode();
  };
  const uploadMusic = async (f: File) => {
    await upload(`/api/episodes/${episodeId}/music`, f);
    loadEpisode();
  };

  const move = async (idx: number, dir: -1 | 1) => {
    const next = [...shots];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    setShots(next);
    await api.reorderShots(episodeId, next.map((s) => s.id));
    loadShots();
  };

  const totalShotSecs = shots.reduce((a, s) => a + (s.duration || 0), 0);

  return (
    <div className="container">
      <div className="crumbs">
        <a onClick={onBack}>Projects</a> /{" "}
        <a onClick={() => onBackProject(project.id)}>{project.scp_number}</a> /{" "}
        Part {episode.part_number}
      </div>
      <h1>Part {episode.part_number}: {episode.title || "(untitled)"}</h1>
      <span className={`tag ${episode.status}`}>{episode.status}</span>

      {/* ---- script ---- */}
      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Script</h3>
        <div className="grid-2">
          <div className="field"><label>Episode title</label>
            <input value={episode.title} onChange={(e) => set("title", e.target.value)} /></div>
          <div className="field"><label>Part number</label>
            <input type="number" value={episode.part_number}
              onChange={(e) => set("part_number", Number(e.target.value))} /></div>
        </div>
        <div className="field"><label>Hook (first ~2 seconds)</label>
          <textarea rows={2} value={episode.hook} onChange={(e) => set("hook", e.target.value)} /></div>
        {episode.part_number > 1 && (
          <div className="field"><label>“Previously…” one-liner</label>
            <input value={episode.previously} onChange={(e) => set("previously", e.target.value)} /></div>
        )}
        <div className="field"><label>Narration script</label>
          <textarea rows={6} value={episode.narration_script}
            onChange={(e) => set("narration_script", e.target.value)} /></div>
        <div className="field"><label>Cliffhanger ending</label>
          <textarea rows={2} value={episode.cliffhanger}
            onChange={(e) => set("cliffhanger", e.target.value)} /></div>
        <div className="btn-row">
          <button className="primary" onClick={saveEpisode}>Save script</button>
          {episode.status === "draft" && (
            <button onClick={async () => { await api.updateEpisode(episodeId, { status: "approved" }); loadEpisode(); }}>
              Mark approved
            </button>
          )}
          {saved && <span style={{ color: "var(--ok)" }}>Saved ✓</span>}
        </div>
      </div>

      {/* ---- audio ---- */}
      <div className="panel">
        <h3>Audio</h3>
        <div className="row">
          <div>
            <label>Narration audio</label>
            <FileButton accept="audio/*" label="Upload narration" onFile={uploadNarration} />
            {episode.narration_audio_path && (
              <audio controls src={fileUrl(episode.narration_audio_path)} style={{ width: "100%", marginTop: 8 }} />
            )}
          </div>
          <div>
            <label>Background music (optional)</label>
            <FileButton accept="audio/*" label="Upload music" onFile={uploadMusic} />
            {episode.music_path && (
              <audio controls src={fileUrl(episode.music_path)} style={{ width: "100%", marginTop: 8 }} />
            )}
          </div>
        </div>
      </div>

      {/* ---- shots ---- */}
      <div className="btn-row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ border: "none" }}>
          Shots <span className="muted small">· {shots.length} shots · {totalShotSecs.toFixed(0)}s</span>
        </h2>
        <div className="btn-row">
          <button onClick={() => addShot("still_image")}>+ Image shot</button>
          <button onClick={() => addShot("text_card")}>+ Text card</button>
        </div>
      </div>
      {shots.length === 0 ? (
        <div className="empty">No shots yet. Add an image shot and upload a picture, or a text card.</div>
      ) : (
        shots.map((shot, i) => (
          <ShotRow key={shot.id} shot={shot} index={i} total={shots.length}
            onMove={move} onChange={loadShots} />
        ))
      )}

      {/* ---- render ---- */}
      <h2>Output</h2>
      <RenderPanel episode={episode}
        whisperOk={whisperOk} onRendered={loadEpisode} />
    </div>
  );
}

function FileButton({
  accept, label, onFile,
}: {
  accept: string; label: string; onFile: (f: File) => void | Promise<void>;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <button onClick={() => ref.current?.click()} disabled={busy}>
        {busy ? <span className="spin" /> : label}
      </button>
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          setBusy(true);
          try { await onFile(f); } finally { setBusy(false); if (ref.current) ref.current.value = ""; }
        }} />
    </>
  );
}

function ShotRow({
  shot, index, total, onMove, onChange,
}: {
  shot: Shot;
  index: number;
  total: number;
  onMove: (idx: number, dir: -1 | 1) => void;
  onChange: () => void;
}) {
  const [local, setLocal] = useState(shot);
  useEffect(() => setLocal(shot), [shot]);
  const set = (k: keyof Shot, v: string | number) => setLocal({ ...local, [k]: v });
  const commit = (data: Partial<Shot>) => api.updateShot(shot.id, data).then(onChange);

  const isVideo = !!local.asset_path && /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(local.asset_path);
  const uploadAsset = async (f: File) => {
    await upload(`/api/shots/${shot.id}/asset`, f);
    onChange();
  };

  return (
    <div className="shot">
      <div className="handle">
        <span className="muted">#{index + 1}</span>
        <button disabled={index === 0} onClick={() => onMove(index, -1)}>▲</button>
        <button disabled={index === total - 1} onClick={() => onMove(index, 1)}>▼</button>
      </div>

      {local.shot_type === "text_card" ? (
        <div className="thumb placeholder">TEXT<br />CARD</div>
      ) : local.asset_path ? (
        isVideo
          ? <video className="thumb" src={fileUrl(local.asset_path)} muted />
          : <img className="thumb" src={fileUrl(local.asset_path)} alt="" />
      ) : (
        <div className="thumb placeholder">no<br />media</div>
      )}

      <div className="body">
        <div className="row">
          <div style={{ maxWidth: 160 }}>
            <label>Type</label>
            <select value={local.shot_type}
              onChange={(e) => { set("shot_type", e.target.value); commit({ shot_type: e.target.value as ShotType }); }}>
              <option value="still_image">Still image (Ken Burns)</option>
              <option value="uploaded_media">Uploaded media</option>
              <option value="text_card">Text card</option>
              <option value="veo_video">Veo video (M4)</option>
            </select>
          </div>
          <div style={{ maxWidth: 120 }}>
            <label>Duration (s)</label>
            <input type="number" step="0.5" value={local.duration}
              onChange={(e) => set("duration", Number(e.target.value))}
              onBlur={() => commit({ duration: local.duration })} />
          </div>
          {(local.shot_type === "still_image") && !isVideo && (
            <div style={{ maxWidth: 140 }}>
              <label>Ken Burns</label>
              <select value={local.kenburns_direction}
                onChange={(e) => { set("kenburns_direction", e.target.value); commit({ kenburns_direction: e.target.value }); }}>
                {KB_DIRECTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          )}
        </div>

        {local.shot_type === "text_card" ? (
          <div className="field" style={{ marginTop: 8 }}>
            <label>Card text</label>
            <textarea rows={2} value={local.text_content}
              onChange={(e) => set("text_content", e.target.value)}
              onBlur={() => commit({ text_content: local.text_content })} />
          </div>
        ) : (
          <div className="field" style={{ marginTop: 8 }}>
            <label>Narration excerpt this shot covers</label>
            <input value={local.narration_excerpt}
              onChange={(e) => set("narration_excerpt", e.target.value)}
              onBlur={() => commit({ narration_excerpt: local.narration_excerpt })} />
          </div>
        )}

        <div className="btn-row" style={{ marginTop: 6 }}>
          {local.shot_type !== "text_card" && (
            <FileButton accept="image/*,video/*" label={local.asset_path ? "Replace media" : "Upload media"} onFile={uploadAsset} />
          )}
          <button className="danger ghost" onClick={() => api.deleteShot(shot.id).then(onChange)}>Delete</button>
        </div>
      </div>
    </div>
  );
}
