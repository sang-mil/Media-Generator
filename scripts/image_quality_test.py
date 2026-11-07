from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import COMFYUI_BASE_URL, COMFYUI_CHECKPOINT, COMFYUI_TIMEOUT  # noqa: E402


# Keep this prompt intentionally short and focused: one subject, one scene.
# Korean typography is added later by Pillow, never generated inside the image.
TEST_PROMPT = (
    "A single friendly young adult IT educator with short dark hair, "
    "wearing a simple teal sweater, seated at a cafe table using a smartphone, "
    "one open laptop beside them, clean polished 2D editorial vector illustration, "
    "soft mint and navy palette, crisp bold outlines, simple shapes, "
    "centered single scene, uncluttered warm off-white background, "
    "balanced composition, no lettering"
)
TEST_NEGATIVE_PROMPT = (
    "collage, character sheet, sticker sheet, grid, multiple panels, "
    "multiple characters, crowd, duplicate person, text, lettering, watermark, logo, "
    "blurry, lowres, noisy, muddy colors, messy background, "
    "extra arms, extra legs, malformed hands, distorted face"
)


@dataclass(frozen=True)
class GenerationProfile:
    name: str
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"
    hires_scale: float = 1.0
    hires_method: str = "bislerp"
    hires_steps: int = 12
    hires_cfg: float = 5.5
    hires_denoise: float = 0.28

    @property
    def output_width(self) -> int:
        return round(self.width * self.hires_scale)

    @property
    def output_height(self) -> int:
        return round(self.height * self.hires_scale)


PROFILES: dict[str, GenerationProfile] = {
    "sd15-native": GenerationProfile(
        name="sd15-native",
        width=512,
        height=640,
        steps=28,
        cfg=6.0,
    ),
    "sd15-current-hires": GenerationProfile(
        name="sd15-current-hires",
        width=512,
        height=640,
        steps=28,
        cfg=6.0,
        hires_scale=1.5,
        hires_method="bislerp",
        hires_steps=12,
        hires_cfg=5.5,
        hires_denoise=0.28,
    ),
    "sdxl": GenerationProfile(
        name="sdxl",
        width=768,
        height=960,
        steps=30,
        cfg=5.5,
    ),
}


def build_workflow(
    checkpoint: str,
    seed: int,
    profile: GenerationProfile,
    filename_prefix: str,
    prompt: str = TEST_PROMPT,
    negative_prompt: str = TEST_NEGATIVE_PROMPT,
) -> dict[str, Any]:
    """Build a reproducible one-image ComfyUI workflow for a model comparison."""
    workflow: dict[str, Any] = {
        "3": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["3", 1]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["3", 1]},
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": profile.width,
                "height": profile.height,
                "batch_size": 1,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": profile.steps,
                "cfg": profile.cfg,
                "sampler_name": profile.sampler,
                "scheduler": profile.scheduler,
                "denoise": 1.0,
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
    }

    final_samples: list[Any] = ["7", 0]
    if profile.hires_scale > 1.0:
        workflow["10"] = {
            "class_type": "LatentUpscaleBy",
            "inputs": {
                "samples": ["7", 0],
                "upscale_method": profile.hires_method,
                "scale_by": profile.hires_scale,
            },
        }
        workflow["11"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": (seed + 1) % (2**32),
                "steps": profile.hires_steps,
                "cfg": profile.hires_cfg,
                "sampler_name": profile.sampler,
                "scheduler": profile.scheduler,
                "denoise": profile.hires_denoise,
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["10", 0],
            },
        }
        final_samples = ["11", 0]

    workflow["8"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": final_samples, "vae": ["3", 2]},
    }
    workflow["9"] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["8", 0],
            "filename_prefix": filename_prefix,
        },
    }
    return workflow


def _safe_slug(value: str) -> str:
    stem = Path(value.replace("\\", "/")).stem
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return slug or "checkpoint"


def _response_json(response: requests.Response, context: str) -> dict[str, Any]:
    try:
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"{context} 요청 실패: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"{context} 응답 형식이 올바르지 않습니다.")
    return result


def get_checkpoint_names(session: requests.Session, base_url: str) -> list[str]:
    url = urljoin(base_url.rstrip("/") + "/", "object_info/CheckpointLoaderSimple")
    response = session.get(url, timeout=15)
    data = _response_json(response, "ComfyUI 체크포인트 목록")
    node = data.get("CheckpointLoaderSimple", {})
    required = node.get("input", {}).get("required", {})
    checkpoint_spec = required.get("ckpt_name", [])
    if not isinstance(checkpoint_spec, list) or not checkpoint_spec:
        return []
    names = checkpoint_spec[0]
    return [str(name) for name in names] if isinstance(names, list) else []


def _has_node(session: requests.Session, base_url: str, node_name: str) -> bool:
    url = urljoin(base_url.rstrip("/") + "/", f"object_info/{node_name}")
    response = session.get(url, timeout=10)
    if response.status_code == 404:
        return False
    data = _response_json(response, f"{node_name} 노드 확인")
    return node_name in data


def wait_for_image(
    session: requests.Session,
    base_url: str,
    prompt_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    history_url = urljoin(base_url.rstrip("/") + "/", f"history/{prompt_id}")

    while time.monotonic() < deadline:
        response = session.get(history_url, timeout=15)
        data = _response_json(response, "ComfyUI 작업 상태")
        history = data.get(prompt_id)
        if history:
            status = history.get("status", {})
            status_text = status.get("status_str")
            messages = status.get("messages", [])
            if status_text in {"error", "failed"}:
                raise RuntimeError(f"ComfyUI 이미지 생성 실패: {messages}")
            for message in (messages if isinstance(messages, list) else []):
                if isinstance(message, (list, tuple)) and message and message[0] == "execution_error":
                    raise RuntimeError(
                        f"ComfyUI 노드 실행 실패: {message[1] if len(message) > 1 else message}"
                    )
            outputs = history.get("outputs", {})
            for node_output in outputs.values():
                images = node_output.get("images") or []
                if images:
                    return images[0]
        time.sleep(2)

    raise TimeoutError(
        f"ComfyUI 이미지 생성이 {timeout_seconds}초 안에 완료되지 않았습니다. "
        "ComfyUI 대기열과 VRAM 사용량을 확인하세요."
    )


def _load_or_create_report(
    report_path: Path,
    run_id: str,
    seed: int,
) -> dict[str, Any]:
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"기존 실험 보고서를 읽을 수 없습니다: {exc}") from exc
        if report.get("seed") != seed or report.get("prompt") != TEST_PROMPT:
            raise RuntimeError(
                "기존 run-id의 Seed 또는 프롬프트가 다릅니다. "
                "동일 조건 비교를 위해 새 --run-id를 사용하세요."
            )
        return report

    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "aspect_ratio": "4:5",
        "prompt": TEST_PROMPT,
        "negative_prompt": TEST_NEGATIVE_PROMPT,
        "results": [],
    }


def _save_report(report_path: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    temp_path = report_path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(report_path)


def run_generation(
    session: requests.Session,
    base_url: str,
    checkpoint: str,
    profile: GenerationProfile,
    seed: int,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(checkpoint)
    result_key = f"{profile.name}__{slug}"
    prefix = f"media_quality_tests/{result_key}"
    workflow = build_workflow(
        checkpoint=checkpoint,
        seed=seed,
        profile=profile,
        filename_prefix=prefix,
    )

    prompt_url = urljoin(base_url.rstrip("/") + "/", "prompt")
    started = time.monotonic()
    response = session.post(
        prompt_url,
        json={"prompt": workflow, "client_id": f"media-quality-{result_key}"},
        timeout=45,
    )
    prompt_data = _response_json(response, "ComfyUI 이미지 생성 요청")
    node_errors = prompt_data.get("node_errors") or {}
    if node_errors:
        raise RuntimeError(f"ComfyUI 워크플로 검증 오류: {node_errors}")
    prompt_id = prompt_data.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI가 prompt_id를 반환하지 않았습니다: {prompt_data}")

    image_info = wait_for_image(session, base_url, str(prompt_id), timeout_seconds)
    view_url = urljoin(base_url.rstrip("/") + "/", "view")
    image_response = session.get(
        view_url,
        params={
            "filename": image_info["filename"],
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        },
        timeout=120,
    )
    try:
        image_response.raise_for_status()
        image_bytes = image_response.content
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_size = list(image.size)
    except (requests.RequestException, OSError) as exc:
        raise RuntimeError(f"ComfyUI 결과 이미지를 저장할 수 없습니다: {exc}") from exc

    filename = f"{result_key}.png"
    image_path = output_dir / filename
    image_path.write_bytes(image_bytes)

    elapsed = round(time.monotonic() - started, 2)
    return {
        "key": result_key,
        "checkpoint": checkpoint,
        "profile": asdict(profile),
        "seed": seed,
        "prompt_id": str(prompt_id),
        "comfyui_output": image_info,
        "image_file": filename,
        "image_size": image_size,
        "file_bytes": len(image_bytes),
        "elapsed_seconds": elapsed,
        "review_status": "pending_manual_review",
    }


def _build_run_plan(
    phase: str,
    baseline_model: str,
    sd15_models: list[str],
    sdxl_models: list[str],
) -> list[tuple[str, GenerationProfile]]:
    plan: list[tuple[str, GenerationProfile]] = []
    if phase in {"baseline", "all"}:
        plan.append((baseline_model, PROFILES["sd15-native"]))
        plan.append((baseline_model, PROFILES["sd15-current-hires"]))
    if phase in {"candidates", "all"}:
        plan.extend((model, PROFILES["sd15-native"]) for model in sd15_models)
        plan.extend((model, PROFILES["sdxl"]) for model in sdxl_models)
    return plan


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ComfyUI에서 동일한 장면·Seed로 이미지 모델을 비교합니다."
    )
    parser.add_argument(
        "--phase",
        choices=("baseline", "candidates", "all"),
        default="baseline",
        help="baseline은 현재 SD 1.5, candidates는 설치된 후보 모델, all은 모두 실행",
    )
    parser.add_argument(
        "--baseline-model",
        default=COMFYUI_CHECKPOINT,
        help="기준 SD 1.5 체크포인트의 ComfyUI 표시 파일명",
    )
    parser.add_argument(
        "--sd15-models",
        nargs="*",
        default=[],
        help="비교할 추가 SD 1.5 체크포인트 파일명",
    )
    parser.add_argument(
        "--sdxl-models",
        nargs="*",
        default=[],
        help="비교할 SDXL 체크포인트 파일명",
    )
    parser.add_argument("--seed", type=int, default=20261108)
    parser.add_argument("--run-id", default="public-wifi-v1")
    parser.add_argument("--base-url", default=COMFYUI_BASE_URL)
    parser.add_argument("--timeout", type=int, default=COMFYUI_TIMEOUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT_DIR / "generated" / "quality_tests")
    parser.add_argument("--list-checkpoints", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    base_url = args.base_url.rstrip("/")
    if not args.run_id or not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_id):
        raise SystemExit("--run-id는 영문, 숫자, 점, 밑줄, 하이픈만 사용할 수 있습니다.")
    if args.seed < 0 or args.seed >= 2**32:
        raise SystemExit("--seed는 0 이상 2^32 미만이어야 합니다.")
    if args.timeout < 30:
        raise SystemExit("--timeout은 최소 30초여야 합니다.")

    with requests.Session() as session:
        try:
            checkpoints = get_checkpoint_names(session, base_url)
            if args.list_checkpoints:
                print("ComfyUI에서 확인된 체크포인트:")
                for name in checkpoints:
                    print(f" - {name}")
                return 0

            plan = _build_run_plan(
                args.phase,
                args.baseline_model,
                args.sd15_models,
                args.sdxl_models,
            )
            if args.phase == "candidates" and not (args.sd15_models or args.sdxl_models):
                raise SystemExit(
                    "후보 모델을 지정하세요. --sd15-models 또는 --sdxl-models를 사용합니다."
                )
            if not plan:
                raise SystemExit("실행할 모델이 없습니다.")
            missing = sorted({model for model, _ in plan if model not in checkpoints})
            if missing:
                raise SystemExit(
                    "다음 체크포인트를 ComfyUI에서 찾을 수 없습니다:\n"
                    + "\n".join(f" - {name}" for name in missing)
                    + "\n모델을 직접 설치한 뒤 --list-checkpoints로 정확한 파일명을 확인하세요. "
                    "이 스크립트는 모델을 다운로드하거나 .env를 수정하지 않습니다."
                )

            if any(profile.hires_scale > 1.0 for _, profile in plan):
                if not _has_node(session, base_url, "LatentUpscaleBy"):
                    raise SystemExit(
                        "현재 Hires 비교에 필요한 LatentUpscaleBy 노드가 없습니다."
                    )

            output_dir = args.output_dir / args.run_id
            report_path = output_dir / "report.json"
            report = _load_or_create_report(report_path, args.run_id, args.seed)
            existing_keys = {item.get("key") for item in report.get("results", [])}
            for checkpoint, profile in plan:
                key = f"{profile.name}__{_safe_slug(checkpoint)}"
                if key in existing_keys and not args.overwrite:
                    raise SystemExit(
                        f"이미 결과가 있습니다: {key}. 재생성하려면 --overwrite를 사용하세요."
                    )

            print(f"실험 ID: {args.run_id}")
            print(f"Seed: {args.seed}")
            print(f"결과 폴더: {output_dir}")
            print(f"실행 이미지 수: {len(plan)}")

            for checkpoint, profile in plan:
                key = f"{profile.name}__{_safe_slug(checkpoint)}"
                print(f"\n[생성] {checkpoint} / {profile.name}")
                result = run_generation(
                    session=session,
                    base_url=base_url,
                    checkpoint=checkpoint,
                    profile=profile,
                    seed=args.seed,
                    output_dir=output_dir,
                    timeout_seconds=args.timeout,
                )
                if key in existing_keys:
                    report["results"] = [
                        item for item in report["results"] if item.get("key") != key
                    ]
                report.setdefault("results", []).append(result)
                existing_keys.add(key)
                _save_report(report_path, report)
                print(
                    f"[완료] {result['image_file']} | "
                    f"{result['image_size'][0]}x{result['image_size'][1]} | "
                    f"{result['elapsed_seconds']}초"
                )

            print(f"\n실험이 끝났습니다. 결과와 report.json을 확인하세요: {output_dir}")
            return 0
        except requests.RequestException as exc:
            raise SystemExit(
                f"ComfyUI에 연결하지 못했습니다: {exc}\n"
                "ComfyUI가 실행 중이고 --base-url 주소가 맞는지 확인하세요."
            ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
