import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, fileUrl } from "./api";
import type { Scene, SystemStatus, Video } from "./types";

/* ---------- toasts ------------------------------------------------------ */

type ToastKind = "ok" | "err" | "info";
interface Toast { id: number; kind: ToastKind; text: string; }
const ToastCtx = createContext<(kind: ToastKind, text: string) => void>(() => {});
const useToast = () => useContext(ToastCtx);

function ToastHost({ toasts }: { toasts: Toast[] }) {
  const ico: Record<ToastKind, string> = { ok: "✓", err: "!", info: "›" };
  return createPortal(
    <div className="toast-host" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div className={`toast ${t.kind}`} key={t.id}>
          <span className="t-ico">{ico[t.kind]}</span>
          <span>{t.text}</span>
        </div>
      ))}
    </div>,
    document.body,
  );
}

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
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn ghost sm" aria-label="Close" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

interface Confirm {
  title: string; body: React.ReactNode; confirmLabel: string;
  danger?: boolean; onConfirm: () => void;
}

function ConfirmDialog({ confirm, onClose }: { confirm: Confirm; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal confirm" role="alertdialog" aria-modal="true" aria-label={confirm.title}
        onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><h3>{confirm.title}</h3></div>
        <div>{confirm.body}</div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className={`btn ${confirm.danger ? "danger" : "stamp"}`} autoFocus
            onClick={() => { confirm.onConfirm(); onClose(); }}>{confirm.confirmLabel}</button>
        </div>
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
        <button className="mark" onClick={onHome} aria-label="Back to intake">
          <span className="mark-glyph" />
          <span className="mark-text"><b>SCP</b> VIDEO <i>STUDIO</i></span>
        </button>
        <div className="spacer" />
        <div className="chips">
          {sys && <>
            {chip(sys.script_ok, "Script")}
            {chip(sys.veo_ok, "Video")}
            {chip(sys.tts_ok, "Voice")}
          </>}
          <button className="btn ghost sm" onClick={onSettings}>Settings</button>
        </div>
      </div>
    </div>
  );
}

/* ---------- settings ---------------------------------------------------- */

function KeyField({ saved, value, onChange, onSave, placeholder, label }: {
  saved: boolean; value: string; onChange: (v: string) => void;
  onSave: () => void; placeholder: string; label: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <>
      <div className="field">
        <input type={show ? "text" : "password"} value={value} aria-label={label}
          placeholder={placeholder} autoComplete="off" spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) onSave(); }} />
        <button type="button" className="reveal" onClick={() => setShow((s) => !s)}>
          {show ? "HIDE" : "SHOW"}
        </button>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="btn stamp sm" disabled={!value.trim()} onClick={onSave}>Save key</button>
        {saved && <span className="key-saved">✓ A key is saved</span>}
      </div>
    </>
  );
}

function Settings({ sys, onClose, onSaved }: {
  sys: SystemStatus | null; onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const [openai, setOpenai] = useState("");
  const [gemini, setGemini] = useState("");
  const [voice, setVoice] = useState(sys?.tts_voices?.includes("onyx") ? "onyx" : "");

  const save = async (key: string, value: string, label: string) => {
    if (!value.trim()) return;
    await api.saveSecret(key, value.trim());
    toast("ok", `${label} saved locally to .secrets.json.`);
    setOpenai(""); setGemini(""); onSaved();
  };
  const saveVoice = async (v: string) => {
    setVoice(v);
    await api.saveSecret("OPENAI_TTS_VOICE", v);
    toast("ok", `Narrator voice set to ${v || "onyx"}.`);
    onSaved();
  };

  const stat = (ok: boolean, on: string, off: string | undefined) =>
    ok ? <span className="on">{on}</span> : <span className="off">{off || "not ready"}</span>;

  return (
    <Modal title="Settings" onClose={onClose}>
      <h4>Readiness</h4>
      <div className="readout">
        <div className="row"><span>FFmpeg</span>{stat(!!sys?.ffmpeg_ok, "found", "missing — run scripts/setup.sh")}</div>
        <div className="row"><span>Script writer (OpenAI)</span>{stat(!!sys?.script_ok, sys?.script_model || "ready", sys?.script_detail)}</div>
        <div className="row"><span>Narration (OpenAI TTS)</span>{stat(!!sys?.tts_ok, "ready", sys?.tts_detail)}</div>
        <div className="row"><span>Video (Veo)</span>{stat(!!sys?.veo_ok, sys?.veo_model || "ready", sys?.veo_detail)}</div>
      </div>

      <h4>OpenAI API key — writes the script and narrates it</h4>
      <KeyField label="OpenAI API key" saved={!!sys?.openai_key_set} value={openai} onChange={setOpenai}
        onSave={() => save("OPENAI_API_KEY", openai, "OpenAI key")}
        placeholder={sys?.openai_key_set ? "•••••••• (replace the saved key)" : "Paste your OpenAI API key"} />

      <h4>Google Gemini API key — generates the video with Veo</h4>
      <KeyField label="Gemini API key" saved={!!sys?.gemini_key_set} value={gemini} onChange={setGemini}
        onSave={() => save("GEMINI_API_KEY", gemini, "Gemini key")}
        placeholder={sys?.gemini_key_set ? "•••••••• (replace the saved key)" : "Paste your Gemini API key"} />

      <h4>Narrator voice</h4>
      <div className="field">
        <select value={voice} aria-label="Narrator voice" onChange={(e) => saveVoice(e.target.value)}>
          <option value="">Default (onyx)</option>
          {sys?.tts_voices?.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>
    </Modal>
  );
}

/* ---------- intake + registry ------------------------------------------ */

function Intake({ sys, loading, onCreated, videos, onOpen, onDelete }: {
  sys: SystemStatus | null;
  loading: boolean;
  onCreated: (v: Video) => void;
  videos: Video[];
  onOpen: (id: string) => void;
  onDelete: (v: Video) => void;
}) {
  const [ref, setRef] = useState("");
  const [guidance, setGuidance] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const go = async () => {
    if (!ref.trim() || busy) return;
    setBusy(true); setErr(null);
    try { onCreated(await api.createVideo(ref.trim(), guidance.trim())); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="view">
      <div className="intake">
        <div className="intake-body">
          <div className="intake-kicker">
            <span>Special Containment Media · Intake</span>
            <span className="stamp-badge">PENDING</span>
          </div>
          <div className="item-field">
            <span className="item-prefix">ITEM&nbsp;#</span>
            <input className="item-input" value={ref} spellCheck={false} aria-label="SCP designation"
              placeholder="SCP-173"
              onChange={(e) => setRef(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
          </div>
          <p className="intake-lede">
            Enter an SCP designation, slug, or wiki URL. OpenAI retells it as a
            30-second, 5–6 scene script — each scene with narration, a visual, and
            sound design — then you review it before Veo films anything.
          </p>
          <div className="intake-row">
            <button className="btn stamp" onClick={go} disabled={busy || !ref.trim() || !sys?.script_ok}>
              {busy ? <><span className="spin" /> Classifying…</> : "Generate script"}
            </button>
            <span className="intake-hint"><span className="dot" /> Free to draft · Veo is billed per clip at production</span>
          </div>
          <textarea className="guidance" rows={2} value={guidance} aria-label="Optional direction"
            onChange={(e) => setGuidance(e.target.value)}
            placeholder="Optional direction — e.g. “lean into the dread, keep it found-footage.”" />
          {!sys?.script_ok && (
            <div style={{ marginTop: 16 }}>
              <Banner kind="warn">{sys?.script_detail ?? "Add your OpenAI API key under Settings to write scripts."}</Banner>
            </div>
          )}
          {err && <div style={{ marginTop: 16 }}><Banner kind="err">{err}</Banner></div>}
        </div>
      </div>

      <div className="section-head">
        <h2>CASE FILES</h2>
        <span className="count">{loading ? "loading…" : `${videos.length} on record`}</span>
      </div>

      {loading ? (
        <div className="registry">{[0, 1, 2].map((i) => <div className="skeleton" key={i} />)}</div>
      ) : videos.length === 0 ? (
        <div className="empty"><b>No case files yet.</b>Classify an SCP above and your drafts will collect here.</div>
      ) : (
        <div className="registry">
          {videos.map((v) => (
            <button className={`file-row ${v.status}`} key={v.id} onClick={() => onOpen(v.id)}>
              <span className="file-id">{(v.scp_ref || "SCP").toUpperCase()}</span>
              <span className="file-title">{v.title || "(untitled)"}</span>
              <span className="file-meta">{v.scenes.length} scenes · {v.created_at.slice(0, 10)}</span>
              <span className="file-actions">
                <span className={`tag ${v.status}`}>{v.status}</span>
                <span className="btn ghost sm danger" role="button" tabIndex={0}
                  onClick={(e) => { e.stopPropagation(); onDelete(v); }}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); onDelete(v); } }}>
                  Delete
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- scene card -------------------------------------------------- */

function SceneCard({ video, scene, onChange }: {
  video: Video; scene: Scene; onChange: (v: Video) => void;
}) {
  const [local, setLocal] = useState(scene);
  const vidRef = useRef<HTMLVideoElement>(null);
  useEffect(() => setLocal(scene), [scene]);
  const editable = video.status !== "producing";

  /* Autoplay the preview while it's on screen — works on touch, not just hover. */
  useEffect(() => {
    const el = vidRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) el.play().catch(() => {}); else el.pause(); },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [scene.clip_path]);

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
            <textarea rows={2} value={local.narration} disabled={!editable} aria-label={`Scene ${n} narration`}
              onChange={(e) => setLocal({ ...local, narration: e.target.value })}
              onBlur={() => commit("narration")} />
          </div>
          <div className="f">
            <label>Visual — what Veo films</label>
            <textarea rows={3} value={local.visual} disabled={!editable} aria-label={`Scene ${n} visual`}
              onChange={(e) => setLocal({ ...local, visual: e.target.value })}
              onBlur={() => commit("visual")} />
          </div>
          <div className="f">
            <label>Sound design</label>
            <textarea rows={1} value={local.sound} disabled={!editable} aria-label={`Scene ${n} sound`}
              onChange={(e) => setLocal({ ...local, sound: e.target.value })}
              onBlur={() => commit("sound")} />
          </div>
        </div>
      </div>
      <div className={`monitor ${scene.status === "generating" ? "gen" : ""}`}>
        {scene.status === "generating" && <span className="rec">REC</span>}
        {scene.clip_path ? (
          <>
            <video ref={vidRef} src={fileUrl(scene.clip_path)} muted loop playsInline preload="metadata" />
            <span className="play"><span /></span>
          </>
        ) : (
          <span className="ph">{
            scene.status === "generating" ? "RENDERING…"
            : scene.status === "error" ? "FILM FAILED"
            : "NO FOOTAGE"
          }</span>
        )}
      </div>
    </div>
  );
}

/* ---------- dossier (review + produce + result) ------------------------ */

function Dossier({ video, sys, onChange, onBack, onConfirm }: {
  video: Video; sys: SystemStatus | null;
  onChange: (v: Video) => void; onBack: () => void;
  onConfirm: (c: Confirm) => void;
}) {
  const toast = useToast();
  const [err, setErr] = useState<string | null>(null);
  const [regen, setRegen] = useState(false);
  const producing = video.status === "producing";

  useInterval(async () => {
    try { onChange(await api.getVideo(video.id)); } catch { /* keep last state */ }
  }, 2000, producing);

  const estCost = sys ? video.scenes.length * sys.veo_price_per_sec * sys.veo_clip_seconds : 0;

  const startProduce = async () => {
    setErr(null);
    try { onChange(await api.produce(video.id)); toast("info", "Production started — filming each scene."); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  const produce = () => {
    onConfirm({
      title: "Produce video",
      confirmLabel: `Produce · ~$${estCost.toFixed(2)}`,
      body: (
        <>
          <p>Veo will film {video.scenes.length} clips with <code>{sys?.veo_model}</code> and
            OpenAI will narrate each line. This calls a paid API.</p>
          <p style={{ marginTop: 10, color: "var(--hazard)", fontFamily: "var(--mono)", fontSize: 13 }}>
            Estimated cost ≈ ${estCost.toFixed(2)} ({video.scenes.length} × {sys?.veo_clip_seconds}s)
          </p>
        </>
      ),
      onConfirm: startProduce,
    });
  };

  const regenerate = async () => {
    setRegen(true); setErr(null);
    try { onChange(await api.regenerateScript(video.id)); toast("ok", "Script rewritten."); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setRegen(false); }
  };

  const askRegenerate = () => onConfirm({
    title: "Rewrite script",
    confirmLabel: "Rewrite",
    body: <p>This replaces the current scenes with a fresh take from OpenAI. Your edits will be lost.</p>,
    onConfirm: regenerate,
  });

  const done = video.scenes.filter((s) => s.status === "ready").length;
  const pct = Math.round(video.progress * 100);

  return (
    <div className="view">
      <button className="crumb" onClick={onBack}>← Case files</button>

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
        <span className={`classif ${video.status === "done" ? "released" : ""}`}>
          {video.status === "done" ? "RELEASED" : "CLASSIFIED"}
        </span>
      </div>

      <div className="scenes">
        {video.scenes.map((s) => (
          <SceneCard key={s.index} video={video} scene={s} onChange={onChange} />
        ))}
      </div>

      <div className="actionbar">
        {!producing && video.status !== "done" && (
          <>
            <span className="cost"><span className="bars" /> Est. ${estCost.toFixed(2)} to produce</span>
            <div className="spacer" />
            <button className="btn ghost" onClick={askRegenerate} disabled={regen}>
              {regen ? <><span className="spin" /> Rewriting…</> : "Rewrite script"}
            </button>
            <button className="btn stamp" onClick={produce} disabled={!sys?.veo_ok || !sys?.tts_ok}
              title={sys?.veo_ok ? "" : sys?.veo_detail}>Produce video</button>
          </>
        )}
        {producing && (
          <>
            <div className="progress-wrap">
              <div className="pips">
                {video.scenes.map((s) => (
                  <i key={s.index} className={
                    s.status === "ready" ? "done" : s.status === "generating" ? "active" : s.status === "error" ? "error" : ""
                  } />
                ))}
              </div>
              <span className="progress-label">Filming · {done}/{video.scenes.length} scenes · {pct}%</span>
            </div>
          </>
        )}
        {video.status === "done" && (
          <>
            <span className="cost ok">✓ Released · {video.final_duration.toFixed(0)}s</span>
            <div className="spacer" />
            <button className="btn" onClick={produce}>Re-produce</button>
          </>
        )}
        {(producing || video.message) && <div className="msg">{video.message}</div>}
      </div>

      {!sys?.veo_ok && !producing && (
        <Banner kind="warn">{sys?.veo_detail ?? "Veo isn’t ready — add a Gemini key with Veo access under Settings."}</Banner>
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
            <p>Your {video.final_duration.toFixed(0)}-second vertical video is ready. Download it below, or re-produce to regenerate the clips.</p>
            <a className="btn stamp" href={fileUrl(video.final_path)} download={`${video.scp_ref || "scp"}.mp4`}>Download MP4</a>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- app shell --------------------------------------------------- */

export default function App() {
  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(true);
  const [current, setCurrent] = useState<Video | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const pushToast = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts, { id, kind, text }]);
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 3800);
  }, []);

  const loadSys = useCallback(() => { api.system().then(setSys).catch(() => setSys(null)); }, []);
  const loadVideos = useCallback(() => {
    setLoadingVideos(true);
    api.listVideos().then(setVideos).catch(() => setVideos([])).finally(() => setLoadingVideos(false));
  }, []);
  useEffect(() => { loadSys(); loadVideos(); }, [loadSys, loadVideos]);

  const open = async (id: string) => { setCurrent(await api.getVideo(id)); };
  const home = () => { setCurrent(null); loadVideos(); };

  const askDelete = (v: Video) => setConfirm({
    title: "Delete case file",
    confirmLabel: "Delete",
    danger: true,
    body: <p>Permanently delete <code>{(v.scp_ref || "SCP").toUpperCase()}</code> and its generated media? This can’t be undone.</p>,
    onConfirm: async () => { await api.deleteVideo(v.id); pushToast("ok", "Case file deleted."); loadVideos(); },
  });

  return (
    <ToastCtx.Provider value={pushToast}>
      <TopBar sys={sys} onHome={home} onSettings={() => setShowSettings(true)} />
      <main>
        <div className="wrap">
          {current
            ? <Dossier video={current} sys={sys} onChange={setCurrent} onBack={home} onConfirm={setConfirm} />
            : <Intake sys={sys} loading={loadingVideos} videos={videos} onOpen={open} onDelete={askDelete}
                onCreated={(v) => { setCurrent(v); loadVideos(); }} />}
        </div>
      </main>
      {showSettings && (
        <Settings sys={sys} onClose={() => setShowSettings(false)} onSaved={loadSys} />
      )}
      {confirm && <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />}
      <ToastHost toasts={toasts} />
    </ToastCtx.Provider>
  );
}
