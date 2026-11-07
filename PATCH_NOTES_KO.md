# v0.3.1 ComfyUI 체크포인트 선택 수정

## 문제
기존 코드가 `CheckpointLoaderSimple`에서 반환된 체크포인트 목록의 첫 번째 파일을 무조건 선택했습니다.
현재 환경에서는 첫 항목인 `ace_step_v1_3.5b.safetensors`가 선택되어 일반 SD KSampler 이미지 워크플로와 호환되지 않았습니다.

## 수정
- 기본 이미지 체크포인트를 `v1-5-pruned-emaonly.safetensors`로 지정했습니다.
- `.env`의 `COMFYUI_CHECKPOINT`로 사용할 체크포인트를 명시할 수 있습니다.
- 설정한 체크포인트가 없으면 다른 모델로 조용히 대체하지 않고 오류를 표시합니다.
- 자동 선택 시 ACE-Step, Stable Audio, MusicGen 등 명백한 오디오 체크포인트를 제외합니다.

## 적용
프로젝트 폴더에 ZIP을 압축 해제하여 `app/comfyui.py`, `app/config.py`, `.env.example`을 덮어씁니다. 기존 `.env`는 덮어쓰지 마세요.
기존 `.env`에 다음 줄을 추가하거나 값을 수정합니다.

```env
COMFYUI_CHECKPOINT=v1-5-pruned-emaonly.safetensors
```

그다음 `run.ps1`로 프로그램을 재시작합니다.
