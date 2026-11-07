from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                audience TEXT NOT NULL DEFAULT 'IT에 익숙하지 않은 일반 사용자',
                format TEXT NOT NULL DEFAULT 'webtoon_carousel',
                design_template TEXT NOT NULL DEFAULT 'character_explainer',
                angle TEXT NOT NULL DEFAULT '',
                source_notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                format TEXT NOT NULL,
                design_template TEXT NOT NULL DEFAULT 'character_explainer',
                hook TEXT NOT NULL DEFAULT '',
                panels_json TEXT NOT NULL DEFAULT '[]',
                caption TEXT NOT NULL DEFAULT '',
                hashtags_json TEXT NOT NULL DEFAULT '[]',
                fact_check_json TEXT NOT NULL DEFAULT '[]',
                technical_review_json TEXT NOT NULL DEFAULT '{}',
                generation_meta_json TEXT NOT NULL DEFAULT '{}',
                character_guide TEXT NOT NULL DEFAULT '',
                images_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft',
                post_url TEXT NOT NULL DEFAULT '',
                published_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL UNIQUE REFERENCES posts(id) ON DELETE CASCADE,
                measured_at TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                reach INTEGER NOT NULL DEFAULT 0,
                likes INTEGER NOT NULL DEFAULT 0,
                comments INTEGER NOT NULL DEFAULT 0,
                shares INTEGER NOT NULL DEFAULT 0,
                saves INTEGER NOT NULL DEFAULT 0,
                profile_visits INTEGER NOT NULL DEFAULT 0,
                follows INTEGER NOT NULL DEFAULT 0,
                link_clicks INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            );
            """
        )
        # Lightweight forward-only migrations for existing v0.1 databases.
        post_columns = {row["name"] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
        if "character_guide" not in post_columns:
            conn.execute("ALTER TABLE posts ADD COLUMN character_guide TEXT NOT NULL DEFAULT ''")
        if "images_json" not in post_columns:
            conn.execute("ALTER TABLE posts ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]'")
        if "technical_review_json" not in post_columns:
            conn.execute("ALTER TABLE posts ADD COLUMN technical_review_json TEXT NOT NULL DEFAULT '{}'")
        if "generation_meta_json" not in post_columns:
            conn.execute("ALTER TABLE posts ADD COLUMN generation_meta_json TEXT NOT NULL DEFAULT '{}'")

        topic_columns = {row["name"] for row in conn.execute("PRAGMA table_info(topics)").fetchall()}
        if "source_notes" not in topic_columns:
            conn.execute("ALTER TABLE topics ADD COLUMN source_notes TEXT NOT NULL DEFAULT ''")
        if "design_template" not in topic_columns:
            conn.execute("ALTER TABLE topics ADD COLUMN design_template TEXT NOT NULL DEFAULT 'character_explainer'")
        if "design_template" not in post_columns:
            conn.execute("ALTER TABLE posts ADD COLUMN design_template TEXT NOT NULL DEFAULT 'character_explainer'")

        count = conn.execute("SELECT COUNT(*) AS n FROM topics").fetchone()["n"]
        if count == 0:
            seed_topics = [
                ("스마트폰 저장 공간이 부족해지는 진짜 이유", "디지털 생활", "webtoon_carousel", "흔한 오해를 바로잡는 4컷 설명"),
                ("브라우저 탭을 많이 열면 컴퓨터가 느려질까?", "컴퓨터 기초", "webtoon_carousel", "일상적인 상황에서 원리 설명"),
                ("공용 와이파이에서 주의해야 할 행동 3가지", "디지털 안전", "webtoon_carousel", "생활 속 보안 습관"),
                ("무료 온라인 도구를 사용할 때 개인정보를 확인하는 법", "웹 도구", "webtoon_carousel", "체크리스트형 콘텐츠"),
                ("AI에게 질문할 때 결과가 달라지는 이유", "AI 기초", "webtoon_carousel", "나쁜 질문과 좋은 질문 비교"),
            ]
            conn.executemany(
                "INSERT INTO topics(title, category, format, angle, created_at) VALUES (?, ?, ?, ?, ?)",
                [(t, c, f, a, now_iso()) for t, c, f, a in seed_topics],
            )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def decode_post(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for field in ("panels_json", "hashtags_json", "fact_check_json", "images_json", "technical_review_json", "generation_meta_json"):

        try:
            result[field.removesuffix("_json")] = json.loads(result.pop(field) or "[]")
        except json.JSONDecodeError:
            result[field.removesuffix("_json")] = {} if field.endswith("_json") and field in ("technical_review_json", "generation_meta_json") else []
    return result
