from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "benchmark_results"

# Baseline mirrors the current app/app/ai.py SYSTEM_PROMPT so this test can
# measure the value added by the technical guardrails, not a different persona.
BASE_SYSTEM = """당신은 한국어 IT 대중 콘텐츠 편집자이자 독창적인 4컷 웹툰 스토리 작가입니다.
목표는 IT에 익숙하지 않은 일반 사용자도 이해하고 저장하거나 공유하고 싶은 짧은 콘텐츠를 만드는 것입니다.
사실을 만들어내지 마세요. 메뉴 경로, 수치, 제품 기능 등 확인이 필요한 내용은 fact_check 항목에 기록하세요.
광고 문구, 제휴 링크, 구매 유도는 포함하지 마세요. 특정 제품을 근거 없이 추천하지 마세요.
기존 유명 캐릭터나 특정 작가의 화풍을 모방하지 말고 독창적인 캐릭터와 표현을 사용하세요.
반드시 요청된 JSON 객체만 반환하세요.
"""

TECHNICAL_GUARDRAILS = """\n[기술 정보 정확성 하네스 - 반드시 준수]
1. 사실, 추정, 기기/OS/앱 버전에 따라 달라지는 내용을 구분합니다.
2. 메뉴 경로, 설정 이름, 수치, 제품 기능을 확실히 모르면 지어내지 말고 '기기·버전별 확인 필요'라고 씁니다.
3. 원인과 결과를 단정하기 전에 그 관계가 일반적으로 성립하는지 점검합니다.
4. 저장 공간 설명에서는 사진·동영상 원본, 다운로드 파일, 앱 문서/데이터, 캐시, 운영체제/시스템 데이터가 서로 다른 범주임을 구분합니다. 모든 메신저 데이터가 캐시라고 표현하지 않습니다.
5. 데이터를 삭제하는 안내는 위험을 설명합니다. '캐시 삭제'와 '앱 데이터/저장공간 삭제'를 혼동하지 않으며, 후자는 로그인 정보나 로컬 파일 등이 삭제될 수 있음을 알립니다.
6. 기술 주장은 factual_claims 배열에 짧게 정리하고, 각 항목에 confidence('high'|'medium'|'low'), needs_verification(boolean), reason을 포함합니다.
7. 외부 검색을 수행하지 않았다면 출처나 공식 문서 링크를 꾸며내지 않습니다. 검증이 필요한 주장은 fact_check에 구체적인 확인 항목을 기록합니다.
8. 모르는 내용은 추측해서 채우지 말고 제한사항을 명시합니다.
9. 출력 JSON 스키마를 엄격히 지킵니다. 모든 사용자 노출 문구는 자연스러운 한국어로 작성합니다. visual_prompt만 영어로 작성합니다.
"""

TASKS: list[dict[str, Any]] = [
    {
        "id": "comic_storage_4panel",
        "title": "4컷 웹툰 기획 - 스마트폰 저장 공간",
        "prompt": """다음 주제로 인스타그램용 4컷 IT 웹툰을 기획하세요.
주제: 스마트폰 저장 공간이 부족해지는 이유와 안전하게 정리하는 방법
대상: 스마트폰 설정이 익숙하지 않은 일반 성인
목표: 첫 컷에서 공감을 얻고, 마지막 컷에서 실제로 도움이 되는 안전한 행동을 제시합니다.
요구사항:
- 도입 → 문제 확인 → 원인 구분 → 안전한 해결 순서로 구성합니다.
- 캐릭터는 독창적인 한 명의 주인공과 조력자 한 명 이내로 제한합니다.
- 각 컷 대사는 짧고 자연스러운 한국어로 씁니다.
- 잘못된 기술 설명이나 확인되지 않은 메뉴 경로를 넣지 않습니다.
- 사진/동영상 원본, 앱 데이터, 캐시, 다운로드 파일을 같은 것으로 취급하지 않습니다.
- 각 컷은 장면, 대사, 핵심 정보, 이미지 생성용 visual_prompt를 포함합니다.
- 이미지 안에 글자, 로고, 말풍선을 생성하지 않도록 visual_prompt를 작성합니다.
반드시 다음 JSON 구조를 사용합니다:
{
  "title": "웹툰 제목",
  "hook": "첫 컷의 관심 유도 문장",
  "character_guide": "캐릭터 외형 설명(영어)",
  "panels": [
    {"number": 1, "scene": "장면", "dialogue": "대사", "key_information": "핵심 정보", "visual_prompt": "English image prompt"},
    {"number": 2, "scene": "장면", "dialogue": "대사", "key_information": "핵심 정보", "visual_prompt": "English image prompt"},
    {"number": 3, "scene": "장면", "dialogue": "대사", "key_information": "핵심 정보", "visual_prompt": "English image prompt"},
    {"number": 4, "scene": "장면", "dialogue": "대사", "key_information": "핵심 정보", "visual_prompt": "English image prompt"}
  ],
  "caption": "게시물 본문",
  "hashtags": ["태그1", "태그2"],
  "factual_claims": [{"claim": "기술 주장", "confidence": "high|medium|low", "needs_verification": true, "reason": "판단 이유"}],
  "fact_check": ["게시 전 확인할 사항"]
}
""",
    },
    {
        "id": "technical_explainer_storage",
        "title": "기술 설명 - 스마트폰 저장 공간",
        "prompt": """스마트폰 저장 공간이 부족한 일반 사용자에게 저장 공간의 종류와 안전한 정리 방법을 설명하세요.
대상은 기술 용어에 익숙하지 않은 성인입니다.
요구사항:
- 사진/동영상 원본, 다운로드 파일, 앱 문서/데이터, 캐시, 운영체제/시스템 데이터를 구분합니다.
- 캐시를 지워도 되는 경우와 앱 데이터를 삭제할 때 주의할 점을 구분합니다.
- 기기 종류와 운영체제 버전에 따라 메뉴 경로가 달라질 수 있으므로, 확실하지 않은 메뉴 경로를 단정하지 않습니다.
- 사용자 파일이나 대화 기록이 지워질 수 있는 위험을 설명합니다.
- 정확하지 않은 수치나 단정적인 효과를 만들지 않습니다.
- 외부 검색은 수행하지 않았다고 가정하고 공식 출처를 꾸며내지 않습니다.
반드시 다음 JSON 구조를 사용합니다:
{
  "title": "짧은 제목",
  "plain_language_explanation": "쉬운 설명",
  "storage_categories": [{"name": "범주", "what_it_is": "설명", "example": "예시", "cleanup_caution": "주의사항"}],
  "safe_steps": [{"step": 1, "action": "할 일", "risk": "주의할 점"}],
  "device_version_caveat": "기기/OS별 차이 안내",
  "factual_claims": [{"claim": "기술 주장", "confidence": "high|medium|low", "needs_verification": true, "reason": "판단 이유"}],
  "fact_check": ["실제 게시 전 추가 확인할 사항"]
}
""",
    },
]


@dataclass
class RunResult:
    model: str
    prompt_mode: str
    task_id: str
    task_title: str
    status: str
    elapsed_seconds: float
    load_seconds: float | None
    prompt_tokens: int | None
    output_tokens: int | None
    output_tokens_per_second: float | None
    gpu_memory_used_max_mb: int | None
    gpu_utilization_max_percent: int | None
    ollama_processor_allocation: str | None
    json_valid: bool
    schema_valid: bool
    validation_notes: list[str]
    response_text: str
    parsed: dict[str, Any] | None
    error: str | None



class GpuMonitor:
    """Best-effort NVIDIA telemetry sampler; gracefully disables if nvidia-smi is absent."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.max_memory_mb: int | None = None
        self.max_utilization: int | None = None
        self.available = True

    def _sample(self) -> None:
        while not self.stop_event.is_set():
            try:
                proc = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3,
                    check=False,
                )
                if proc.returncode != 0 or not proc.stdout.strip():
                    self.available = False
                    return
                first_line = proc.stdout.strip().splitlines()[0]
                parts = [part.strip() for part in first_line.split(",")]
                if len(parts) >= 2:
                    memory_mb = int(re.sub(r"[^0-9]", "", parts[0]))
                    utilization = int(re.sub(r"[^0-9]", "", parts[1]))
                    self.max_memory_mb = max(self.max_memory_mb or 0, memory_mb)
                    self.max_utilization = max(self.max_utilization or 0, utilization)
            except (OSError, subprocess.SubprocessError, ValueError):
                self.available = False
                return
            self.stop_event.wait(self.interval)

    def start(self) -> None:
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()

    def stop(self) -> tuple[int | None, int | None]:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)
        if not self.available:
            return None, None
        return self.max_memory_mb, self.max_utilization


def get_ollama_processor_allocation(model: str) -> str | None:
    try:
        proc = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if model in line:
                match = re.search(r"\d+%\s*/\s*\d+%\s+CPU/GPU", line, flags=re.IGNORECASE)
                return match.group(0) if match else line.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None

def extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("최상위 JSON 값이 객체가 아닙니다.")
    return parsed


def validate_result(task_id: str, data: dict[str, Any]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if task_id == "comic_storage_4panel":
        panels = data.get("panels")
        if not isinstance(panels, list) or len(panels) != 4:
            notes.append("panels가 정확히 4개가 아님")
        else:
            for index, panel in enumerate(panels, 1):
                if not isinstance(panel, dict):
                    notes.append(f"{index}번 패널이 객체가 아님")
                    continue
                for key in ("scene", "dialogue", "key_information", "visual_prompt"):
                    if not panel.get(key):
                        notes.append(f"{index}번 패널의 {key} 누락")
                if panel.get("number") != index:
                    notes.append(f"{index}번 패널 number 불일치")
        if not data.get("title"):
            notes.append("title 누락")
        if not data.get("character_guide"):
            notes.append("character_guide 누락")
    elif task_id == "technical_explainer_storage":
        categories = data.get("storage_categories")
        if not isinstance(categories, list) or len(categories) < 5:
            notes.append("storage_categories가 5개 미만 (사진/동영상, 다운로드, 앱 데이터, 캐시, 시스템 데이터 구분 확인 필요)")
        else:
            category_names = " ".join(str(item.get("name", "")) for item in categories if isinstance(item, dict))
            required_groups = {
                "사진/동영상": r"사진|동영상|미디어",
                "다운로드": r"다운로드|받은 파일|내려받",
                "앱 데이터": r"앱.*데이터|데이터.*앱|앱 문서",
                "캐시": r"캐시",
                "시스템": r"시스템|운영체제",
            }
            for label, pattern in required_groups.items():
                if not re.search(pattern, category_names, flags=re.IGNORECASE):
                    notes.append(f"저장 공간 범주 누락 또는 명칭 불명확: {label}")
        for key in ("plain_language_explanation", "safe_steps", "device_version_caveat"):
            if not data.get(key):
                notes.append(f"{key} 누락")
        safe_steps_text = json.dumps(data.get("safe_steps", []), ensure_ascii=False)
        if re.search(r"앱\s*(데이터|저장공간)|데이터\s*삭제", safe_steps_text) and not re.search(r"주의|삭제되|사라|백업|손실", safe_steps_text):
            notes.append("앱 데이터 삭제에 대한 데이터 손실/주의 문구 확인 필요")
    claims = data.get("factual_claims")
    if not isinstance(claims, list):
        notes.append("factual_claims가 배열이 아님")
    else:
        for idx, claim in enumerate(claims, 1):
            if not isinstance(claim, dict):
                notes.append(f"factual_claims {idx}번 항목이 객체가 아님")
                continue
            for key in ("claim", "confidence", "needs_verification", "reason"):
                if key not in claim:
                    notes.append(f"factual_claims {idx}번 항목의 {key} 누락")
    if not isinstance(data.get("fact_check"), list):
        notes.append("fact_check가 배열이 아님")
    return len(notes) == 0, notes


def resolve_model(requested: str, available: list[str]) -> str | None:
    if requested in available:
        return requested
    requested_base = requested.split(":", 1)[0]
    exact_base = [name for name in available if name.split(":", 1)[0] == requested_base]
    if len(exact_base) == 1:
        return exact_base[0]
    return None


def get_models(base_url: str, timeout: int) -> list[str]:
    response = requests.get(f"{base_url}/api/tags", timeout=min(timeout, 10))
    response.raise_for_status()
    return [str(item["name"]) for item in response.json().get("models", []) if item.get("name")]


def run_case(
    base_url: str,
    model: str,
    prompt_mode: str,
    task: dict[str, Any],
    temperature: float,
    num_ctx: int,
    num_predict: int,
    timeout: int,
    keep_alive: str,
) -> RunResult:
    system = BASE_SYSTEM + (TECHNICAL_GUARDRAILS if prompt_mode == "guarded" else "")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": task["prompt"]},
        ],
        "stream": False,
        "format": "json",
        "keep_alive": keep_alive,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    started = time.perf_counter()
    gpu_monitor = GpuMonitor()
    gpu_monitor.start()
    try:
        response = requests.post(f"{base_url}/api/chat", json=body, timeout=timeout)
        elapsed = time.perf_counter() - started
        response.raise_for_status()
        payload = response.json()
        gpu_memory_max, gpu_util_max = gpu_monitor.stop()
        processor_allocation = get_ollama_processor_allocation(model)
        text = str(payload.get("message", {}).get("content", ""))
        parsed: dict[str, Any] | None = None
        notes: list[str] = []
        try:
            parsed = extract_json(text)
            schema_valid, notes = validate_result(task["id"], parsed)
            json_valid = True
        except (ValueError, json.JSONDecodeError) as exc:
            json_valid = False
            schema_valid = False
            notes.append(f"JSON 파싱 실패: {exc}")
        output_tokens = payload.get("eval_count")
        eval_duration = payload.get("eval_duration")
        tps = None
        if isinstance(output_tokens, (int, float)) and isinstance(eval_duration, (int, float)) and eval_duration > 0:
            tps = float(output_tokens) / (float(eval_duration) / 1_000_000_000)
        load_duration = payload.get("load_duration")
        return RunResult(
            model=model,
            prompt_mode=prompt_mode,
            task_id=task["id"],
            task_title=task["title"],
            status="ok",
            elapsed_seconds=round(elapsed, 3),
            load_seconds=round(float(load_duration) / 1_000_000_000, 3) if isinstance(load_duration, (int, float)) else None,
            prompt_tokens=payload.get("prompt_eval_count"),
            output_tokens=output_tokens,
            output_tokens_per_second=round(tps, 2) if tps is not None else None,
            gpu_memory_used_max_mb=gpu_memory_max,
            gpu_utilization_max_percent=gpu_util_max,
            ollama_processor_allocation=processor_allocation,
            json_valid=json_valid,
            schema_valid=schema_valid,
            validation_notes=notes,
            response_text=text,
            parsed=parsed,
            error=None,
        )
    except Exception as exc:  # preserve benchmark progress on one failed model/task
        gpu_memory_max, gpu_util_max = gpu_monitor.stop()
        processor_allocation = get_ollama_processor_allocation(model)
        return RunResult(
            model=model,
            prompt_mode=prompt_mode,
            task_id=task["id"],
            task_title=task["title"],
            status="error",
            elapsed_seconds=round(time.perf_counter() - started, 3),
            load_seconds=None,
            prompt_tokens=None,
            output_tokens=None,
            output_tokens_per_second=None,
            gpu_memory_used_max_mb=gpu_memory_max,
            gpu_utilization_max_percent=gpu_util_max,
            ollama_processor_allocation=processor_allocation,
            json_valid=False,
            schema_valid=False,
            validation_notes=[],
            response_text="",
            parsed=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def render_report(results: list[RunResult], output_dir: Path, settings: dict[str, Any]) -> None:
    lines = [
        "# Ollama 모델 비교 결과",
        "",
        f"- 실행 시각: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Ollama: `{settings['base_url']}`",
        f"- Qwen 후보: `{settings['qwen_model']}`",
        f"- Gemma 후보: `{settings['gemma_model']}`",
        f"- 옵션: temperature={settings['temperature']}, num_ctx={settings['num_ctx']}, num_predict={settings['num_predict']}",
        "",
        "## 자동 측정 결과",
        "",
        "| 모델 | 프롬프트 | 과제 | 상태 | 시간(초) | 로딩(초) | 출력 토큰 | 토큰/초 | GPU 최대 메모리(MB) | GPU 최대 사용률(%) | Ollama 배치 | JSON | 스키마 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r.model}` | {r.prompt_mode} | {r.task_id} | {r.status} | {r.elapsed_seconds} | {r.load_seconds if r.load_seconds is not None else '-'} | {r.output_tokens if r.output_tokens is not None else '-'} | {r.output_tokens_per_second if r.output_tokens_per_second is not None else '-'} | {r.gpu_memory_used_max_mb if r.gpu_memory_used_max_mb is not None else '-'} | {r.gpu_utilization_max_percent if r.gpu_utilization_max_percent is not None else '-'} | {r.ollama_processor_allocation or '-'} | {'통과' if r.json_valid else '실패'} | {'통과' if r.schema_valid else '실패'} |"
        )
    lines += [
        "",
        "## 수동 품질 평가표",
        "",
        "아래 평가는 자동 점수가 아닙니다. 결과 JSON을 읽고 사람이 1~5점으로 평가하세요.",
        "",
        "| 모델 | 프롬프트 | 과제 | 한국어 자연스러움 | 지시 준수 | 정보 정확성 | 설명 명료성 | 독창성/재미 | 총평 |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        if r.status == "ok":
            lines.append(f"| `{r.model}` | {r.prompt_mode} | {r.task_id} | /5 | /5 | /5 | /5 | /5 |  |")
    lines += [
        "",
        "## 평가 시 주의사항",
        "",
        "- 속도는 같은 PC에서 측정한 값이며, 첫 실행의 모델 로딩 시간과 이후 웜 실행 시간을 구분하세요.",
        "- GPU 최대 메모리/사용률은 `nvidia-smi`를 1초 간격으로 샘플링한 최댓값입니다. 짧은 순간의 피크는 놓칠 수 있습니다.",
        "- Ollama 배치 비율은 응답 직후 `ollama ps`에서 읽은 CPU/GPU 배치 정보이며 GPU 사용률 자체가 아닙니다.",
        "- 기술 설명의 정확성은 모델 자체 평가만으로 확정하지 마세요. 공식 문서 또는 실제 기기에서 검증해야 합니다.",
        "- `guarded`는 기술 정확성 지침을 강화한 프롬프트이고, 모델 가중치를 학습시키는 파인튜닝이 아닙니다.",
        "- `fact_check`가 비어 있거나 confidence가 높다는 이유만으로 사실이라고 간주하지 마세요.",
        "",
        "## 결과 파일",
        "",
        "각 실행의 전체 JSON 응답은 같은 폴더의 `results.json`과 `responses/` 폴더에 저장됩니다.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Qwen 27B and Gemma 4 with a repeatable Korean content benchmark.")
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"))
    parser.add_argument("--qwen-model", default="qwen3.8:27b-q4_K_M")
    parser.add_argument("--gemma-model", default="gemma4:26b")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--num-predict", type=int, default=2200)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--keep-alive", default="5m")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--models-order", choices=("qwen-first", "gemma-first"), default="qwen-first")
    args = parser.parse_args()

    try:
        available = get_models(args.base_url, args.timeout)
    except Exception as exc:
        print(f"Ollama 연결 실패: {exc}", file=sys.stderr)
        return 2

    qwen = resolve_model(args.qwen_model, available)
    gemma = resolve_model(args.gemma_model, available)
    missing = []
    if not qwen:
        missing.append(f"Qwen 후보 `{args.qwen_model}`")
    if not gemma:
        missing.append(f"Gemma 후보 `{args.gemma_model}`")
    if missing:
        print("설치된 모델을 찾지 못했습니다: " + ", ".join(missing), file=sys.stderr)
        print("현재 설치 모델:", file=sys.stderr)
        for name in available:
            print(f"  - {name}", file=sys.stderr)
        print("모델을 임의로 대체하지 않았습니다. 정확한 모델명을 --qwen-model / --gemma-model로 지정하세요.", file=sys.stderr)
        return 3

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir).resolve() if args.output_dir else DEFAULT_OUTPUT_ROOT / stamp
    response_dir = output_dir / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)

    model_pairs = [("Qwen", qwen), ("Gemma", gemma)]
    if args.models_order == "gemma-first":
        model_pairs.reverse()
    results: list[RunResult] = []

    print("\n=== Self-improving Media Pipeline: Model Benchmark ===")
    print(f"Ollama: {args.base_url}")
    print(f"Qwen:   {qwen}")
    print(f"Gemma:  {gemma}")
    print(f"Tasks:  {len(TASKS)} x prompt modes 2 x models 2 = 8 calls")
    print("ComfyUI 이미지 생성 작업은 벤치마크 중 잠시 중지하는 것을 권장합니다.\n")

    for label, model in model_pairs:
        print(f"\n--- {label}: {model} ---")
        for task in TASKS:
            for prompt_mode in ("baseline", "guarded"):
                print(f"[{label} | {prompt_mode} | {task['id']}] 요청 중...", flush=True)
                result = run_case(
                    base_url=args.base_url,
                    model=model,
                    prompt_mode=prompt_mode,
                    task=task,
                    temperature=args.temperature,
                    num_ctx=args.num_ctx,
                    num_predict=args.num_predict,
                    timeout=args.timeout,
                    keep_alive=args.keep_alive,
                )
                results.append(result)
                case_name = f"{label.lower()}_{prompt_mode}_{task['id']}.json"
                (response_dir / case_name).write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
                if result.status == "ok":
                    print(
                        f"  완료: {result.elapsed_seconds}s | {result.output_tokens_per_second or 0} tok/s | JSON {'OK' if result.json_valid else 'FAIL'} | schema {'OK' if result.schema_valid else 'FAIL'}",
                        flush=True,
                    )
                else:
                    print(f"  실패: {result.error}", flush=True)
                (output_dir / "results.json").write_text(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2), encoding="utf-8")

    settings = {
        "base_url": args.base_url,
        "qwen_model": qwen,
        "gemma_model": gemma,
        "temperature": args.temperature,
        "num_ctx": args.num_ctx,
        "num_predict": args.num_predict,
    }
    render_report(results, output_dir, settings)
    print("\n=== 완료 ===")
    print(f"보고서: {output_dir / 'report.md'}")
    print(f"원본 결과: {output_dir / 'results.json'}")
    print(f"개별 응답: {response_dir}")

    # Unload both models after benchmark to return RAM/VRAM to other local workloads.
    for model in (qwen, gemma):
        try:
            requests.post(
                f"{args.base_url}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=15,
            )
        except requests.RequestException:
            pass
    return 0 if all(item.status == "ok" for item in results) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
