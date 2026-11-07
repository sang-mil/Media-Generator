import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app


class ApiV03Tests(unittest.TestCase):
    def test_topic_source_notes_and_review_metadata_are_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = db.DB_PATH
            db.DB_PATH = Path(temp_dir) / "api.sqlite3"
            generated = {
                "title": "테스트 웹툰",
                "hook": "테스트 훅",
                "character_guide": "Original mascot with teal hoodie.",
                "panels": [
                    {"number": i, "scene": f"장면 {i}", "dialogue": f"대사 {i}", "key_information": f"정보 {i}", "visual_prompt": f"Panel {i} visual prompt, no text."}
                    for i in range(1, 5)
                ],
                "caption": "테스트 캡션입니다.",
                "hashtags": ["IT팁", "디지털생활", "테스트"],
                "fact_check": ["출처 확인 필요"],
                "technical_review": {"status": "source_material_required", "summary": "출처 자료가 필요합니다.", "claims": [], "critical_issues": [], "human_review_required": True},
                "generation_meta": {"model": "gemma4:26b", "prompt_version": "v0.3.0", "pipeline": []},
            }
            try:
                with patch("app.main.generate_webtoon", return_value=generated), patch("app.main.ollama_status", return_value={"selected_model": "gemma4:26b"}), patch("app.main.unload_model", return_value={"unloaded": True}):
                    with TestClient(app) as client:
                        topic_response = client.post("/api/topics", json={
                            "title": "스마트폰 저장 공간",
                            "category": "디지털 생활",
                            "source_notes": "Android 공식 문서 발췌 테스트",
                        })
                        self.assertEqual(topic_response.status_code, 200)
                        topic = topic_response.json()
                        self.assertEqual(topic["source_notes"], "Android 공식 문서 발췌 테스트")

                        post_response = client.post(f"/api/topics/{topic['id']}/generate")
                        self.assertEqual(post_response.status_code, 200)
                        post = post_response.json()
                        self.assertEqual(len(post["panels"]), 4)
                        self.assertEqual(post["technical_review"]["status"], "source_material_required")
                        self.assertEqual(post["generation_meta"]["model"], "gemma4:26b")
            finally:
                db.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
