# ComfyUI 이미지 품질 비교 테스트

이 실험은 이미지 생성 모델을 선택하기 전에 실제 결과를 동일한 조건으로 비교하기 위한 도구입니다. 운영용 이미지 생성 로직과 .env는 변경하지 않습니다.

## 비교 원칙

- 모든 모델에 동일한 장면 프롬프트와 동일한 Seed를 사용합니다.
- SD 1.5 기준선은 기본 해상도 생성과 현재 Hires Fix 생성, 두 결과를 각각 만듭니다.
- SDXL 후보는 4:5 비율의 768×960 해상도에서 Hires Fix 없이 먼저 비교합니다.
- 후보 체크포인트는 사용자가 ComfyUI에 직접 설치해야 합니다. 이 도구는 모델을 다운로드하거나 파일을 이동하지 않습니다.
- 생성된 이미지와 설정은 generated/quality_tests/<run-id>/에 기록합니다. generated/는 Git에서 제외됩니다.

해상도와 스텝은 각 모델 계열에 맞춘 초기 비교값입니다. 첫 비교에서 우승 모델을 확정하지 말고, 결과가 좋은 후보를 같은 모델 내에서 설정 최적화한 다음 최종 선택합니다.

## 1. ComfyUI 체크포인트 확인

프로젝트 루트에서 Windows PowerShell로 실행합니다.

    .\.venv\Scripts\python.exe -m scripts.image_quality_test --list-checkpoints

ComfyUI의 CheckpointLoaderSimple에서 인식한 체크포인트 파일명이 출력됩니다. 모델 파일을 설치한 뒤에도 목록에 없으면 ComfyUI를 재시작하거나 체크포인트 폴더를 확인합니다.

## 2. 현재 SD 1.5 기준선 생성

    .\.venv\Scripts\python.exe -m scripts.image_quality_test --phase baseline --run-id public-wifi-v1 --seed 20261108

다음 두 장을 생성합니다.

| 결과 | 설정 | 확인 목적 |
|---|---|---|
| sd15-native 이미지 | 512×640, 28 steps, Hires 없음 | 기본 SD 1.5 품질 |
| sd15-current-hires 이미지 | 512×640 시작, 1.5배 확대, 12-step refinement | 기존 확대 단계가 결과에 미치는 영향 |

두 이미지가 생성되면 report.json과 함께 보관합니다. 먼저 이 결과를 기준 이미지로 삼습니다.

## 3. 후보 모델 준비 및 비교

후보 모델의 가중치 파일과 라이선스를 각각 확인한 뒤 ComfyUI의 models/checkpoints 폴더에 직접 설치합니다. 코드 저장소의 라이선스가 모델 가중치에 자동으로 적용되는 것은 아닙니다.

추천 비교 후보:

- DreamShaper XL: https://huggingface.co/Lykon/dreamshaper-xl-1-0
- Animagine XL 4.0: https://huggingface.co/cagliostrolab/animagine-xl-4.0

모델을 설치한 다음 정확한 파일명을 다시 확인합니다.

    .\.venv\Scripts\python.exe -m scripts.image_quality_test --list-checkpoints

목록에 표시된 이름을 그대로 전달해 후보를 생성합니다. 아래 파일명은 예시이므로 실제 목록에 표시된 이름으로 바꿔야 합니다.

    .\.venv\Scripts\python.exe -m scripts.image_quality_test --phase candidates --run-id public-wifi-v1 --seed 20261108 --sdxl-models "DreamShaperXL.safetensors" "AnimagineXL.safetensors"

기존 기준선과 같은 --run-id, --seed를 사용해야 한 보고서에 결과가 추가됩니다. 후보를 하나씩 실행해도 됩니다. 이미 생성된 결과는 자동으로 건너뛰고 아직 없는 결과만 생성합니다. 의도적으로 재생성할 때만 --overwrite를 붙입니다.

추가 SD 1.5 후보를 비교할 때는 --sd15-models "파일명.safetensors"를 사용할 수 있습니다.

## 4. 결과 평가

다음 항목을 각 이미지에 1~5점으로 기록합니다.

| 평가 항목 | 확인할 내용 |
|---|---|
| 주제 적합도 | 카페에서 스마트폰을 사용하는 한 장면을 표현했는가 |
| 구성 준수 | 한 장면만 표현하고 스티커 시트·격자·콜라주가 없는가 |
| 선명도 | 피사체와 윤곽이 뚜렷한가 |
| 형태 완성도 | 얼굴, 손, 휴대전화, 노트북의 형태가 자연스러운가 |
| 스타일 완성도 | 색상·선·배경이 카드뉴스에 어울리는가 |
| 수정 가능성 | 같은 모델에서 프롬프트·설정을 조정하면 개선될 여지가 있는가 |

기록 템플릿:

| 모델 / 설정 | 주제 | 구성 | 선명도 | 형태 | 스타일 | 생성 시간 | 총점 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SD 1.5 기본 |  |  |  |  |  |  |  |
| SD 1.5 Hires |  |  |  |  |  |  |  |
| 후보 A |  |  |  |  |  |  |  |
| 후보 B |  |  |  |  |  |  |  |

주제·구성·선명도 중 하나라도 2점 이하인 모델은 최종 후보에서 제외하는 것을 권장합니다. 총점만으로 선택하지 말고 생성 이미지 원본을 함께 확인합니다.

## 5. RTX 3060 12GB 사용 시 주의

- 첫 비교는 이미지를 한 장씩 순차 생성합니다.
- ComfyUI와 Ollama가 VRAM을 동시에 많이 사용하지 않도록 이미지 생성 전 Ollama 모델을 언로드하는 편이 좋습니다.
- SDXL에서 메모리 부족이 발생하면 해상도를 무작정 낮추기 전에 ComfyUI의 메모리 모드와 오프로딩 상태를 확인합니다.
- GPU 가속 여부는 생성 시간과 VRAM 사용에 영향을 주지만 이미지 구도·스타일의 적합성을 대신 개선하지는 않습니다.

## 생성 기록

각 실행은 다음 정보를 report.json에 보관합니다.

- 모델 파일명 및 프로필
- 동일 Seed와 프롬프트
- 해상도, 스텝, CFG, 샘플러, 스케줄러
- Hires 설정
- ComfyUI prompt ID, 실제 출력 크기, 파일 크기, 생성 시간

이 도구는 실제 GPU 생성 결과를 자동으로 합격 판정하지 않습니다. 점수와 최종 모델 선택은 원본 이미지를 확인한 뒤 수행합니다.
