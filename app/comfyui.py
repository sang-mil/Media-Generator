from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from .config import (
    COMFYUI_BASE_URL,
    COMFYUI_TIMEOUT,
    COMFYUI_CHECKPOINT,
    COMFYUI_WIDTH,
    COMFYUI_HEIGHT,
    COMFYUI_STEPS,
    COMFYUI_CFG,
    COMFYUI_SAMPLER,
    COMFYUI_SCHEDULER,
    COMFYUI_HIRES_ENABLED,
    COMFYUI_HIRES_SCALE,
    COMFYUI_HIRES_METHOD,
    COMFYUI_HIRES_STEPS,
    COMFYUI_HIRES_CFG,
    COMFYUI_HIRES_DENOISE,
    COMFYUI_SEED_MODE,
    GENERATED_DIR,
)

AUDIO_CHECKPOINT_MARKERS = (
    "ace_step", "ace-step", "stable-audio", "stable_audio", "musicgen", "audio"
)

WEBTOON_POSITIVE_STYLE = (
    "(masterpiece:1.08), (best quality:1.12), polished 2D Korean webtoon illustration, "
    "professional digital comic art, clean confident lineart, consistent line weight, "
    "appealing expressive character design, clear facial expressions, readable body language, "
    "controlled cel shading, subtle soft shadows, harmonious warm pastel color palette, "
    "clear silhouette, balanced composition, detailed but uncluttered background, "
    "portrait 4:5 composition, single comic panel, one coherent moment, "
    "no panel grid, no collage, no text, no lettering, no logo, no watermark"
)

WEBTOON_NEGATIVE = (
    "(worst quality:1.3), (low quality:1.2), lowres, blurry, out of focus, jpeg artifacts, "
    "noisy image, oversharpened, oversaturated, poorly drawn face, asymmetrical eyes, "
    "bad anatomy, malformed hands, extra fingers, missing fingers, fused fingers, "
    "extra arms, extra legs, duplicate person, multiple heads, distorted face, "
    "inconsistent character design, different hairstyle, different outfit, cropped head, "
    "out of frame, text, letters, subtitles, speech bubble, watermark, signature, logo, "
    "photorealistic, 3d render, collage, split screen, multiple panels"
)


def _select_image_checkpoint(
    checkpoints: list[str], preferred: str = COMFYUI_CHECKPOINT
) -> tuple[str | None, str | None]:
    """Select an explicitly configured image checkpoint; never choose by list order."""
    names = [str(name) for name in checkpoints]
    if preferred:
        if preferred in names:
            if any(marker in preferred.lower() for marker in AUDIO_CHECKPOINT_MARKERS):
                return None, f"'{preferred}'은 오디오 모델로 보입니다. 이미지 체크포인트를 지정하세요."
            return preferred, None
        return None, (
            f"설정한 이미지 체크포인트 '{preferred}'를 찾을 수 없습니다. "
            f"ComfyUI에서 사용 가능한 체크포인트: {', '.join(names) or '(없음)'}"
        )

    image_candidates = [
        name for name in names
        if not any(marker in name.lower() for marker in AUDIO_CHECKPOINT_MARKERS)
    ]
    if image_candidates:
        return image_candidates[0], None
    return None, "일반 이미지 생성에 사용할 체크포인트가 없습니다. 오디오 모델은 이미지 워크플로에서 사용할 수 없습니다."


def _object_info(node_name: str) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{COMFYUI_BASE_URL}/object_info/{node_name}", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get(node_name) if isinstance(data, dict) else None
    except (requests.RequestException, ValueError):
        return None


def _quality_info(hires_supported: bool = False) -> dict[str, Any]:
    return {
        "preset": "sd15_webtoon_portrait_v1",
        "width": COMFYUI_WIDTH,
        "height": COMFYUI_HEIGHT,
        "steps": COMFYUI_STEPS,
        "cfg": COMFYUI_CFG,
        "sampler": COMFYUI_SAMPLER,
        "scheduler": COMFYUI_SCHEDULER,
        "hires_requested": COMFYUI_HIRES_ENABLED,
        "hires_supported": bool(hires_supported),
        "hires_scale": COMFYUI_HIRES_SCALE if COMFYUI_HIRES_ENABLED and hires_supported else 1.0,
        "character_consistency": "shared_seed_and_repeated_character_guide",
        "reference_adapter": "not_configured",
    }


def get_status() -> dict[str, Any]:
    try:
        response = requests.get(f"{COMFYUI_BASE_URL}/system_stats", timeout=3)
        response.raise_for_status()
        info = _object_info("CheckpointLoaderSimple") or {}
        required = info.get("input", {}).get("required", {})
        checkpoints = required.get("ckpt_name", [[]])[0] if required else []
        selected, selection_error = _select_image_checkpoint(checkpoints)
        hires_supported = bool(_object_info("LatentUpscaleBy"))
        quality = _quality_info(hires_supported)
        warning = None
        if COMFYUI_HIRES_ENABLED and not hires_supported:
            warning = "ComfyUI LatentUpscaleBy 노드를 찾지 못해 1차 생성만 사용합니다."
        return {
            "available": True,
            "url": COMFYUI_BASE_URL,
            "checkpoints": checkpoints,
            "selected_checkpoint": selected,
            "error": selection_error,
            "quality": quality,
            "warning": warning,
        }
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        return {
            "available": False,
            "url": COMFYUI_BASE_URL,
            "checkpoints": [],
            "selected_checkpoint": None,
            "error": str(exc),
            "quality": _quality_info(False),
            "warning": None,
        }


def _workflow(
    checkpoint: str,
    prompt: str,
    seed: int,
    filename_prefix: str,
    *,
    hires_supported: bool = True,
) -> dict[str, Any]:
    """Build an SD 1.5 workflow with an optional latent high-resolution refinement pass."""
    workflow: dict[str, Any] = {
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 1]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": WEBTOON_NEGATIVE, "clip": ["3", 1]}},
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": COMFYUI_WIDTH, "height": COMFYUI_HEIGHT, "batch_size": 1},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": COMFYUI_STEPS,
                "cfg": COMFYUI_CFG,
                "sampler_name": COMFYUI_SAMPLER,
                "scheduler": COMFYUI_SCHEDULER,
                "denoise": 1.0,
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
    }

    final_samples: list[Any] = ["7", 0]
    if COMFYUI_HIRES_ENABLED and hires_supported and COMFYUI_HIRES_SCALE > 1.0:
        workflow["10"] = {
            "class_type": "LatentUpscaleBy",
            "inputs": {
                "samples": ["7", 0],
                "upscale_method": COMFYUI_HIRES_METHOD,
                "scale_by": COMFYUI_HIRES_SCALE,
            },
        }
        workflow["11"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": (seed + 1) % (2**32),
                "steps": COMFYUI_HIRES_STEPS,
                "cfg": COMFYUI_HIRES_CFG,
                "sampler_name": COMFYUI_SAMPLER,
                "scheduler": COMFYUI_SCHEDULER,
                "denoise": COMFYUI_HIRES_DENOISE,
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["10", 0],
            },
        }
        final_samples = ["11", 0]

    workflow["8"] = {"class_type": "VAEDecode", "inputs": {"samples": final_samples, "vae": ["3", 2]}}
    workflow["9"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix},
    }
    return workflow


def _format_execution_error(messages: Any) -> str:
    if not isinstance(messages, list):
        return str(messages)
    for message in messages:
        if isinstance(message, (list, tuple)) and len(message) > 1 and message[0] == "execution_error":
            detail = message[1]
            if isinstance(detail, dict):
                node = detail.get("node_type", "unknown node")
                node_id = detail.get("node_id", "?")
                reason = detail.get("exception_message", "알 수 없는 실행 오류")
                return f"{node} 노드({node_id}) 실패: {reason}"
    return str(messages)[:1500]


def _wait_for_image(prompt_id: str, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = requests.get(f"{COMFYUI_BASE_URL}/history/{prompt_id}", timeout=10)
        response.raise_for_status()
        history = response.json().get(prompt_id)
        if history:
            status = history.get("status", {})
            if status.get("status_str") == "error" or (
                status.get("completed") is False and status.get("messages")
            ):
                raise RuntimeError(f"ComfyUI 작업 실패: {_format_execution_error(status.get('messages', status))}")
            outputs = history.get("outputs", {})
            for node in outputs.values():
                images = node.get("images") or []
                if images:
                    return images[0]
        time.sleep(2)
    raise TimeoutError(f"ComfyUI 이미지 생성이 {timeout}초 안에 완료되지 않았습니다.")


def _build_panel_prompt(panel: dict[str, Any], character_guide: str, index: int) -> str:
    visual = str(panel.get("visual_prompt") or panel.get("scene") or "simple educational cartoon scene").strip()
    character_lock = (
        "same recurring character design across the full comic, preserve the exact hairstyle, hair color, "
        "face shape, eye style, clothing, accessories and body proportions described in the character guide; "
        "do not redesign or replace the characters"
    )
    composition = (
        f"comic panel {index} of the same four-panel story, a single scene only, "
        "clear foreground subject, readable pose, medium shot unless the scene requires otherwise"
    )
    parts = [WEBTOON_POSITIVE_STYLE, character_lock, character_guide.strip(), visual, composition]
    return ", ".join(part for part in parts if part)


def generate_panels(
    post_id: int,
    panels: list[dict[str, Any]],
    character_guide: str = "",
) -> list[dict[str, Any]]:
    status = get_status()
    if not status["available"]:
        raise RuntimeError(f"ComfyUI에 연결할 수 없습니다: {status['error']}")
    checkpoint = status.get("selected_checkpoint")
    if not checkpoint:
        raise RuntimeError(status.get("error") or "이미지 생성용 체크포인트가 없습니다.")
    if len(panels) != 4:
        raise ValueError(f"4컷 웹툰은 정확히 4개 패널이 필요합니다. 현재: {len(panels)}개")

    hires_supported = bool(status.get("quality", {}).get("hires_supported"))
    hires_active = bool(COMFYUI_HIRES_ENABLED and hires_supported and COMFYUI_HIRES_SCALE > 1.0)
    output_dir = GENERATED_DIR / str(post_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    base_seed = random.randint(1, 2**31 - 1)

    for index, panel in enumerate(panels, start=1):
        visual_prompt = _build_panel_prompt(panel, character_guide, index)
        seed = base_seed if COMFYUI_SEED_MODE == "shared" else random.randint(1, 2**31 - 1)
        workflow = _workflow(
            checkpoint,
            visual_prompt,
            seed,
            f"media_pipeline/post_{post_id}/panel_{index:02d}",
            hires_supported=hires_supported,
        )
        payload = {
            "prompt": workflow,
            "client_id": f"media-pipeline-{post_id}-{index}",
        }
        response = requests.post(f"{COMFYUI_BASE_URL}/prompt", json=payload, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        node_errors = response_data.get("node_errors") or {}
        if node_errors:
            raise RuntimeError(f"ComfyUI 워크플로 검증 오류: {node_errors}")
        prompt_id = response_data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI가 prompt_id를 반환하지 않았습니다: {response.text[:500]}")

        image_info = _wait_for_image(prompt_id, COMFYUI_TIMEOUT)
        params = urlencode({
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        })
        image_response = requests.get(f"{COMFYUI_BASE_URL}/view?{params}", timeout=90)
        image_response.raise_for_status()
        filename = f"panel_{index:02d}.png"
        target = output_dir / filename
        target.write_bytes(image_response.content)
        results.append({
            "panel": str(index),
            "filename": filename,
            "url": f"/media/{post_id}/{filename}",
            "prompt": visual_prompt,
            "seed": seed,
            "checkpoint": checkpoint,
            "quality_preset": "sd15_webtoon_portrait_v1",
            "width": COMFYUI_WIDTH,
            "height": COMFYUI_HEIGHT,
            "steps": COMFYUI_STEPS,
            "sampler": COMFYUI_SAMPLER,
            "scheduler": COMFYUI_SCHEDULER,
            "hires_fix": hires_active,
            "hires_scale": COMFYUI_HIRES_SCALE if hires_active else 1.0,
            "character_consistency": "same_seed_and_character_guide",
        })
    return results
