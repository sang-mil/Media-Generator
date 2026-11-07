# Self-improving Media Pipeline - 이미지 엔진 개선 패치 v0.4

이 ZIP은 v0.3.1 프로젝트에 적용하는 **부분 패치**입니다. 기존 `.env`, SQLite 데이터베이스, Ollama 설정, `run.ps1`, `stop.ps1`은 덮어쓰지 않습니다.

## 바뀐 점

- 체크포인트 목록의 첫 파일을 무조건 선택하지 않습니다.
- `COMFYUI_CHECKPOINT`에 지정한 이미지 모델만 선택합니다. 기본값은 `v1-5-pruned-emaonly.safetensors`입니다.
- `ace_step` 등 오디오 체크포인트는 이미지 모델 후보에서 제외합니다.
- SD 1.5에 맞춘 세로형 512×640 해상도와 DPM++ 2M Karras 샘플링을 사용합니다.
- 1차 생성 후 ComfyUI의 기본 `LatentUpscaleBy` 노드가 있으면 1.5배 잠재 업스케일 + 낮은 denoise 2차 보정을 시도합니다.
- 해당 노드가 없으면 1차 생성으로 안전하게 폴백합니다.
- 같은 캐릭터 가이드와 시드를 4컷에 반복 적용합니다. 이는 일관성을 보조하지만 IPAdapter/LoRA 수준의 캐릭터 고정을 보장하지는 않습니다.
- 대시보드 이미지 미리보기를 4:5 세로 비율로 변경합니다.
- ComfyUI 실행 오류에서 노드 이름과 원인을 더 읽기 쉽게 표시합니다.

## 적용

1. 앱을 종료합니다.
2. 프로젝트 폴더에서 `app/comfyui.py`, `app/config.py`, `web/index.html`을 백업합니다.
3. 이 ZIP을 `C:\dev\self_improving_media_pipeline`에 압축 해제합니다.
4. `.env`에 아래 설정을 추가하거나 기존 값을 수정합니다.

```env
COMFYUI_CHECKPOINT=v1-5-pruned-emaonly.safetensors
COMFYUI_TIMEOUT=900
COMFYUI_WIDTH=512
COMFYUI_HEIGHT=640
COMFYUI_STEPS=28
COMFYUI_CFG=6.0
COMFYUI_SAMPLER=dpmpp_2m
COMFYUI_SCHEDULER=karras
COMFYUI_HIRES_ENABLED=true
COMFYUI_HIRES_SCALE=1.5
COMFYUI_HIRES_METHOD=bislerp
COMFYUI_HIRES_STEPS=12
COMFYUI_HIRES_CFG=5.5
COMFYUI_HIRES_DENOISE=0.28
COMFYUI_SEED_MODE=shared
```

5. PowerShell에서 `Set-Location "C:\dev\self_improving_media_pipeline"` 후 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` 후 ` .\configure_image_quality.ps1`을 실행하면 위 설정을 자동 반영합니다. 이 스크립트는 기존 `.env`를 백업하고 관련 키만 수정합니다.
6. `run.ps1`로 재실행합니다.

## 권장 첫 시험

먼저 한 게시물에서 이미지 1세트(4컷)를 생성해 품질과 VRAM 사용량을 확인하세요. 2차 업스케일이 OOM 또는 느린 경우 `.env`에서 `COMFYUI_HIRES_ENABLED=false`로 꺼서 1차 생성만 사용합니다. `COMFYUI_WIDTH=512`, `COMFYUI_HEIGHT=640`은 SD 1.5를 위한 안정 우선값입니다.

## 중요한 한계

현재 설치된 `v1-5-pruned-emaonly.safetensors`는 범용 SD 1.5 체크포인트입니다. 이번 패치는 프롬프트, 해상도, 샘플러, 2차 보정을 개선하지만 웹툰 전문 모델로 바꾸지는 않습니다. 최종 품질이 여전히 부족하면 다음 단계에서 웹툰 전용 체크포인트와 해당 모델의 상업적 이용 라이선스를 확인해야 합니다.

캐릭터 일관성은 같은 시드와 캐릭터 설명을 반복하는 수준입니다. IPAdapter/LoRA를 이용한 강한 캐릭터 고정은 별도 노드와 모델 파일, 라이선스 확인 후 추가할 수 있습니다.

## 테스트

프로젝트의 가상환경에서 실행:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_comfyui_quality -v
```
