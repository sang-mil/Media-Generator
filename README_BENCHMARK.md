# Qwen 27B vs Gemma 4 26B 벤치마크 하네스

## 목적

- Qwen과 Gemma에 동일한 작업·생성 옵션을 적용한다.
- `baseline`과 기술 정확성 지침을 강화한 `guarded`를 각각 실행한다.
- 4컷 웹툰 기획과 기술 설명 과제를 비교한다.
- 총 8회 요청(모델 2개 × 프롬프트 2종 × 과제 2개)을 실행한다.
- 응답 원문, JSON/스키마 검사, 생성 시간, 로딩 시간, 토큰 수, 출력 토큰/초를 저장한다.

## 설치 위치

프로젝트 루트에 다음 구조로 복사한다.

```text
self_improving_media_pipeline/
  tools/
    benchmark_models.py
    run_benchmark.ps1
  prompts/
    TECHNICAL_GUARDRAILS.md
    SCORING_RUBRIC.md
  README_BENCHMARK.md
```

## 실행

PowerShell 5.1에서 프로젝트 루트로 이동한 뒤:

```powershell
.\tools\run_benchmark.ps1
```

Qwen 모델 태그가 다르면 정확한 설치 모델명으로 변경한다.

```powershell
.\.venv\Scripts\python.exe .\tools\benchmark_models.py --qwen-model "qwen3.8-code-api:latest" --gemma-model "gemma4:26b"
```

기본 Qwen 모델은 `qwen3.8:27b-q4_K_M`이다. 스크립트는 설치되지 않은 모델을 자동으로 다른 모델로 대체하지 않고, 설치 목록을 출력하고 중단한다.

## 실행 전 주의

- Ollama가 실행 중이어야 한다.
- ComfyUI를 통한 이미지 생성은 벤치마크 동안 잠시 멈추는 것을 권장한다. LLM과 이미지 생성이 GPU/RAM을 경쟁하지 않게 하기 위함이다.
- 기본 컨텍스트는 8192, 출력 제한은 2200토큰이다.
- 모델마다 4회 요청하고, 끝나면 두 모델의 keep_alive를 0으로 설정해 메모리 반환을 요청한다.
- 벤치마크는 모델을 다운로드하지 않는다.

## 결과 위치

`benchmark_results/YYYYMMDD_HHMMSS/`

- `report.md`: 속도 및 자동 구조 검사 결과 + 수동 평가표
- `results.json`: 모든 실행 메타데이터
- `responses/*.json`: 과제별 원문과 파싱된 JSON

## 평가 해석

- `guarded`는 프롬프트 지침이며 파인튜닝이 아니다.
- 자동 검사는 JSON/필드 구조만 검증한다. 기술적 진실 여부를 판정하지 않는다.
- `factual_claims`의 confidence는 모델의 자기평가이므로 정확성 보증이 아니다.
- 기술 정확성은 공식 문서 또는 실제 기기로 검증해야 한다.
