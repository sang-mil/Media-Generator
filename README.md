# Self-improving Media Pipeline (Local MVP v0.5)

Windows PC에서 실행하는 로컬 우선 SNS 콘텐츠 제작 파이프라인입니다. 기본 창작 모델은 `gemma4:26b`이며, Ollama JSON Schema 구조화 출력과 Pydantic 검증을 사용합니다. 콘텐츠를 한 번에 긴 JSON으로 생성하던 v0.2와 달리, 스토리 설계 → 이미지 프롬프트/캡션 → 출처 자료 대조 검수 단계로 나누어 출력 잘림과 기술적 혼동을 줄입니다.

## Instagram 카드뉴스 디자인 (v0.5)

주제 등록 시 아래 템플릿 중 하나를 선택할 수 있습니다.

- **화이트 배경 · 캐릭터 설명형**: 단순한 캐릭터 일러스트와 설명 카드 중심
- **이미지 배경 · 검정 하단 설명형**: 상단 이미지와 검정색 하단 캡션 영역
- **미니멀 인포그래픽형**: 여백, 간단한 일러스트, 핵심 정보 카드 중심

ComfyUI는 원본 그림만 생성합니다. Pillow가 한글 제목·설명·페이지 번호를 1080×1350px(Instagram 세로형 4:5) PNG에 합성하고, 네 장의 결과를 ZIP으로 묶습니다. 원본 이미지 URL도 유지하므로 합성 실패 시 원본 그림을 확인할 수 있습니다.

> 품질 한계: 현재 SD 1.5 기본 체크포인트를 사용하는 한 그림체의 완성도와 캐릭터 일관성은 제한됩니다. 텍스트 기반 캐릭터 가이드는 IPAdapter/참조 이미지 기반 정체성 고정을 대체하지 않습니다. 이번 버전은 생성 이미지에 글자와 복잡한 컷 구성을 맡기지 않고, 단순한 일러스트와 앱 측 레이아웃 합성으로 결과의 가독성과 게시물 완성도를 높이는 단계입니다.

## v0.3 주요 변경

- Gemma 4 26B A4B를 기본 모델 후보로 설정
- Ollama `/api/chat`의 `format`에 Pydantic JSON Schema를 전달해 구조화 출력 강제
- JSON 파싱뿐 아니라 Pydantic 스키마 검증
- 출력 `done_reason=length`, JSON 오류, 스키마 오류에 대해 최대 2회 재시도
- 대본 설계와 이미지 프롬프트/캡션 생성을 별도 단계로 분리
- 사실 주장을 별도 목록으로 추출하고 출처 제공 여부를 표시
- 사용자가 제공한 자료가 있을 때만 해당 자료와 주장 사이의 일치 여부를 AI로 대조
- 출처가 없으면 사실 확인 완료로 처리하지 않고 `검증 필요`로 표시
- AI 검수는 독립적인 사실 검증이 아님을 UI에 명시
- 여러 LLM 단계에서는 모델을 `10m` 유지해 재로딩을 줄이고, 전체 LLM 작업이 끝나면 기본 설정상 모델을 언로드해 ComfyUI에 VRAM을 양보
- SQLite 기존 데이터 유지 및 v0.3 컬럼 자동 마이그레이션
- 검수 상태, 주장별 판정, 단계별 모델/토큰/생성 시간 기록을 초안에 저장
- Windows 실행 스크립트는 검증된 전체 스크립트를 사용하고 Gemma 우선 탐색

## 중요한: 기존 `.env` 모델 설정 확인

기존 설치에서 `.env`에 이전 모델명이나 `OLLAMA_KEEP_ALIVE=0`이 저장되어 있으면 실행 스크립트는 기존 모델명을 존중합니다. Gemma 4로 전환하고 3단계 생성 중 모델을 계속 메모리에 유지하려면 프로젝트 폴더의 `.env`에 아래 항목을 적용하세요.

```env
OLLAMA_MODEL=gemma4:26b
OLLAMA_STAGE_KEEP_ALIVE=10m
OLLAMA_NUM_CTX=8192
OLLAMA_UNLOAD_AFTER_GENERATION=true
```

`.env.example`은 새 설치의 기본값이며, 기존 `.env`를 자동으로 덮어쓰지 않습니다. 구버전의 `OLLAMA_KEEP_ALIVE=0`은 v0.3 단계별 호출에 사용하지 않으며, 새 설정 `OLLAMA_STAGE_KEEP_ALIVE=10m`을 추가하세요.

## 처리 흐름

1. `run.ps1`이 Ollama를 시작하고 설치된 모델을 확인합니다.
2. 대기 주제가 없으면 AI가 주제 후보를 만듭니다.
3. **스토리 설계 단계**에서 제목, 훅, 캐릭터, 4컷 장면/대사/핵심 정보를 JSON Schema로 생성합니다.
4. **크리에이티브 패키징 단계**에서 컷별 이미지 프롬프트, 캡션, 해시태그를 별도 생성합니다.
5. **기술 검수 단계**는 주제 입력에 출처 자료가 제공된 경우에만 그 자료와 사실 주장을 대조합니다.
6. 출처 자료가 없으면 각 기술 주장은 `needs_verification` 상태로 남습니다.
7. LLM 단계 종료 후 모델을 언로드하고 ComfyUI 이미지 생성을 시도합니다.
8. 이미지, 대본, 검수 결과를 SQLite에 저장합니다.
9. 사용자가 사실·이미지·저작권을 확인하고 직접 승인한 뒤 Instagram에 수동 게시합니다.
10. 게시 후 성과를 입력하면 다음 콘텐츠 추천에 반영합니다.

## 기술 검수의 한계

- URL만 입력해도 앱이 인터넷을 열람하거나 출처 원문을 자동 확인하지 않습니다. 출처 문서의 핵심 발췌문을 `검증 자료 / 공식 문서 발췌` 칸에 붙여 넣으세요.
- AI 검수는 제공된 텍스트와 모델 주장의 일치 여부를 분류하는 보조 절차입니다. 원문 출처의 진위, 게시 시점의 최신성, 적용 범위를 독립적으로 검증하지 않습니다.
- `supported_by_material`은 자료 안에 근거가 있다는 AI 판단이지 법률·기술적으로 검증 완료를 뜻하지 않습니다.
- 최종 게시 전 사람이 출처 원문과 현재 적용 여부를 확인해야 합니다.

## Ollama 구조화 출력

현재 Ollama API는 `/api/chat`의 `format` 필드에 JSON Schema를 전달하는 구조화 출력을 지원합니다. 프로젝트는 Pydantic `model_json_schema()`를 전달하고 응답을 다시 Pydantic 모델로 검증합니다. 출력이 잘리거나 스키마가 맞지 않으면 토큰 예산을 늘려 최대 2회 재시도합니다.

공식 문서: https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx

## 실행 환경

- Windows 10/11
- Windows PowerShell 5.1 이상
- Python 3.11 이상 (3.12 권장)
- Ollama for Windows 및 모델 1개 이상
- ComfyUI Portable 및 호환 체크포인트 (이미지 생성에 필요)

실행:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run.ps1
```

앱: `http://127.0.0.1:8765`  
API 문서: `http://127.0.0.1:8765/docs`  
종료: ` .\stop.ps1 `

`run.ps1`은 앱을 시작할 때 Ollama와 ComfyUI의 실행 상태를 확인합니다. `.env`가 있으면 기존 설정을 유지하고, 없으면 `.env.example`에서 생성합니다.

## 메모리 운용

기본값은 `OLLAMA_STAGE_KEEP_ALIVE=10m`, `OLLAMA_UNLOAD_AFTER_GENERATION=true`입니다. 스토리·패키징·검수의 다단계 LLM 호출 사이에는 모델을 메모리에 유지하고, 모든 언어 모델 작업이 끝나면 한 번에 언로드합니다. 이후 ComfyUI가 GPU를 사용합니다.

RTX 3060 12GB처럼 VRAM이 제한적인 환경에서는 Ollama와 ComfyUI를 동시에 실행하더라도 생성 시점의 VRAM 경합이 발생할 수 있습니다. 언로드가 실패하면 UI 생성/이미지 생성 로그를 확인하세요.

## 데이터와 로그

- SQLite: `media_pipeline.sqlite3`
- 이미지: `generated/<post_id>/panel_01.png` 등
- 설정: `.env`
- 로그: `.logs/app.stdout.log`, `.logs/app.stderr.log`
- 앱 PID: `.app.pid`

기존 DB에 `topics.source_notes`, `posts.technical_review_json`, `posts.generation_meta_json`을 자동 추가합니다. 기존 게시물과 성과 데이터는 삭제하지 않습니다.

## 아직 구현하지 않은 항목

- Instagram 공식 API OAuth 및 자동 게시
- Instagram Insights 자동 수집
- ComfyUI 참조 이미지/IP-Adapter 기반 캐릭터 일관성 강화
- 브라우저 기반 출처 자동 수집 및 검증
- 자동 게시 및 콘텐츠 전략 자동 변경

게시 전 사람의 승인과 검토는 계속 유지합니다. 로컬 PC가 절전/종료 상태이면 자동화가 실행되지 않습니다.

## 테스트

프로젝트 루트에서 테스트 의존성을 설치한 뒤 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements-dev.txt`는 앱 실행에는 필요하지 않은 테스트 전용 의존성(`httpx2`)을 추가합니다.

## 라이선스

이 프로젝트에는 아직 별도 오픈소스 라이선스를 부여하지 않았습니다. 공개 또는 제3자 배포 전 라이선스를 결정하세요. Ollama, 모델 및 ComfyUI의 라이선스는 각 프로젝트/모델의 별도 조건을 따릅니다.
