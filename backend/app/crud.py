"""Thin CRUD helpers over the sqlite layer. All functions return plain dicts."""

from __future__ import annotations

from typing import Optional

from .database import get_conn, row_to_dict, rows_to_list

# --------------------------------------------------------------------------- #
# projects
# --------------------------------------------------------------------------- #

PROJECT_FIELDS = [
    "scp_number", "title", "authors", "source_url", "license", "language",
    "style_bible", "narrator_voice", "target_episode_length", "source_text",
    "monthly_budget_cap",
]


def create_project(data: dict) -> dict:
    cols = [f for f in PROJECT_FIELDS if f in data]
    placeholders = ", ".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO projects ({', '.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )
        conn.commit()
        return get_project(cur.lastrowid)


def get_project(pid: int) -> Optional[dict]:
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        )


def list_projects() -> list[dict]:
    with get_conn() as conn:
        return rows_to_list(
            conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        )


def update_project(pid: int, data: dict) -> Optional[dict]:
    cols = [f for f in PROJECT_FIELDS if f in data]
    if cols:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE projects SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                [data[c] for c in cols] + [pid],
            )
            conn.commit()
    return get_project(pid)


def delete_project(pid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
        conn.commit()


# --------------------------------------------------------------------------- #
# episodes
# --------------------------------------------------------------------------- #

EPISODE_FIELDS = [
    "project_id", "part_number", "title", "hook", "previously",
    "narration_script", "cliffhanger", "status", "narration_audio_path",
    "narration_words", "music_path", "last_render_path",
]


def create_episode(data: dict) -> dict:
    cols = [f for f in EPISODE_FIELDS if f in data]
    placeholders = ", ".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO episodes ({', '.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )
        conn.commit()
        return get_episode(cur.lastrowid)


def get_episode(eid: int) -> Optional[dict]:
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()
        )


def list_episodes(project_id: int) -> list[dict]:
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM episodes WHERE project_id=? ORDER BY part_number",
                (project_id,),
            ).fetchall()
        )


def update_episode(eid: int, data: dict) -> Optional[dict]:
    cols = [f for f in EPISODE_FIELDS if f in data]
    if cols:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE episodes SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                [data[c] for c in cols] + [eid],
            )
            conn.commit()
    return get_episode(eid)


def delete_episode(eid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM episodes WHERE id=?", (eid,))
        conn.commit()


# --------------------------------------------------------------------------- #
# shots
# --------------------------------------------------------------------------- #

SHOT_FIELDS = [
    "episode_id", "order_index", "narration_excerpt", "duration", "shot_type",
    "prompt", "camera_motion", "audio_description", "text_content",
    "kenburns_direction", "asset_path", "takes", "selected_take", "status", "cost",
]


def create_shot(data: dict) -> dict:
    cols = [f for f in SHOT_FIELDS if f in data]
    placeholders = ", ".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO shots ({', '.join(cols)}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )
        conn.commit()
        return get_shot(cur.lastrowid)


def get_shot(sid: int) -> Optional[dict]:
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone()
        )


def list_shots(episode_id: int) -> list[dict]:
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM shots WHERE episode_id=? ORDER BY order_index, id",
                (episode_id,),
            ).fetchall()
        )


def update_shot(sid: int, data: dict) -> Optional[dict]:
    cols = [f for f in SHOT_FIELDS if f in data]
    if cols:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE shots SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                [data[c] for c in cols] + [sid],
            )
            conn.commit()
    return get_shot(sid)


def delete_shot(sid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM shots WHERE id=?", (sid,))
        conn.commit()


# --------------------------------------------------------------------------- #
# render jobs
# --------------------------------------------------------------------------- #

def create_job(episode_id: int, kind: str, options: str) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO render_jobs (episode_id, kind, status, options) "
            "VALUES (?, ?, 'queued', ?)",
            (episode_id, kind, options),
        )
        conn.commit()
        return get_job(cur.lastrowid)


def get_job(jid: int) -> Optional[dict]:
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM render_jobs WHERE id=?", (jid,)).fetchone()
        )


def latest_job_for_episode(episode_id: int) -> Optional[dict]:
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM render_jobs WHERE episode_id=? "
                "ORDER BY id DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
        )


def update_job(jid: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = None  # set via SQL below
    cols = [k for k in fields if k != "updated_at"]
    sets = ", ".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now')"
    with get_conn() as conn:
        conn.execute(
            f"UPDATE render_jobs SET {sets} WHERE id=?",
            [fields[c] for c in cols] + [jid],
        )
        conn.commit()
