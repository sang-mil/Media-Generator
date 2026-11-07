import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import db


class DatabaseMigrationTests(unittest.TestCase):
    def test_v02_database_receives_v03_columns_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = db.DB_PATH
            db.DB_PATH = Path(temp_dir) / "old.sqlite3"
            try:
                with sqlite3.connect(db.DB_PATH) as conn:
                    conn.executescript("""
                    CREATE TABLE topics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        audience TEXT NOT NULL DEFAULT 'IT에 익숙하지 않은 일반 사용자',
                        format TEXT NOT NULL DEFAULT 'webtoon_carousel',
                        angle TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'queued',
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic_id INTEGER,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        format TEXT NOT NULL,
                        hook TEXT NOT NULL DEFAULT '',
                        panels_json TEXT NOT NULL DEFAULT '[]',
                        caption TEXT NOT NULL DEFAULT '',
                        hashtags_json TEXT NOT NULL DEFAULT '[]',
                        fact_check_json TEXT NOT NULL DEFAULT '[]',
                        character_guide TEXT NOT NULL DEFAULT '',
                        images_json TEXT NOT NULL DEFAULT '[]',
                        status TEXT NOT NULL DEFAULT 'draft',
                        post_url TEXT NOT NULL DEFAULT '',
                        published_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO topics(title, category, created_at) VALUES ('기존 주제', '디지털 생활', '2026-01-01');
                    INSERT INTO posts(title, category, format, created_at, updated_at) VALUES ('기존 게시물', '디지털 생활', 'webtoon_carousel', '2026-01-01', '2026-01-01');
                    """)
                db.init_db()
                with db.connect() as conn:
                    topic_columns = {row["name"] for row in conn.execute("PRAGMA table_info(topics)").fetchall()}
                    post_columns = {row["name"] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
                    topic = conn.execute("SELECT title, source_notes FROM topics WHERE id=1").fetchone()
                    post = conn.execute("SELECT title, technical_review_json, generation_meta_json FROM posts WHERE id=1").fetchone()
                self.assertIn("source_notes", topic_columns)
                self.assertIn("technical_review_json", post_columns)
                self.assertIn("generation_meta_json", post_columns)
                self.assertEqual(topic["title"], "기존 주제")
                self.assertEqual(post["title"], "기존 게시물")
                self.assertEqual(post["technical_review_json"], "{}")
            finally:
                db.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
