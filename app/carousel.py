from __future__ import annotations

import os
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


CANVAS_SIZE = (1080, 1350)
TEMPLATE_LABELS = {
    "character_explainer": "화이트 배경 · 캐릭터 설명형",
    "image_caption": "이미지 배경 · 검정 하단 설명형",
    "minimal_infographic": "미니멀 인포그래픽형",
}
DEFAULT_TEMPLATE = "character_explainer"


def normalize_template(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in TEMPLATE_LABELS else DEFAULT_TEMPLATE


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    names = (
        ["malgunbd.ttf", "NanumGothicBold.ttf", "NotoSansCJK-Bold.ttc", "segoeuib.ttf", "arialbd.ttf"]
        if bold
        else ["malgun.ttf", "NanumGothic.ttf", "NotoSansCJK-Regular.ttc", "segoeui.ttf", "arial.ttf"]
    )
    candidates = [windows / name for name in names]
    candidates.extend(
        Path(folder) / name
        for folder in (
            "/usr/share/fonts/truetype/nanum",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/opentype/noto",
            "/usr/share/fonts/truetype/dejavu",
        )
        for name in names
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    raise RuntimeError(
        "한글 합성용 글꼴을 찾지 못했습니다. Windows의 맑은 고딕(malgun.ttf)이 설치되어 있는지 확인하세요."
    )


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    paragraphs = str(text or "").replace("\r", "").split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            trial = current + char
            if current and draw.textlength(trial, font=font) > width:
                lines.append(current.rstrip())
                current = char.lstrip()
            else:
                current = trial
        if current:
            lines.append(current.rstrip())
    return lines or [""]


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    width: int,
    font: ImageFont.FreeTypeFont,
    fill: str,
    *,
    max_lines: int = 3,
    line_gap: int = 12,
) -> int:
    x, y = xy
    lines = _wrap_lines(draw, text, font, width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    line_height = max(font.size + line_gap, int(font.size * 1.22))
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _paste_rounded(
    canvas: Image.Image,
    source: Image.Image,
    bounds: tuple[int, int, int, int],
    *,
    fit: str = "contain",
    radius: int = 28,
    centering: tuple[float, float] = (0.5, 0.45),
) -> None:
    x1, y1, x2, y2 = bounds
    size = (x2 - x1, y2 - y1)
    if fit == "cover":
        image = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS, centering=centering)
    else:
        image = ImageOps.contain(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
    x = x1 + (size[0] - image.width) // 2
    y = y1 + (size[1] - image.height) // 2
    canvas.paste(image, (x, y), mask)


def _base_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = Image.new("RGB", CANVAS_SIZE, "#F8F9F7")
    return canvas, ImageDraw.Draw(canvas)


def _draw_header(draw: ImageDraw.ImageDraw, title: str, index: int, *, dark: bool = False) -> None:
    ink = "#FFFFFF" if dark else "#18221F"
    muted = "#D0D5D2" if dark else "#718079"
    draw.text((76, 54), "DIGITAL NOTES  /  EASY IT", font=_font(22, True), fill=muted)
    draw.text((932, 54), f"{index:02d} / 04", font=_font(22, True), fill=ink)


def _character_explainer(
    title: str,
    panel: dict[str, Any],
    source: Image.Image,
    index: int,
) -> Image.Image:
    canvas, draw = _base_canvas()
    _draw_header(draw, title, index)
    heading = title if index == 1 else str(panel.get("key_information") or panel.get("scene") or title)
    _draw_wrapped(draw, heading, (78, 125), 920, _font(58, True), "#17231F", max_lines=2, line_gap=10)

    draw.rounded_rectangle((68, 380, 548, 1040), radius=34, fill="#E9F0EA")
    _paste_rounded(canvas, source, (82, 394, 534, 1026), fit="contain", radius=26)

    draw.rounded_rectangle((588, 455, 1010, 875), radius=30, fill="#FFFFFF", outline="#E0E8E1", width=3)
    draw.text((630, 505), "캐릭터의 설명", font=_font(25, True), fill="#4D765C")
    _draw_wrapped(
        draw,
        str(panel.get("dialogue") or panel.get("key_information") or ""),
        (630, 565),
        340,
        _font(36, True),
        "#26352C",
        max_lines=6,
        line_gap=14,
    )

    draw.rounded_rectangle((68, 1080, 1010, 1260), radius=26, fill="#E6EEE8")
    draw.text((104, 1110), "핵심 정리", font=_font(23, True), fill="#477253")
    _draw_wrapped(
        draw,
        str(panel.get("key_information") or panel.get("dialogue") or ""),
        (104, 1152),
        860,
        _font(30, True),
        "#203128",
        max_lines=2,
        line_gap=8,
    )
    draw.text((78, 1300), "쉽게 배우는 디지털 생활", font=_font(18), fill="#87938B")
    return canvas


def _image_caption(
    title: str,
    panel: dict[str, Any],
    source: Image.Image,
    index: int,
) -> Image.Image:
    image_height = 900
    background = ImageOps.fit(
        source.convert("RGB"),
        (CANVAS_SIZE[0], image_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.38),
    )
    canvas = Image.new("RGB", CANVAS_SIZE, "#050505")
    canvas.paste(background, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, image_height, CANVAS_SIZE[0], CANVAS_SIZE[1]), fill="#090909")
    _draw_header(draw, title, index, dark=True)
    heading = title if index == 1 else str(panel.get("key_information") or panel.get("scene") or title)
    draw.text((76, 962), "한 장으로 이해하는 IT", font=_font(23, True), fill="#A8D6B3")
    _draw_wrapped(draw, heading, (76, 1008), 920, _font(52, True), "#FFFFFF", max_lines=2, line_gap=8)
    _draw_wrapped(
        draw,
        str(panel.get("dialogue") or ""),
        (78, 1174),
        910,
        _font(29),
        "#E8E8E8",
        max_lines=3,
        line_gap=8,
    )
    return canvas


def _minimal_infographic(
    title: str,
    panel: dict[str, Any],
    source: Image.Image,
    index: int,
) -> Image.Image:
    canvas, draw = _base_canvas()
    _draw_header(draw, title, index)
    heading = title if index == 1 else str(panel.get("key_information") or panel.get("scene") or title)
    _draw_wrapped(draw, heading, (78, 132), 920, _font(55, True), "#1B2922", max_lines=2, line_gap=10)

    draw.rounded_rectangle((70, 365, 420, 810), radius=30, fill="#EAF0EB")
    _paste_rounded(canvas, source, (86, 382, 404, 792), fit="contain", radius=24)

    draw.rounded_rectangle((458, 365, 1010, 810), radius=30, fill="#FFFFFF", outline="#E0E8E1", width=3)
    draw.text((505, 412), "쉽게 말하면", font=_font(26, True), fill="#4B7658")
    _draw_wrapped(
        draw,
        str(panel.get("dialogue") or ""),
        (505, 475),
        455,
        _font(34, True),
        "#27352D",
        max_lines=6,
        line_gap=13,
    )

    draw.rounded_rectangle((70, 870, 1010, 1205), radius=30, fill="#E6EEE8")
    draw.ellipse((112, 928, 208, 1024), fill="#4E795D")
    draw.text((143, 947), str(index), font=_font(42, True), fill="#FFFFFF")
    draw.text((245, 925), "기억할 포인트", font=_font(25, True), fill="#4B7658")
    _draw_wrapped(
        draw,
        str(panel.get("key_information") or panel.get("dialogue") or ""),
        (245, 978),
        710,
        _font(35, True),
        "#1E2B23",
        max_lines=4,
        line_gap=10,
    )
    draw.text((78, 1300), "쉽게 배우는 디지털 생활", font=_font(18), fill="#87938B")
    return canvas


def compose_carousel(
    post_id: int,
    title: str,
    panels: list[dict[str, Any]],
    images: list[dict[str, Any]],
    design_template: str = DEFAULT_TEMPLATE,
    generated_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Compose model-generated illustrations into Instagram-ready 1080x1350 slides."""
    if len(panels) != 4 or len(images) != 4:
        raise ValueError("Instagram 카드뉴스 합성에는 대본 4개와 원본 이미지 4개가 필요합니다.")

    template = normalize_template(design_template)
    root = Path(generated_dir) if generated_dir is not None else Path("generated")
    output_dir = root / str(post_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    renderers = {
        "character_explainer": _character_explainer,
        "image_caption": _image_caption,
        "minimal_infographic": _minimal_infographic,
    }
    renderer = renderers[template]
    rendered: list[dict[str, Any]] = []

    for index, (panel, image_info) in enumerate(zip(panels, images), start=1):
        filename = Path(str(image_info.get("filename") or "")).name
        if not filename:
            raise RuntimeError(f"{index}번 원본 이미지 파일명이 없습니다.")
        source_path = output_dir / filename
        if not source_path.is_file():
            raise RuntimeError(f"{index}번 원본 이미지를 찾을 수 없습니다: {source_path}")
        try:
            with Image.open(source_path) as opened:
                source = opened.convert("RGB")
        except OSError as exc:
            raise RuntimeError(f"{index}번 원본 이미지를 읽을 수 없습니다: {exc}") from exc

        slide = renderer(title, panel, source, index)
        slide_filename = f"slide_{index:02d}.png"
        slide_path = output_dir / slide_filename
        slide.save(slide_path, format="PNG", optimize=True)
        rendered.append(
            {
                **image_info,
                "carousel_filename": slide_filename,
                "carousel_url": f"/media/{post_id}/{slide_filename}",
                "template": template,
                "template_label": TEMPLATE_LABELS[template],
                "canvas_width": CANVAS_SIZE[0],
                "canvas_height": CANVAS_SIZE[1],
            }
        )

    zip_filename = "instagram_carousel.zip"
    zip_path = output_dir / zip_filename
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in rendered:
            archive.write(output_dir / item["carousel_filename"], arcname=item["carousel_filename"])
    for item in rendered:
        item["carousel_zip_url"] = f"/media/{post_id}/{zip_filename}"
    return rendered
