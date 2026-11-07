import unittest
from unittest.mock import patch, Mock

from app.comfyui import _select_image_checkpoint, _workflow, _build_panel_prompt, _format_execution_error


class ComfyUIQualityTests(unittest.TestCase):
    def test_audio_checkpoint_is_not_selected_by_list_order(self):
        selected, error = _select_image_checkpoint([
            "ace_step_v1_3.5b.safetensors",
            "v1-5-pruned-emaonly.safetensors",
        ])
        self.assertEqual(selected, "v1-5-pruned-emaonly.safetensors")
        self.assertIsNone(error)

    def test_explicit_missing_checkpoint_fails_closed(self):
        selected, error = _select_image_checkpoint(
            ["v1-5-pruned-emaonly.safetensors"], "missing.safetensors"
        )
        self.assertIsNone(selected)
        self.assertIn("missing.safetensors", error)

    def test_workflow_uses_portrait_sd15_and_hires_pass(self):
        workflow = _workflow(
            "v1-5-pruned-emaonly.safetensors", "webtoon prompt", 123, "test/panel", hires_supported=True
        )
        self.assertEqual(workflow["6"]["inputs"]["width"], 512)
        self.assertEqual(workflow["6"]["inputs"]["height"], 640)
        self.assertEqual(workflow["7"]["inputs"]["sampler_name"], "dpmpp_2m")
        self.assertIn("10", workflow)
        self.assertIn("11", workflow)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["11", 0])

    def test_workflow_falls_back_without_hires_node(self):
        workflow = _workflow(
            "v1-5-pruned-emaonly.safetensors", "webtoon prompt", 123, "test/panel", hires_supported=False
        )
        self.assertNotIn("10", workflow)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["7", 0])

    def test_character_guide_is_repeated_in_each_panel_prompt(self):
        prompt = _build_panel_prompt({"scene": "카페에서 스마트폰을 든다"}, "woman with short black bob and yellow sweater", 2)
        self.assertIn("same recurring character design", prompt)
        self.assertIn("short black bob", prompt)
        self.assertIn("single comic panel", prompt)

    def test_comfyui_execution_error_is_readable(self):
        message = _format_execution_error([
            ["execution_error", {"node_id": "7", "node_type": "KSampler", "exception_message": "tensor mismatch"}]
        ])
        self.assertIn("KSampler", message)
        self.assertIn("tensor mismatch", message)


if __name__ == "__main__":
    unittest.main()
