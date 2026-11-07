from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .ai import generate_topic_ideas, generate_webtoon, ollama_status, unload_model
from .comfyui import generate_panels, get_status as comfyui_status
from .carousel import compose_carousel, normalize_template
from .config import GENERATED_DIR
from .learning import build_recommendations

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Self-improving Media Pipeline", version="0.5.0")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/media", StaticFiles(directory=GENERATED_DIR), name="media")


class TopicCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    category: str = Field(min_length=2, max_length=60)
    audience: str = Field(default="IT에 익숙하지 않은 일반 사용자", max_length=160)
    format: str = Field(default="webtoon_carousel", max_length=40)
    design_template: Literal["character_explainer", "image_caption", "minimal_infographic"] = "character_explainer"
    angle: str = Field(default="일상적인 문제를 쉽고 재미있게 설명", max_length=300)
    source_notes: str = Field(default="", max_length=12000)


class MetricsInput(BaseModel):
    views: int = Field(default=0, ge=0)
    reach: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    profile_visits: int = Field(default=0, ge=0)
    follows: int = Field(default=0, ge=0)
    link_clicks: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=1000)


class PublishMark(BaseModel):
    post_url: str = Field(min_length=5, max_length=500)
    confirmed: bool = False


def _create_post(topic: dict[str, Any]) -> dict[str, Any]:
    unload_result: dict[str, Any] = {"attempted": False, "unloaded": False, "reason": "not_run"}
    try:
        generated = generate_webtoon(topic)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 대본 생성 실패: {exc}") from exc
    finally:
        # Keep the model warm across planning/packaging/review stages, then
        # release it once before ComfyUI image generation needs the GPU.
        try:
            selected = ollama_status().get("selected_model")
            unload_result = unload_model(selected)
        except Exception as exc:
            unload_result = {"attempted": True, "unloaded": False, "reason": str(exc)}

    generated.setdefault("generation_meta", {})["model_unload"] = unload_result
    now = db.now_iso()
    with db.connect() as conn:
        cur = conn.execute(
            """INSERT INTO posts(topic_id, title, category, format, design_template, hook, panels_json, caption,
               hashtags_json, fact_check_json, technical_review_json, generation_meta_json,
               character_guide, images_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', 'draft', ?, ?)""",
            (
                topic["id"],
                str(generated.get("title") or topic["title"]),
                topic["category"],
                topic["format"],
                normalize_template(topic.get("design_template")),
                str(generated.get("hook") or ""),
                json.dumps(generated.get("panels", []), ensure_ascii=False),
                str(generated.get("caption") or ""),
                json.dumps(generated.get("hashtags", []), ensure_ascii=False),
                json.dumps(generated.get("fact_check", []), ensure_ascii=False),
                json.dumps(generated.get("technical_review", {}), ensure_ascii=False),
                json.dumps(generated.get("generation_meta", {}), ensure_ascii=False),
                str(generated.get("character_guide") or ""),
                now,
                now,
            ),
        )
        post_id = cur.lastrowid
        conn.execute("UPDATE topics SET status='drafted' WHERE id=?", (topic["id"],))
        row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    return db.decode_post(row)


def _generate_images_for_post(post: dict[str, Any]) -> dict[str, Any]:
    try:
        template = normalize_template(post.get("design_template"))
        images = generate_panels(
            int(post["id"]),
            post.get("panels", []),
            post.get("character_guide", ""),
            design_template=template,
        )
        composition_warning = None
        try:
            images = compose_carousel(
                int(post["id"]),
                str(post.get("title") or "디지털 생활"),
                post.get("panels", []),
                images,
                design_template=template,
                generated_dir=GENERATED_DIR,
            )
        except Exception as exc:
            # Keep original images when typography/layout rendering fails.
            composition_warning = str(exc)

        with db.connect() as conn:
            conn.execute(
                "UPDATE posts SET images_json=?, updated_at=? WHERE id=?",
                (json.dumps(images, ensure_ascii=False), db.now_iso(), post["id"]),
            )
            row = conn.execute("SELECT * FROM posts WHERE id=?", (post["id"],)).fetchone()
        return {
            "status": "generated" if not composition_warning else "generated_with_warnings",
            "post": db.decode_post(row),
            "images": images,
            "composition_warning": composition_warning,
        }
    except Exception as exc:
        return {"status": "not_generated", "error": str(exc), "images": []}


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": "Self-improving Media Pipeline", "version": "0.5.0", "publish_mode": "human_approval_required"}


@app.get("/api/system/status")
def system_status() -> dict[str, Any]:
    ollama = ollama_status()
    comfy = comfyui_status()
    return {
        "app": {"available": True, "version": "0.5.0"},
        "ollama": ollama,
        "comfyui": comfy,
        "pipeline_ready": bool(ollama.get("available") and ollama.get("selected_model")),
        "image_generation_ready": bool(comfy.get("available") and comfy.get("selected_checkpoint")),
        "publishing": {"ready": False, "mode": "manual_approval", "message": "Meta 개발자 앱과 계정 권한을 확인하기 전까지 게시 전 승인을 유지합니다."},
    }


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with db.connect() as conn:
        topics = conn.execute("SELECT COUNT(*) AS n FROM topics WHERE status='queued'").fetchone()["n"]
        drafts = conn.execute("SELECT COUNT(*) AS n FROM posts WHERE status IN ('draft','approved')").fetchone()["n"]
        published = conn.execute("SELECT COUNT(*) AS n FROM posts WHERE status='published'").fetchone()["n"]
        metrics_count = conn.execute("SELECT COUNT(*) AS n FROM metrics").fetchone()["n"]
        recent = conn.execute(
            """SELECT p.id, p.title, p.category, p.format, p.status, p.created_at,
                      m.reach, m.views, m.likes, m.comments, m.shares, m.saves, m.follows
               FROM posts p LEFT JOIN metrics m ON m.post_id=p.id
               ORDER BY p.id DESC LIMIT 6"""
        ).fetchall()
    return {"queued_topics": topics, "drafts": drafts, "published": published, "measured_posts": metrics_count, "recent": [dict(r) for r in recent]}


@app.get("/api/topics")
def list_topics() -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/topics")
def create_topic(payload: TopicCreate) -> dict[str, Any]:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO topics(title, category, audience, format, design_template, angle, source_notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (payload.title, payload.category, payload.audience, payload.format, payload.design_template, payload.angle, payload.source_notes, db.now_iso()),
        )
        topic_id = cur.lastrowid
        row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
    return dict(row)


@app.post("/api/pipeline/run-next")
def run_next_pipeline() -> dict[str, Any]:
    """Create the next script and try to render its four panels in one guided action."""
    with db.connect() as conn:
        topic_row = conn.execute("SELECT * FROM topics WHERE status='queued' ORDER BY id ASC LIMIT 1").fetchone()

    generated_ideas = False
    if not topic_row:
        try:
            ideas = generate_topic_ideas(5)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"새 주제 자동 발굴 실패: {exc}") from exc
        if not ideas:
            raise HTTPException(status_code=502, detail="AI가 사용할 수 있는 새 주제를 만들지 못했습니다.")
        with db.connect() as conn:
            for idea in ideas:
                conn.execute(
                    "INSERT INTO topics(title, category, audience, format, design_template, angle, source_notes, created_at) VALUES (?, ?, ?, 'webtoon_carousel', 'character_explainer', ?, '', ?)",
                    (idea["title"], idea["category"], idea["audience"], idea["angle"], db.now_iso()),
                )
            topic_row = conn.execute("SELECT * FROM topics WHERE status='queued' ORDER BY id ASC LIMIT 1").fetchone()
        generated_ideas = True

    post = _create_post(dict(topic_row))
    image_result = _generate_images_for_post(post)
    with db.connect() as conn:
        final_row = conn.execute("SELECT * FROM posts WHERE id=?", (post["id"],)).fetchone()
    return {
        "status": "draft_created",
        "generated_topic_ideas": generated_ideas,
        "post": db.decode_post(final_row),
        "images": image_result,
        "next_step": "사실 확인과 게시물 검수를 완료한 뒤 승인하세요. Instagram 자동 발행은 Meta API 연결 후 별도로 활성화합니다.",
    }


@app.post("/api/topics/{topic_id}/generate")
def create_from_topic(topic_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        topic_row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
    if not topic_row:
        raise HTTPException(status_code=404, detail="주제를 찾을 수 없습니다.")
    return _create_post(dict(topic_row))


@app.get("/api/posts")
def list_posts() -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    return [db.decode_post(r) for r in rows]


@app.post("/api/posts/{post_id}/generate-images")
def create_post_images(post_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
    result = _generate_images_for_post(db.decode_post(row))
    if result["status"] not in ("generated", "generated_with_warnings"):
        raise HTTPException(status_code=503, detail=result["error"])
    return result["post"]


@app.post("/api/posts/{post_id}/approve")
def approve_post(post_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        cur = conn.execute("UPDATE posts SET status='approved', updated_at=? WHERE id=? AND status='draft'", (db.now_iso(), post_id))
        if cur.rowcount == 0:
            row = conn.execute("SELECT status FROM posts WHERE id=?", (post_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
            if row["status"] != "approved":
                raise HTTPException(status_code=409, detail="초안 상태의 게시물만 승인할 수 있습니다.")
        row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    return db.decode_post(row)


@app.post("/api/posts/{post_id}/mark-published")
def mark_published(post_id: int, payload: PublishMark) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Instagram 앱에서 직접 게시를 완료했음을 확인해야 합니다.")
    with db.connect() as conn:
        row = conn.execute("SELECT status FROM posts WHERE id=?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
        if row["status"] not in ("approved", "published"):
            raise HTTPException(status_code=409, detail="승인된 게시물만 게시 완료 처리할 수 있습니다.")
        conn.execute(
            "UPDATE posts SET status='published', post_url=?, published_at=?, updated_at=? WHERE id=?",
            (payload.post_url, db.now_iso(), db.now_iso(), post_id),
        )
        updated = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    return db.decode_post(updated)


@app.post("/api/posts/{post_id}/metrics")
def save_metrics(post_id: int, payload: MetricsInput) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute("SELECT id, status FROM posts WHERE id=?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다.")
        if row["status"] != "published":
            raise HTTPException(status_code=409, detail="게시 완료 처리된 게시물에만 성과를 입력할 수 있습니다.")
        values = payload.model_dump()
        conn.execute(
            """INSERT INTO metrics(post_id, measured_at, views, reach, likes, comments, shares, saves,
               profile_visits, follows, link_clicks, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(post_id) DO UPDATE SET measured_at=excluded.measured_at,
               views=excluded.views, reach=excluded.reach, likes=excluded.likes,
               comments=excluded.comments, shares=excluded.shares, saves=excluded.saves,
               profile_visits=excluded.profile_visits, follows=excluded.follows,
               link_clicks=excluded.link_clicks, notes=excluded.notes""",
            (post_id, db.now_iso(), values["views"], values["reach"], values["likes"], values["comments"], values["shares"], values["saves"], values["profile_visits"], values["follows"], values["link_clicks"], values["notes"]),
        )
        saved = conn.execute("SELECT * FROM metrics WHERE post_id=?", (post_id,)).fetchone()
    return dict(saved)


@app.get("/api/recommendations")
def recommendations() -> dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT p.id, p.title, p.category, p.format,
                      m.measured_at, m.views, m.reach, m.likes, m.comments, m.shares, m.saves,
                      m.profile_visits, m.follows, m.link_clicks
               FROM posts p LEFT JOIN metrics m ON m.post_id=p.id
               WHERE p.status='published' ORDER BY p.id DESC"""
        ).fetchall()
    normalized = []
    for row in rows:
        item = dict(row)
        item["metrics"] = {key: item.get(key, 0) or 0 for key in ("views", "reach", "likes", "comments", "shares", "saves", "profile_visits", "follows", "link_clicks")}
        normalized.append(item)
    return build_recommendations(normalized)
