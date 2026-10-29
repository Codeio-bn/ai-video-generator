import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, fileUrl } from "./api";
import type { Scene, SystemStatus, Video } from "./types";

/* ---------- small helpers ---------------------------------------------- */

function useInterval(cb: () => void, ms: number, active: boolean) {
  const saved = useRef(cb);
  saved.current = cb;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms, active]);
}

function Banner({ kind, children }: { kind: "err" | "warn" | "ok"; children: React.ReactNode }) {
  return <div className={`banner ${kind}`}>{children}</div>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/* ---------- top bar ----------------------------------------------------- */

function TopBar({ sys, onHome, onSettings }: {
  sys: SystemStatus | null; onHome: () => void; onSettings: () => void;
}) {
  const chip = (ok: boolean, label: string) => (
    <span className="chip"><span className={`dot ${ok ? "on" : "off"}`} />{label}</span>
  );
  return (
    <div className="topbar">
      <div className="topbar-in">
        <div className="mark" onClick={onHome}>
          <span className="mark-glyph" />
          <span className="mark-text"><b>SCP</b> VIDEO <span>STUDIO</span></span>
        </div>
        <div className="spacer" />
        <div className="chips">
          {sys && <>
            {chip(sys.script_ok, "Script · OpenAI")}
            {chip(sys.veo_ok, "Video · Veo")}
            {chip(sys.tts_ok, "Voice")}
          </>}
          <button className="btn ghost sm" onClick={onSettings}>Settings</button>
        </div>
      </div>
    </div>
  );
}

/* ---------- settings ---------------------------------------------------- */

function Settings({ sys, onClose, onSaved }: {
  sys: SystemStatus | null; onClose: () => void; onSaved: () => void;
}) {
  const [openai, setOpenai] = useState("");
  const [gemini, setGemini] = useState("");
  const [voice, setVoice] = useState(sys?.tts_voices?.includes("onyx") ? "onyx" : "");
  const [note, setNote] = useState<string | null>(null);

  const save = async (key: string, value: string) => {
    if (!value.trim()) return;
    await api.saveSecret(key, value.trim());
    setNote(`Saved ${key} locally to .secrets.json (never committed).`);
    setOpenai(""); setGemini(""); onSaved();
  };
  const saveVoice = async (v: string) => {
    setVoice(v);
    await api.saveSecret("OPENAI_TTS_VOICE", v);
    setNote(`Narrator voice set to ${v}.`);
    onSaved();
  };

  return (
    <Modal title="Settings" onClose={onClose}>
      <h4>Readiness</h4>
      <div className="readout">
        <div>FFmpeg: {sys?.ffmpeg_ok ? <span className="on">found</span> : <span className="off">missing — run scripts/setup.ps1</span>}</div>
        <div>Script writer (OpenAI): {sys?.script_ok ? <span className="on">{sys.script_model}</span> : <span className="off">{sys?.script_detail}</span>}</div>
        <div>Narration (OpenAI TTS): {sys?.tts_ok ? <span className="on">ready</span> : <span className="off">{sys?.tts_detail}</span>}</div>
        <div>Video (Veo): {sys?.veo_ok ? <span className="on">{sys.veo_model}</span> : <span className="off">{sys?.veo_detail}</span>}</div>
      </div>

      <h4>OpenAI API key — writes the script &amp; narrates</h4>
      <div className="field">
        <input type="password" value={openai} onChange={(e) => setOpenai(e.target.value)}
          placeholder={sys?.openai_key_set ? "•••••••• (a key is saved)" : "Paste your OpenAI API key"} />
      </div>
      <button className="btn stamp sm" disabled={!openai.trim()} onClick={() => save("OPENAI_API_KEY", openai)}>Save OpenAI key</button>

      <h4>Google Gemini API key — generates the video (Veo)</h4>
      <div className="field">
        <input type="password" value={gemini} onChange={(e) => setGemini(e.target.value)}
          placeholder={sys?.gemini_key_set ? "•••••••• (a key is saved)" : "Paste your Gemini API key"} />
      </div>
      <button className="btn stamp sm" disabled={!gemini.trim()} onClick={() => save("GEMINI_API_KEY", gemini)}>Save Gemini key</button>

      <h4>Narrator voice</h4>
      <div className="field">
        <select value={voice} onChange={(e) => saveVoice(e.target.value)}>
          <option value="">Default (onyx)</option>
          {sys?.tts_voices?.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>

      {note && <div style={{ marginTop: 14 }}><Banner kind="ok">{note}</Banner></div>}
    </Modal>
  );
}

/* ---------- intake + registry ------------------------------------------ */

function Intake({ sys, onCreated, videos, onOpen, onRefresh }: {
  sys: SystemStatus | null;
  onCreated: (v: Video) => void;
  videos: Video[];
  onOpen: (id: string) => void;
  onRefresh: () => void;
}) {
  const [ref, setRef] = useState("");
  const [guidance, setGuidance] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const go = async () => {
    if (!ref.trim()) return;
    setBusy(true); setErr(null);
    try { onCreated(await api.createVideo(ref.trim(), guidance.trim())); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const remove = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!window.confirm("Delete this case file and its generated media?")) return;
    await api.deleteVideo(id); onRefresh();
  };

  return (
    <>
      <div className="intake">
        <div className="intake-body">
          <div className="intake-kicker">
            <span>SPECIAL CONTAINMENT MEDIA / INTAKE</span>
            <span className="stamp-badge">PENDING</span>
          </div>
          <div className="item-field">
            <span className="item-prefix">ITEM&nbsp;#</span>
            <input className="item-input" value={ref} spellCheck={false}
              placeholder="SCP-173"
              onChange={(e) => setRef(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !busy) go(); }} />
          </div>
          <p className="intake-lede">
            Enter an SCP designation, slug, or wiki URL. OpenAI retells it as a
            30-second, 5–6 scene script — each scene with narration, a visual, and
            sound design — then Veo turns every scene into video.
          </p>
          <div className="intake-row">
            <button className="btn stamp" onClick={go} disabled={busy || !ref.trim() || !sys?.script_ok}>
              {busy ? <><span className="spin" /> &nbsp;Classifying…</> : "Generate script"}
            </button>
            <span style={{ fontSize: 13, color: "var(--ink-soft)" }}>
              Veo billed per clip · review the script before producing
            </span>
          </div>
          <textarea className="guidance" rows={2} value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            placeholder="Optional direction — e.g. 'lean into the dread, keep it found-footage'." />
          {!sys?.script_ok && (
            <div style={{ marginTop: 14 }}>
              <Banner kind="warn">{sys?.script_detail ?? "Add your OpenAI API key under Settings to write scripts."}</Banner>
            </div>
          )}
          {err && <div style={{ marginTop: 14 }}><Banner kind="err">{err}</Banner></div>}
        </div>
      </div>

      <div className="section-head">
        <h2>CASE FILES</h2>
        <span className="count">{videos.length} on record</span>
      </div>
      {videos.length === 0 ? (
        <div className="empty">No case files yet. Classify an SCP above to begin.</div>
      ) : (
        <div className="registry">
          {videos.map((v) => (
            <div className="file-row" key={v.id} onClick={() => onOpen(v.id)}>
              <span className="file-id">{(v.scp_ref || "SCP").toUpperCase()}</span>
              <span className="file-title">{v.title || "(untitled)"}</span>
              <span className="file-meta">{v.scenes.length} scenes · {v.created_at.slice(0, 10)}</span>
              <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className={`tag ${v.status}`}>{v.status}</span>
                <button className="btn ghost sm danger" onClick={(e) => remove(e, v.id)}>Delete</button>
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

/* ---------- scene card -------------------------------------------------- */

function SceneCard({ video, scene, onChange }: {
  video: Video; scene: Scene; onChange: (v: Video) => void;
}) {
  const [local, setLocal] = useState(scene);
  useEffect(() => setLocal(scene), [scene]);
  const editable = video.status !== "producing";

  const commit = async (field: "narration" | "visual" | "sound") => {
    if (local[field] === scene[field]) return;
    onChange(await api.patchScene(video.id, scene.index, { [field]: local[field] }));
  };

  const n = String(scene.index + 1).padStart(2, "0");
  return (
    <div className={`scene ${scene.status}`}>
      <div>
        <div className="scene-num">
          <span>SCENE {n}</span>
          <span className="dur">{scene.duration ? `${scene.duration.toFixed(1)}s` : "~5s"}</span>
        </div>
        <div className="fieldset">
          <div className="f narration">
            <label>Narration</label>
            <textarea rows={2} value={local.narration} disabled={!editable}
              onChange={(e) => setLocal({ ...local, narration: e.target.value })}
              onBlur={() => commit("narration")} />
          </div>
          <div className="f">
            <label>Visual — what Veo films</label>
            <textarea rows={3} value={local.visual} disabled={!editable}
              onChange={(e) => setLocal({ ...local, visual: e.target.value })}
              onBlur={() => commit("visual")} />
          </div>
          <div className="f">
            <label>Sound design</label>
            <textarea rows={1} value={local.sound} disabled={!editable}
              onChange={(e) => setLocal({ ...local, sound: e.target.value })}
              onBlur={() => commit("sound")} />
          </div>
        </div>
      </div>
      <div className={`monitor ${scene.status === "generating" ? "gen" : ""}`}>
        {scene.clip_path
          ? <video src={fileUrl(scene.clip_path)} muted loop playsInline
              onMouseOver={(e) => e.currentTarget.play()}
              onMouseOut={(e) => e.currentTarget.pause()} />
          : <span className="ph">{
              scene.status === "generating" ? "RENDERING…"
              : scene.status === "error" ? "FAILED"
              : "NO FOOTAGE"
            }</span>}
      </div>
    </div>
  );
}

/* ---------- dossier (review + produce + result) ------------------------ */

function Dossier({ video, sys, onChange, onBack }: {
  video: Video; sys: SystemStatus | null; onChange: (v: Video) => void; onBack: () => void;
}) {
  const [err, setErr] = useState<string | null>(null);
  const [regen, setRegen] = useState(false);
  const producing = video.status === "producing";

  useInterval(async () => {
    try { onChange(await api.getVideo(video.id)); } catch { /* keep */ }
  }, 2000, producing);

  const estCost = sys ? video.scenes.length * sys.veo_price_per_sec * sys.veo_clip_seconds : 0;

  const produce = async () => {
    if (!window.confirm(
      `Produce ${video.scenes.length} Veo clips (${sys?.veo_model}).\n\n` +
      `This calls a paid API — roughly $${estCost.toFixed(2)} total. Continue?`)) return;
    setErr(null);
    try { onChange(await api.produce(video.id)); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  const regenerate = async () => {
    if (!window.confirm("Rewrite the script from scratch? This replaces the current scenes.")) return;
    setRegen(true); setErr(null);
    try { onChange(await api.regenerateScript(video.id)); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setRegen(false); }
  };

  return (
    <>
      <div className="crumb" onClick={onBack}>← Case files</div>

      <div className="dossier-head">
        <div className="reg">
          <span>REGISTRY {video.id.toUpperCase()}</span>
          <span>{video.scenes.length} SCENES · ~{Math.round(video.final_duration || 30)}s</span>
        </div>
        <div className="item">{(video.scp_ref || "SCP").toUpperCase()}</div>
        <div className="title">{video.title || "(untitled)"}</div>
        <div className="attrib">
          {video.authors ? <>By {video.authors}. </> : <>Author on record pending. </>}
          {video.source_url && <a href={video.source_url} target="_blank" rel="noreferrer">Source</a>}
          {" · "}{video.license}
        </div>
        <span className="classif">{video.status === "done" ? "RELEASED" : "CLASSIFIED"}</span>
      </div>

      <div className="scenes">
        {video.scenes.map((s) => (
          <SceneCard key={s.index} video={video} scene={s} onChange={onChange} />
        ))}
      </div>

      <div className="actionbar">
        {!producing && video.status !== "done" && (
          <>
            <span className="cost"><span className="bars" /> est. ${estCost.toFixed(2)} to produce</span>
            <button className="btn stamp" onClick={produce} disabled={!sys?.veo_ok || !sys?.tts_ok}
              title={sys?.veo_ok ? "" : sys?.veo_detail}>Produce video</button>
            <button className="btn ghost" onClick={regenerate} disabled={regen}>
              {regen ? <><span className="spin" />&nbsp;Rewriting…</> : "Rewrite script"}
            </button>
          </>
        )}
        {producing && (
          <>
            <div className="progress"><div style={{ width: `${Math.round(video.progress * 100)}%` }} /></div>
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--hazard)" }}>
              {Math.round(video.progress * 100)}%
            </span>
          </>
        )}
        {video.status === "done" && (
          <>
            <span className="cost" style={{ color: "var(--sage)" }}>✓ Released · {video.final_duration.toFixed(0)}s</span>
            <button className="btn" onClick={produce}>Re-produce</button>
          </>
        )}
        {(producing || video.message) && <div className="msg">{video.message}</div>}
      </div>

      {!sys?.veo_ok && video.status !== "producing" && (
        <Banner kind="warn">{sys?.veo_detail ?? "Veo isn't ready — add a Gemini key with Veo access under Settings."}</Banner>
      )}
      {err && <Banner kind="err">{err}</Banner>}
      {video.status === "error" && video.error && <Banner kind="err">{video.error}</Banner>}

      {video.status === "done" && video.final_path && (
        <div className="result">
          <div className="big-monitor">
            <video src={fileUrl(video.final_path)} controls playsInline />
          </div>
          <div>
            <h3>FINAL CUT</h3>
            <p>Your {video.final_duration.toFixed(0)}-second vertical video is ready. Right-click the player to save it, or re-produce to regenerate the clips.</p>
            <a className="btn stamp" href={fileUrl(video.final_path)} download={`${video.scp_ref || "scp"}.mp4`}>Download MP4</a>
          </div>
        </div>
      )}
    </>
  );
}

/* ---------- app shell --------------------------------------------------- */

export default function App() {
  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [current, setCurrent] = useState<Video | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const loadSys = useCallback(() => { api.system().then(setSys).catch(() => setSys(null)); }, []);
  const loadVideos = useCallback(() => { api.listVideos().then(setVideos).catch(() => setVideos([])); }, []);
  useEffect(() => { loadSys(); loadVideos(); }, [loadSys, loadVideos]);

  const open = async (id: string) => { setCurrent(await api.getVideo(id)); };
  const home = () => { setCurrent(null); loadVideos(); };

  return (
    <>
      <TopBar sys={sys} onHome={home} onSettings={() => setShowSettings(true)} />
      <main>
        <div className="wrap">
          {current
            ? <Dossier video={current} sys={sys} onChange={setCurrent} onBack={home} />
            : <Intake sys={sys} videos={videos} onOpen={open} onRefresh={loadVideos}
                onCreated={(v) => { setCurrent(v); loadVideos(); }} />}
        </div>
      </main>
      {showSettings && (
        <Settings sys={sys} onClose={() => setShowSettings(false)}
          onSaved={() => { loadSys(); }} />
      )}
    </>
  );
}
