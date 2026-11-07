import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("benchmark_models.py")
spec = importlib.util.spec_from_file_location("benchmark_models", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class BenchmarkHarnessTests(unittest.TestCase):
    def test_extract_json_with_fence(self):
        self.assertEqual(mod.extract_json('```json\n{"ok": true}\n```'), {"ok": True})

    def test_resolve_exact_model(self):
        self.assertEqual(mod.resolve_model("gemma4:26b", ["gemma4:26b"]), "gemma4:26b")

    def test_resolve_unambiguous_base(self):
        self.assertEqual(mod.resolve_model("gemma4", ["gemma4:26b"]), "gemma4:26b")

    def test_does_not_guess_ambiguous_model(self):
        self.assertIsNone(mod.resolve_model("gemma4", ["gemma4:12b", "gemma4:26b"]))

    def test_comic_schema(self):
        panels = [{"number": i, "scene": "s", "dialogue": "d", "key_information": "k", "visual_prompt": "v"} for i in range(1, 5)]
        data = {"title": "t", "character_guide": "c", "panels": panels, "factual_claims": [], "fact_check": []}
        ok, notes = mod.validate_result("comic_storage_4panel", data)
        self.assertTrue(ok, notes)

    def test_technical_schema_flags_missing_categories(self):
        data = {"title": "t", "plain_language_explanation": "x", "storage_categories": [], "safe_steps": [], "device_version_caveat": "v", "factual_claims": [], "fact_check": []}
        ok, notes = mod.validate_result("technical_explainer_storage", data)
        self.assertFalse(ok)
        self.assertTrue(any("storage_categories" in n for n in notes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
