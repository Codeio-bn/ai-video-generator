import { useEffect, useState } from "react";
import { api, fileUrl } from "../api";
import type { Episode, Job, RenderOptions } from "../types";
import { Banner, useInterval } from "./common";

const DEFAULTS: RenderOptions = {
  show_title_card: true,
  show_end_card: true,
  title_card_seconds: 2,
  end_card_seconds: 3,
  captions: true,
  caption_mode: "word",
  film_grain: true,
  vignette: true,
  flicker: false,
  music: false,
  music_volume: 0.18,
  duck_music: true,
};

export function RenderPanel({
  episode, whisperOk, onRendered,
}: {
  episode: Episode;
  whisperOk: boolean;
  onRendered: () => void;
}) {
  const [opts, setOpts] = useState<RenderOptions>(DEFAULTS);
  const [job, setJob] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const set = (k: keyof RenderOptions, v: boolean | number | string) =>
    setOpts({ ...opts, [k]: v });

  // Restore an in-flight or finished job after a browser refresh.
  useEffect(() => {
    api.latestJob(episode.id).then((j) => {
      if (j && (j as Job).id) setJob(j as Job);
    });
  }, [episode.id]);

  const polling = job?.status === "running" || job?.status === "queued";
  useInterval(() => {
    if (job) api.getJob(job.id).then((j) => {
      setJob(j);
      if (j.status === "done") onRendered();
    });
  }, 1000, polling);

  const start = async () => {
    setStarting(true);
    try { setJob(await api.startRender(episode.id, opts)); }
    catch (e) { alert(String(e)); }
    finally { setStarting(false); }
  };

  const toggle = (k: keyof RenderOptions, label: string, disabled = false, hint?: string) => (
    <div className="checkbox" title={hint}>
      <input type="checkbox" id={k} checked={!!opts[k]} disabled={disabled}
        onChange={(e) => set(k, e.target.checked)} />
      <label htmlFor={k}>{label}{disabled && hint ? ` — ${hint}` : ""}</label>
    </div>
  );

  return (
    <div className="panel">
      <h3>Render</h3>
      <div className="grid-2" style={{ gap: 6 }}>
        {toggle("show_title_card", "“Part N” title card")}
        {toggle("show_end_card", "Attribution end card")}
        {toggle("captions", "Burned-in captions", !whisperOk,
          whisperOk ? undefined : "faster-whisper unavailable")}
        {toggle("film_grain", "Film grain")}
        {toggle("vignette", "Vignette")}
        {toggle("flicker", "Archive flicker")}
        {toggle("music", "Music bed", !episode.music_path,
          episode.music_path ? undefined : "no music uploaded")}
        {opts.music && toggle("duck_music", "Duck music under narration")}
      </div>
      {opts.captions && whisperOk && (
        <div className="field" style={{ marginTop: 10, maxWidth: 240 }}>
          <label>Caption style</label>
          <select value={opts.caption_mode}
            onChange={(e) => set("caption_mode", e.target.value)}>
            <option value="word">Word-by-word (big pop)</option>
            <option value="phrase">Short phrase (highlight active word)</option>
          </select>
        </div>
      )}

      <div className="btn-row" style={{ marginTop: 14 }}>
        <button className="primary" onClick={start} disabled={starting || polling}>
          {polling ? "Rendering…" : "▶ Render episode"}
        </button>
        {!episode.narration_audio_path && (
          <span className="muted small">Tip: upload narration audio for captions & timing.</span>
        )}
      </div>

      {job && (
        <div style={{ marginTop: 16 }}>
          {polling && (
            <>
              <div className="progress"><div style={{ width: `${(job.progress * 100).toFixed(0)}%` }} /></div>
              <div className="muted small" style={{ marginTop: 6 }}>
                <span className="spin" /> {job.message} ({(job.progress * 100).toFixed(0)}%)
              </div>
            </>
          )}
          {job.status === "error" && <Banner kind="err">Render failed: {job.error}</Banner>}
          {job.status === "done" && (
            <>
              {job.message && job.message !== "Render complete" && (
                <Banner kind="warn">{job.message}</Banner>
              )}
              {job.output_path && (
                <div className="video-wrap" style={{ marginTop: 12 }}>
                  <video key={job.output_path} src={fileUrl(job.output_path)} controls />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
