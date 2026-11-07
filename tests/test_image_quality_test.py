import unittest

from scripts.image_quality_test import (
    PROFILES,
    TEST_NEGATIVE_PROMPT,
    TEST_PROMPT,
    _build_run_plan,
    _safe_slug,
    build_workflow,
)


class ImageQualityExperimentTests(unittest.TestCase):
    def test_fixed_prompt_describes_one_scene_and_excludes_collage(self):
        self.assertIn("single", TEST_PROMPT.lower())
        self.assertIn("single scene", TEST_PROMPT.lower())
        self.assertIn("collage", TEST_NEGATIVE_PROMPT.lower())
        self.assertIn("sticker sheet", TEST_NEGATIVE_PROMPT.lower())

    def test_sd15_native_profile_uses_portrait_base_resolution(self):
        profile = PROFILES["sd15-native"]
        workflow = build_workflow(
            "v1-5-pruned-emaonly.safetensors",
            123,
            profile,
            "quality/native",
        )
        self.assertEqual(workflow["6"]["inputs"]["width"], 512)
        self.assertEqual(workflow["6"]["inputs"]["height"], 640)
        self.assertEqual(workflow["7"]["inputs"]["seed"], 123)
        self.assertNotIn("10", workflow)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["7", 0])

    def test_sd15_hires_profile_records_two_stage_workflow(self):
        profile = PROFILES["sd15-current-hires"]
        workflow = build_workflow(
            "v1-5-pruned-emaonly.safetensors",
            123,
            profile,
            "quality/hires",
        )
        self.assertEqual(profile.output_width, 768)
        self.assertEqual(profile.output_height, 960)
        self.assertEqual(workflow["10"]["inputs"]["scale_by"], 1.5)
        self.assertEqual(workflow["11"]["inputs"]["seed"], 124)
        self.assertEqual(workflow["11"]["inputs"]["denoise"], 0.28)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["11", 0])

    def test_sdxl_profile_starts_at_768_by_960_without_hires(self):
        profile = PROFILES["sdxl"]
        workflow = build_workflow(
            "DreamShaperXL.safetensors",
            456,
            profile,
            "quality/sdxl",
        )
        self.assertEqual(workflow["6"]["inputs"]["width"], 768)
        self.assertEqual(workflow["6"]["inputs"]["height"], 960)
        self.assertEqual(workflow["7"]["inputs"]["seed"], 456)
        self.assertNotIn("10", workflow)
        self.assertEqual(workflow["4"]["inputs"]["text"], TEST_PROMPT)
        self.assertEqual(workflow["5"]["inputs"]["text"], TEST_NEGATIVE_PROMPT)

    def test_run_plan_keeps_baseline_and_candidates_separate(self):
        baseline = _build_run_plan(
            "baseline",
            "v1-5-pruned-emaonly.safetensors",
            [],
            [],
        )
        self.assertEqual(
            [profile.name for _, profile in baseline],
            ["sd15-native", "sd15-current-hires"],
        )

        candidates = _build_run_plan(
            "candidates",
            "v1-5-pruned-emaonly.safetensors",
            ["other-sd15.safetensors"],
            ["DreamShaperXL.safetensors"],
        )
        self.assertEqual(
            [(model, profile.name) for model, profile in candidates],
            [
                ("other-sd15.safetensors", "sd15-native"),
                ("DreamShaperXL.safetensors", "sdxl"),
            ],
        )

    def test_model_filename_is_safely_converted_to_result_slug(self):
        self.assertEqual(
            _safe_slug("checkpoints/DreamShaper XL_v1.safetensors"),
            "DreamShaper-XL_v1",
        )


if __name__ == "__main__":
    unittest.main()
