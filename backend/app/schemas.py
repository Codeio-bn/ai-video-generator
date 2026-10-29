"""Pydantic request models. Responses are plain dicts straight from sqlite."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    scp_number: str
    title: str = ""
    authors: str = ""
    source_url: str = ""
    license: str = "CC BY-SA 3.0"
    language: str = "en"
    style_bible: str = ""
    narrator_voice: str = ""
    target_episode_length: int = 30   # short TikTok by default
    source_text: str = ""
    monthly_budget_cap: float = 0


class ProjectUpdate(BaseModel):
    scp_number: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    language: Optional[str] = None
    style_bible: Optional[str] = None
    narrator_voice: Optional[str] = None
    target_episode_length: Optional[int] = None
    source_text: Optional[str] = None
    monthly_budget_cap: Optional[float] = None


class EpisodeCreate(BaseModel):
    part_number: int = 1
    title: str = ""
    hook: str = ""
    previously: str = ""
    narration_script: str = ""
    cliffhanger: str = ""


class EpisodeUpdate(BaseModel):
    part_number: Optional[int] = None
    title: Optional[str] = None
    hook: Optional[str] = None
    previously: Optional[str] = None
    narration_script: Optional[str] = None
    cliffhanger: Optional[str] = None
    status: Optional[str] = None


class ShotCreate(BaseModel):
    order_index: int = 0
    narration_excerpt: str = ""
    duration: float = 5.0
    shot_type: str = "still_image"
    prompt: str = ""
    camera_motion: str = ""
    audio_description: str = ""
    text_content: str = ""
    kenburns_direction: str = "in"


class ShotUpdate(BaseModel):
    order_index: Optional[int] = None
    narration_excerpt: Optional[str] = None
    duration: Optional[float] = None
    shot_type: Optional[str] = None
    prompt: Optional[str] = None
    camera_motion: Optional[str] = None
    audio_description: Optional[str] = None
    text_content: Optional[str] = None
    kenburns_direction: Optional[str] = None
    selected_take: Optional[int] = None
    status: Optional[str] = None


class ReorderRequest(BaseModel):
    shot_ids: list[int]


class ScriptGenRequest(BaseModel):
    source_text: str = ""
    num_parts: int = 0        # 0 = let the model choose
    guidance: str = ""
    replace: bool = False     # replace existing episodes instead of appending


class TTSRequest(BaseModel):
    voice: str = ""           # Kokoro voice id; defaults to project/narrator voice
    lang_code: str = ""       # optional override ('a' American, 'b' British)


class ShotGenRequest(BaseModel):
    avg_shot_secs: float = 6.0
    shot_type: str = "veo_video"   # default type for the generated shots
    replace: bool = True           # replace the episode's current shots


class AutoGenRequest(BaseModel):
    scp_ref: str = ""              # number/slug/URL; defaults to project's SCP number
    num_parts: int = 0             # 0 = let Gemini choose
    guidance: str = ""
    generate_shots: bool = True    # also build a shot list per episode
    avg_shot_secs: float = 6.0
    shot_type: str = "veo_video"
    replace: bool = True           # replace existing episodes


class RenderRequest(BaseModel):
    options: dict = {}
