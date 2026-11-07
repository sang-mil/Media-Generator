import json
import unittest
from unittest.mock import Mock, patch

from pydantic import BaseModel, ConfigDict, Field

from app.ai import (
    CreativePackagingOutput, FactualClaim, PanelPlan, PanelVisualPrompt, StoryPlanOutput,
    _chat_structured, generate_webtoon, select_model,
)


class TinyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=3)


def fake_response(content, done_reason="stop", eval_count=20):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "message": {"role": "assistant", "content": content},
        "done_reason": done_reason,
        "load_duration": 1_000_000_000,
        "prompt_eval_count": 12,
        "eval_count": eval_count,
        "eval_duration": 2_000_000_000,
    }
    return response


class ModelSelectionTests(unittest.TestCase):
    def test_returns_none_when_no_models_installed(self):
        self.assertIsNone(select_model([]))

    def test_prefers_gemma4_when_no_model_is_configured(self):
        with patch("app.ai.OLLAMA_MODEL", ""):
            self.assertEqual(select_model(["qwen3.8:27b-q4_K_M", "gemma4:26b"]), "gemma4:26b")

    def test_respects_explicitly_configured_model(self):
        with patch("app.ai.OLLAMA_MODEL", "qwen3.8-code-api"):
            self.assertEqual(select_model(["gemma4:26b", "qwen3.8-code-api:latest"]), "qwen3.8-code-api:latest")

    def test_configured_model_without_latest_tag_matches_latest(self):
        with patch("app.ai.OLLAMA_MODEL", "gemma4:26b"):
            self.assertEqual(select_model(["gemma4:26b", "qwen2.5:7b"]), "gemma4:26b")


class StructuredOutputTests(unittest.TestCase):
    @patch("app.ai.requests.post")
    @patch("app.ai.ollama_status")
    def test_sends_json_schema_and_validates_response(self, mock_status, mock_post):
        mock_status.return_value = {"available": True, "selected_model": "gemma4:26b"}
        mock_post.return_value = fake_response('{"answer":"정상 응답"}')

        result, meta = _chat_structured(
            [{"role": "user", "content": "테스트"}],
            TinyOutput,
            num_predict=500,
        )

        self.assertEqual(result.answer, "정상 응답")
        self.assertEqual(meta["model"], "gemma4:26b")
        request_payload = mock_post.call_args.kwargs["json"]
        self.assertIsInstance(request_payload["format"], dict)
        self.assertIn("answer", request_payload["format"]["properties"])
        self.assertEqual(request_payload["options"]["num_predict"], 500)

    @patch("app.ai.requests.post")
    @patch("app.ai.ollama_status")
    def test_retries_when_generation_is_truncated(self, mock_status, mock_post):
        mock_status.return_value = {"available": True, "selected_model": "gemma4:26b"}
        mock_post.side_effect = [
            fake_response('{"answer":"cut', done_reason="length", eval_count=500),
            fake_response('{"answer":"완성된 응답"}', done_reason="stop", eval_count=40),
        ]

        result, meta = _chat_structured(
            [{"role": "user", "content": "테스트"}],
            TinyOutput,
            num_predict=500,
            max_retries=1,
        )

        self.assertEqual(result.answer, "완성된 응답")
        self.assertEqual(len(meta["attempts"]), 2)
        first_budget = mock_post.call_args_list[0].kwargs["json"]["options"]["num_predict"]
        second_budget = mock_post.call_args_list[1].kwargs["json"]["options"]["num_predict"]
        self.assertGreater(second_budget, first_budget)

    @patch("app.ai.requests.post")
    @patch("app.ai.ollama_status")
    def test_retries_when_schema_validation_fails(self, mock_status, mock_post):
        mock_status.return_value = {"available": True, "selected_model": "gemma4:26b"}
        mock_post.side_effect = [
            fake_response('{"wrong":"field"}'),
            fake_response('{"answer":"재시도 성공"}'),
        ]

        result, meta = _chat_structured(
            [{"role": "user", "content": "테스트"}],
            TinyOutput,
            num_predict=500,
            max_retries=1,
        )
        self.assertEqual(result.answer, "재시도 성공")
        self.assertEqual(meta["retry_count"], 1)

    @patch("app.ai.requests.post")
    @patch("app.ai.ollama_status")
    def test_raises_after_all_retries_fail(self, mock_status, mock_post):
        mock_status.return_value = {"available": True, "selected_model": "gemma4:26b"}
        mock_post.return_value = fake_response('{"wrong":"field"}')
        with self.assertRaises(RuntimeError):
            _chat_structured(
                [{"role": "user", "content": "테스트"}],
                TinyOutput,
                num_predict=300,
                max_retries=1,
            )


class GenerationPipelineTests(unittest.TestCase):
    @patch("app.ai._chat_structured")
    @patch("app.ai.ollama_status")
    def test_webtoon_pipeline_is_split_and_marks_claims_unverified_without_sources(self, mock_status, mock_chat):
        mock_status.return_value = {"available": True, "selected_model": "gemma4:26b"}
        plan = StoryPlanOutput(
            title="저장 공간 정리",
            hook="사진이 안 찍힌다면?",
            character_guide="Original friendly mascot with teal hoodie and round face.",
            panels=[
                PanelPlan(number=1, scene="사진을 찍으려는데 경고가 뜬다.", dialogue="어? 용량이 부족해!", key_information="저장 공간 부족 상황"),
                PanelPlan(number=2, scene="무엇을 지울지 고민한다.", dialogue="뭘 지워야 하지?", key_information="데이터 종류를 확인해야 함"),
                PanelPlan(number=3, scene="조력자가 데이터 종류를 설명한다.", dialogue="캐시와 원본은 달라!", key_information="캐시와 원본 구분"),
                PanelPlan(number=4, scene="백업을 확인하고 정리한다.", dialogue="먼저 백업부터!", key_information="삭제 전 백업 확인"),
            ],
            factual_claims=[FactualClaim(claim="캐시는 앱이 다시 만들 수 있는 임시 데이터다.", risk_level="medium", requires_current_source=False)],
            fact_check=["기종별 캐시 삭제 방법 확인"],
        )
        packaging = CreativePackagingOutput(
            panel_visual_prompts=[
                PanelVisualPrompt(panel_number=1, visual_prompt="A worried mascot looking at a phone, cozy room, no text."),
                PanelVisualPrompt(panel_number=2, visual_prompt="The mascot thinking beside a phone, simple background, no text."),
                PanelVisualPrompt(panel_number=3, visual_prompt="A helper character explaining three storage icons, no text."),
                PanelVisualPrompt(panel_number=4, visual_prompt="The mascot calmly checking phone backup, no text."),
            ],
            caption="저장 공간을 정리하기 전에 데이터 종류부터 확인하세요.",
            hashtags=["스마트폰", "디지털생활", "IT팁"],
        )
        mock_chat.side_effect = [(plan, {"model": "gemma4:26b", "retry_count": 0}), (packaging, {"model": "gemma4:26b", "retry_count": 0})]

        result = generate_webtoon({"title": "스마트폰 저장 공간", "category": "디지털 생활", "source_notes": ""})

        self.assertEqual(mock_chat.call_count, 2)
        self.assertEqual(len(result["panels"]), 4)
        self.assertEqual(result["technical_review"]["status"], "source_material_required")
        self.assertEqual(result["technical_review"]["claims"][0]["assessment"], "needs_verification")
        self.assertEqual(result["generation_meta"]["model"], "gemma4:26b")


if __name__ == "__main__":
    unittest.main()
