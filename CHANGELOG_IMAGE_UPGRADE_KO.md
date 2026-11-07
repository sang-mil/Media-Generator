# 이미지 엔진 개선 v0.4 - 변경 요약

## 핵심
- SD 1.5용 세로형 512x640, 28 steps, CFG 6.0, DPM++ 2M Karras.
- 선택적으로 LatentUpscaleBy 1.5x + 12-step / denoise 0.28 refinement.
- 명시적 체크포인트 선택 및 오디오 모델 제외.
- 공유 seed와 고정 캐릭터 설명을 4컷 모두에 반복.
- UI 미리보기 세로 4:5 적용.
- ComfyUI 노드 오류 메시지 가독성 개선.

## 알려진 제한
- SD 1.5 기본 체크포인트의 스타일 품질 자체는 그대로입니다.
- IPAdapter / LoRA 기반 참조 이미지 캐릭터 고정은 아직 포함하지 않습니다.
- LatentUpscaleBy가 없으면 자동으로 1차 생성으로 폴백합니다.
- 실제 RTX 3060 12GB 장비에서 생성 속도와 메모리 여유를 검증해야 합니다.
