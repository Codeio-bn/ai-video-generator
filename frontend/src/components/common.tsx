import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import type { SystemStatus } from "../types";

const PROVIDERS = [
  { id: "groq", label: "Groq" },
  { id: "openai", label: "OpenAI (GPT)" },
  { id: "gemini", label: "Google Gemini" },
] as const;

const keySaved = (sys: SystemStatus | null, p: string) =>
  p === "groq" ? !!sys?.groq_key_set
  : p === "openai" ? !!sys?.openai_key_set
  : !!sys?.gemini_key_set;

/**
 * Picks which text AI runs a generation. Writes the LLM_PROVIDER secret and
 * asks the parent to refetch system status so the choice takes effect at once.
 */
export function ProviderPicker({
  sys, onChange, disabled,
}: {
  sys: SystemStatus | null;
  onChange: () => void;
  disabled?: boolean;
}) {
  const [saving, setSaving] = useState(false);
  const current = sys?.llm_provider ?? "";

  const choose = async (p: string) => {
    if (p === current) return;
    setSaving(true);
    try { await api.saveSecret("LLM_PROVIDER", p); onChange(); }
    finally { setSaving(false); }
  };

  const missingKey = !keySaved(sys, current);

  return (
    <div className="field" style={{ maxWidth: 320 }}>
      <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
        AI model for generation {saving && <span className="spin" />}
      </label>
      <select value={current} disabled={disabled || saving}
        onChange={(e) => choose(e.target.value)}>
        {PROVIDERS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}{keySaved(sys, p.id) ? " — key saved" : " — no key"}
          </option>
        ))}
      </select>
      {missingKey && (
        <span className="muted small" style={{ marginTop: 4 }}>
          No API key saved for this provider — add one under <strong>Settings</strong>.
        </span>
      )}
    </div>
  );
}

export function Modal({
  title, onClose, children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  // Close on Escape for convenience.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Render into <body> via a portal. The top bar uses backdrop-filter, which
  // makes it a containing block for position:fixed descendants — so a modal
  // nested under it would anchor to the bar (off-screen) instead of the
  // viewport. The portal lifts it out so `inset: 0` means the whole viewport.
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="btn-row" style={{ justifyContent: "space-between" }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="ghost" onClick={onClose}>✕</button>
        </div>
        <div style={{ marginTop: 14 }}>{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function Banner({ kind, children }: { kind: "warn" | "err" | "ok"; children: ReactNode }) {
  return <div className={`banner ${kind}`}>{children}</div>;
}

/** Calls `cb` every `ms` while `active` is true. */
export function useInterval(cb: () => void, ms: number, active: boolean) {
  const saved = useRef(cb);
  saved.current = cb;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms, active]);
}
