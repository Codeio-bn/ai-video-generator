import { useEffect, useState } from "react";
import { api } from "../api";
import type { SystemStatus } from "../types";
import { Banner, Modal } from "./common";

const PROVIDER_LABELS: Record<string, string> = {
  groq: "Groq",
  openai: "OpenAI",
  gemini: "Gemini",
};
const providerLabel = (p?: string) => PROVIDER_LABELS[p ?? ""] ?? "Gemini";

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
            {chip(status.llm_key_set, `Text: ${providerLabel(status.llm_provider)}`, true)}
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
  const [groqKey, setGroqKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [prov, setProv] = useState(status?.llm_provider ?? "");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const chooseProvider = async (value: string) => {
    setProv(value);
    await api.saveSecret("LLM_PROVIDER", value);
    setResult({ ok: true, detail: `Text provider set to ${providerLabel(value)}. Save that provider's API key below if you haven't yet.` });
  };

  const saveKey = async (name: string, value: string) => {
    if (!value.trim()) return;
    await api.saveSecret(name, value.trim());
    setResult({ ok: true, detail: `Saved ${name} locally to .secrets.json (never committed). Reopen Settings to see it take effect.` });
    setGroqKey(""); setOpenaiKey(""); setGeminiKey("");
  };
  const test = async () => {
    setTesting(true);
    try { setResult(await api.testGemini()); }
    finally { setTesting(false); }
  };

  const provider = providerLabel(status?.llm_provider);

  return (
    <Modal title="Settings" onClose={onClose}>
      <h3>Environment</h3>
      <div className="small" style={{ marginBottom: 14 }}>
        <div>FFmpeg: {status?.ffmpeg ? <code>{status.ffmpeg}</code> : <span className="muted">not found</span>}</div>
        <div style={{ marginTop: 6 }}>
          Text LLM: <strong>{provider}</strong>
          {status?.llm_model && <> — <code>{status.llm_model}</code></>}
          {status?.llm_key_set
            ? <span style={{ color: "var(--ok)" }}> (key saved)</span>
            : <span className="muted"> (no key)</span>}
        </div>
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

      <h3>Active text provider</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        Which service generates the story, episodes and shot lists. Pick one, then
        make sure its key is saved below. (Video/Veo always uses Gemini.)
      </p>
      <div className="field" style={{ marginBottom: 18 }}>
        <select value={prov} onChange={(e) => chooseProvider(e.target.value)}>
          <option value="groq">Groq{status?.groq_key_set ? " — key saved" : " — no key"}</option>
          <option value="openai">OpenAI (GPT){status?.openai_key_set ? " — key saved" : " — no key"}</option>
          <option value="gemini">Google Gemini{status?.gemini_key_set ? " — key saved" : " — no key"}</option>
        </select>
      </div>

      <h3>Groq API key (text)</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        Free & fast when available. Get one at console.groq.com.
      </p>
      <div className="field">
        <input
          type="password"
          placeholder={status?.groq_key_set ? "•••••••• (a key is saved)" : "Paste your Groq API key"}
          value={groqKey}
          onChange={(e) => setGroqKey(e.target.value)}
        />
      </div>
      <div className="btn-row" style={{ marginBottom: 18 }}>
        <button className="primary" onClick={() => saveKey("GROQ_API_KEY", groqKey)} disabled={!groqKey.trim()}>
          Save Groq key
        </button>
      </div>

      <h3>OpenAI API key (text)</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        GPT (default <code>gpt-4o-mini</code>). Get one at platform.openai.com.
        Used for script/shot generation when no Groq key is set (override the
        model with <code>OPENAI_MODEL</code>).
      </p>
      <div className="field">
        <input
          type="password"
          placeholder={status?.openai_key_set ? "•••••••• (a key is saved)" : "Paste your OpenAI API key"}
          value={openaiKey}
          onChange={(e) => setOpenaiKey(e.target.value)}
        />
      </div>
      <div className="btn-row" style={{ marginBottom: 18 }}>
        <button className="primary" onClick={() => saveKey("OPENAI_API_KEY", openaiKey)} disabled={!openaiKey.trim()}>
          Save OpenAI key
        </button>
      </div>

      <h3>Google Gemini API key (video + fallback text)</h3>
      <p className="small muted" style={{ marginTop: 0 }}>
        From Google AI Studio. Used for Veo video (Milestone 4+), and for text if
        no Groq key is set.
      </p>
      <div className="field">
        <input
          type="password"
          placeholder={status?.gemini_key_set ? "•••••••• (a key is saved)" : "Paste your Gemini API key"}
          value={geminiKey}
          onChange={(e) => setGeminiKey(e.target.value)}
        />
      </div>
      <div className="btn-row">
        <button className="primary" onClick={() => saveKey("GEMINI_API_KEY", geminiKey)} disabled={!geminiKey.trim()}>
          Save Gemini key
        </button>
        <button onClick={test} disabled={testing}>
          {testing ? <span className="spin" /> : `Test ${provider} connection`}
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
