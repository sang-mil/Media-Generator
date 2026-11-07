import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from app.carousel import CANVAS_SIZE, TEMPLATE_LABELS, compose_carousel, normalize_template, _font


class CarouselRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.post_dir = self.root / "42"
        self.post_dir.mkdir(parents=True)
        self.panels = [
            {
                "number": index,
                "scene": f"장면 {index}",
                "dialogue": f"이 부분을 쉽게 설명합니다. {index}번 장면입니다.",
                "key_information": f"기억할 핵심 정보 {index}입니다.",
            }
            for index in range(1, 5)
        ]
        self.images = []
        for index in range(1, 5):
            filename = f"panel_{index:02d}.png"
            Image.new("RGB", (512, 640), (220 - index * 10, 230, 220)).save(self.post_dir / filename)
            self.images.append({"panel": str(index), "filename": filename, "url": f"/media/42/{filename}"})

    def tearDown(self):
        self.temp.cleanup()

    def test_all_templates_render_four_instagram_portrait_slides_and_zip(self):
        try:
            _font(18)
        except RuntimeError as exc:
            self.skipTest(str(exc))

        for template in TEMPLATE_LABELS:
            with self.subTest(template=template):
                rendered = compose_carousel(
                    42,
                    "스마트폰을 더 편하게 쓰는 방법",
                    self.panels,
                    self.images,
                    design_template=template,
                    generated_dir=self.root,
                )
                self.assertEqual(len(rendered), 4)
                self.assertEqual(rendered[0]["template"], template)
                self.assertEqual(rendered[0]["canvas_width"], 1080)
                self.assertEqual(rendered[0]["canvas_height"], 1350)
                for item in rendered:
                    with Image.open(self.post_dir / item["carousel_filename"]) as image:
                        self.assertEqual(image.size, CANVAS_SIZE)
                zip_path = self.post_dir / "instagram_carousel.zip"
                self.assertTrue(zip_path.is_file())
                with zipfile.ZipFile(zip_path) as archive:
                    self.assertEqual(len(archive.namelist()), 4)

    def test_unknown_template_falls_back_to_character_explainer(self):
        self.assertEqual(normalize_template("untrusted-template"), "character_explainer")

    def test_renderer_requires_exactly_four_panels_and_images(self):
        with self.assertRaises(ValueError):
            compose_carousel(42, "test", self.panels[:3], self.images, generated_dir=self.root)


if __name__ == "__main__":
    unittest.main()
