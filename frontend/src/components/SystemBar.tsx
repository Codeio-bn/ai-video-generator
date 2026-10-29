import { useEffect, useState } from "react";
import { api } from "../api";
import type { SystemStatus } from "../types";
import { Banner, Modal } from "./common";

export function SystemBar({ onBrand }: { onBrand: () => void }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const refresh = () => api.system().then(setStatus).catch(() => setStatus(null));
  useEffect(() => { refresh(); }, []);

  const chip = (ok: boolean, label: string, warn = false) => (
    <span className="chip">
      <span className={`dot ${ok ? "ok" : warn ? "warn" : "bad"}`} />
      {label}
    </span>
  );

  return (
    <div className="topbar">
      <div className="brand" onClick={onBrand}>
        <span className="badge">SCP</span> Shorts Studio
      </div>
      <div className="spacer" />
      <div className="status-chips">
        {status && (
          <>
            {chip(status.ffmpeg_ok, "FFmpeg")}
            {chip(status.whisper_ok, "Captions", true)}
            {chip(status.kokoro_ok, "Kokoro TTS", true)}
            {chip(status.gemini_key_set, "Gemini", true)}
          </>
        )}
        <button className="ghost" onClick={() => setShowSettings(true)}>Settings</button>
      </div>
      {showSettings && (
        <SettingsModal
          status={status}
          onClose={() => { setShowSettings(false); refresh(); }}
        />
      )}
    </div>
  );
}

function SettingsModal({
  status, onClose,
}: {
  status: SystemStatus | null;
  onClose: () => void;
}) {
  const [key, setKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const save = async () => {
    if (!key.trim()) return;
    await api.saveSecret("GEMINI_API_KEY", key.trim());
    setResult({ ok: true, detail: "Saved locally to .secrets.json (never committed)." });
    setKey("");
  };
  const test = async () => {
    setTesting(true);
    try { setResult(await api.testGemini()); }
    finally { setTesting(false); }
  };

  return (
    <Modal title="Settings" onClose={onClose}>
      <h3>Environment</h3>
      <div className="small" style={{ marginBottom: 14 }}>
        <div>FFmpeg: {status?.ffmpeg ? <code>{status.ffmpeg}</code> : <span className="muted">not found</span>}</div>
        <div style={{ marginTop: 6 }}>
          Captions engine (faster-whisper):{" "}
          {status?.whisper_ok
            ? <span style={{ color: "var(--ok)" }}>available</span>
            : <span className="muted">unavailable — {status?.whisper_detail}</span>}
        </div>
        <div style={{ marginTop: 6 }}>
          Narration TTS (Kokoro):{" "}
          {status?.kokoro_ok
            ? <span style={{ color: "var(--ok)" }}>available</span>
            : <span className="muted">unavailable — {status?.kokoro_detail}</span>}
        </div>
      </div>

      <h3>Google Gemini API key</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        From Google AI Studio. Stored locally only; used from Milestone 2 onward.
      </p>
      <div className="field">
        <input
          type="password"
          placeholder={status?.gemini_key_set ? "•••••••• (a key is saved)" : "Paste your API key"}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </div>
      <div className="btn-row">
        <button className="primary" onClick={save} disabled={!key.trim()}>Save key</button>
        <button onClick={test} disabled={testing}>
          {testing ? <span className="spin" /> : "Test connection"}
        </button>
      </div>
      {result && (
        <div style={{ marginTop: 12 }}>
          <Banner kind={result.ok ? "ok" : "err"}>{result.detail}</Banner>
        </div>
      )}
    </Modal>
  );
}
