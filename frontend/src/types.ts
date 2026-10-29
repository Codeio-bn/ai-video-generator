export interface Scene {
  index: number;
  narration: string;
  visual: string;
  sound: string;
  duration: number;
  clip_path: string | null;
  narration_audio: string | null;
  status: "pending" | "generating" | "ready" | "error";
  cost: number;
}

export type VideoStatus = "draft" | "ready" | "producing" | "done" | "error";

export interface Video {
  id: string;
  scp_ref: string;
  title: string;
  authors: string;
  source_url: string;
  license: string;
  status: VideoStatus;
  progress: number;
  message: string;
  error: string;
  voice?: string;
  scenes: Scene[];
  narration_path: string | null;
  final_path: string | null;
  final_duration: number;
  cost_total: number;
  created_at: string;
}

export interface SystemStatus {
  ffmpeg_ok: boolean;
  openai_key_set: boolean;
  gemini_key_set: boolean;
  script_ok: boolean;
  script_detail: string;
  script_model: string;
  tts_ok: boolean;
  tts_detail: string;
  tts_voices: string[];
  veo_ok: boolean;
  veo_detail: string;
  veo_model: string;
  veo_price_per_sec: number;
  veo_clip_seconds: number;
}
