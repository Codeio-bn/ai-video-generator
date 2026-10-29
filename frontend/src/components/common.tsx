import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

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
