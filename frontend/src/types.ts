export interface Project {
  id: number;
  scp_number: string;
  title: string;
  authors: string;
  source_url: string;
  license: string;
  language: string;
  style_bible: string;
  narrator_voice: string;
  target_episode_length: number;
  source_text: string;
  monthly_budget_cap: number;
  created_at: string;
}

export interface Episode {
  id: number;
  project_id: number;
  part_number: number;
  title: string;
  hook: string;
  previously: string;
  narration_script: string;
  cliffhanger: string;
  status: string;
  narration_audio_path: string | null;
  narration_words: string | null;
  music_path: string | null;
  last_render_path: string | null;
  created_at: string;
}

export type ShotType =
  | "veo_video"
  | "still_image"
  | "uploaded_media"
  | "text_card";

export interface Shot {
  id: number;
  episode_id: number;
  order_index: number;
  narration_excerpt: string;
  duration: number;
  shot_type: ShotType;
  prompt: string;
  camera_motion: string;
  audio_description: string;
  text_content: string;
  kenburns_direction: string;
  asset_path: string | null;
  takes: string | null;
  selected_take: number;
  status: string;
  cost: number;
}

export interface Job {
  id: number;
  episode_id: number;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  message: string;
  output_path: string | null;
  error: string | null;
}

export interface SystemStatus {
  ffmpeg: string | null;
  ffprobe: string | null;
  ffmpeg_ok: boolean;
  whisper_ok: boolean;
  whisper_detail: string;
  gemini_key_set: boolean;
  gemini_model: string;
  kokoro_ok: boolean;
  kokoro_detail: string;
  tts_voices: string[];
}

export interface ScriptGenResult {
  episodes: Episode[];
  model: string;
  cost: number;
  prompt_tokens: number;
  output_tokens: number;
}

export interface RenderOptions {
  show_title_card: boolean;
  show_end_card: boolean;
  title_card_seconds: number;
  end_card_seconds: number;
  captions: boolean;
  caption_mode: "word" | "phrase";
  film_grain: boolean;
  vignette: boolean;
  flicker: boolean;
  music: boolean;
  music_volume: number;
  duck_music: boolean;
}
