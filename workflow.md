# Anchor-Voice 개발 워크플로우

> **20대를 위한 지능형 모바일 뱅킹 에이전트** — 개발 실행 가이드  
> `service_plan.md` 기반 에이전트별 병렬 실행 절차 및 검증 방법

**팀:** 4조 (장원재, 김금비, 민채영)  
**마지막 업데이트:** 2026-04-02

---

## WBS (Work Breakdown Structure)

> **6개의 AI 코딩 에이전트**가 병렬로 서비스를 개발한다.  
> 각 에이전트는 `service_plan.md §8`에 정의된 컨텍스트·지시 프롬프트·산출 파일 기준으로 호출된다.

---

### 📋 에이전트 호출 순서 개요

```
STEP 0 ─── [인터페이스 합의] ──────────────────────────────────────── 모든 에이전트 호출 전 필수
             backend/schemas.py Pydantic 모델 5종 확정

STEP 1 ─── [Agent 1: DevOps] ─────────────────────────────────────── 단독 실행, 선행 조건
             └─ 환경·디렉토리·requirements.txt·README.md 완성
             └─ 완료 기준: uv sync 성공, 디렉토리 구조 생성

STEP 2 ─── 병렬 실행 ──────────────────────────────────────────────── DevOps 완료 후 동시 호출
             ├─ [Agent 2: Vision]   ai/cdd_scorer.py, deepface_auth.py
             ├─ [Agent 3: LLM]     ai/anchor_prompts.py, llm_engine.py, whisper_stt.py, gtts_tts.py
             └─ [Agent 4: Backend] backend/schemas.py → router.py, stealth_sos.py

STEP 3 ─── [Agent 5: Frontend] ───────────────────────────────────── schemas.py 완료 후 호출
             └─ frontend/app.py + components/ 5종

STEP 4 ─── [Agent 6: Tester] ─────────────────────────────────────── STEP 2+3 완료 후 호출
             └─ tests/ conftest, test_*.py, scenarios/*.json

STEP 5 ─── [전체 검증·데모] ──────────────────────────────────────── E2E 통합 테스트 후 발표 준비
```

---

### ⚡ Week 1 (Day 1~7): 파이프라인 구축

#### STEP 0 — 인터페이스 합의 (Day 1, 2시간, 전체 참여)

> **시작 전 필수.** 이 합의가 끝나야 각 에이전트가 독립적으로 코드를 작성할 수 있다.

| 합의 항목 | 값 |
|---------|---|
| 위험도 임계값 | ≥70 = 고위험, <30 = 저위험 |
| LLM 응답 스키마 | `{"is_phishing": bool, "confidence": float, "phishing_type": str}` |
| 앵커 질문 스키마 | `{"question_id": int, "text": str, "answer": bool}` |
| 스텔스 SOS 트리거 | `{"ui_mode": "stealth_complete", "blocked": True}` |
| STT 입력 포맷 | `bytes` (PCM 16kHz 또는 mp3) |

**→ Agent 4(Backend)가 즉시 `backend/schemas.py`에 Pydantic 모델로 코드화한다.**

---

#### STEP 1 — Agent 1: DevOps Agent 호출 (Day 1)

**호출 목적:** 모든 에이전트가 동일한 환경에서 개발할 수 있도록 기반 구조를 생성한다.

**에이전트에게 제공할 컨텍스트:**
- `pyproject.toml`, `.env.example`, `service_plan.md §6.1`

**기대 산출물:**

| 파일 | 완료 기준 |
|------|---------|
| `requirements.txt` | `uv sync` 또는 `pip install` 성공 |
| `.env.example` | 모든 API 키 항목 + 주석 포함 |
| `backend/`, `ai/`, `frontend/`, `tests/` + `__init__.py` | 디렉토리 존재 확인 |
| `README.md` | `uv sync → uvicorn → streamlit run` 절차 기재 |

```bash
# DevOps Agent 완료 검증
python -c "import fastapi, streamlit, deepface; print('OK')"
```

---

#### STEP 2 — 병렬 호출 (Day 2~6): Vision + LLM + Backend

> **3개 에이전트를 동시에 호출한다.** 각 에이전트는 서로의 코드를 기다리지 않고 독립적으로 작성한다.  
> 단, Backend Agent의 `schemas.py`는 Day 2에 먼저 커밋하여 Frontend Agent가 참조할 수 있게 한다.

---

**🔵 Agent 2: Vision Agent 호출 (Day 2~5)**

**에이전트에게 제공할 컨텍스트:**
- `service_plan.md §3.1`, `§6.1`, `§8.3`
- `backend/schemas.py` (RiskCheckRequest/Response 참조)

**기대 산출물 및 일정:**

| Day | 파일 | 완료 기준 |
|-----|------|---------|
| 2~3 | `ai/cdd_scorer.py` | `calculate_risk_score()` 반환값 0~100 확인 |
| 4~5 | `ai/deepface_auth.py` | 웹캠 캡처 → 비교 → `{"verified": bool}` 반환 |
| 5 | `tests/test_vision.py` | pytest 3케이스 통과 |

```bash
# Vision Agent 완료 검증
python -m pytest tests/test_vision.py -v
```

---

**🟢 Agent 3: LLM Agent 호출 (Day 2~6)**

**에이전트에게 제공할 컨텍스트:**
- `service_plan.md §3.2`, `§4.2`
- `workflow.md §Phase 2` (앵커 질문 5종 + 판별 기준)
- `stt_output/` 샘플 텍스트 3~5개
- `backend/schemas.py` (PhishingAnalysisResponse 참조)

**기대 산출물 및 일정:**

| Day | 파일 | 완료 기준 |
|-----|------|---------|
| 2~3 | `ai/anchor_prompts.py` | SYSTEM_PROMPT + ANCHOR_QUESTIONS 5종 정의 |
| 3~4 | `ai/whisper_stt.py` | 오디오 bytes → 한국어 텍스트 변환 성공 |
| 4~5 | `ai/gtts_tts.py` | 텍스트 → 음성 bytes(mp3) 변환 성공 |
| 5~6 | `ai/llm_engine.py` | Gemini API 호출 → 판별 결과 dict 반환 |
| 6 | `tests/test_llm.py` | 3시나리오 판별 정확도 ≥85% |

```bash
# LLM Agent 완료 검증
python -m pytest tests/test_llm.py -v
```

---

**🟡 Agent 4: Backend Agent 호출 (Day 2~6)**

**에이전트에게 제공할 컨텍스트:**
- `service_plan.md §5 시스템 아키텍처`, `§3.1`, `§3.3`
- `service_plan.md §4.1` 기능 명세 (F-08, F-09)

**기대 산출물 및 일정:**

| Day | 파일 | 완료 기준 |
|-----|------|---------|
| 2 | `backend/schemas.py` | 5종 Pydantic 모델 완성 → **즉시 커밋** |
| 2~3 | `backend/config.py`, `backend/main.py` | `GET /health` 응답 |
| 3~4 | `backend/router.py` | 6개 엔드포인트 라우팅 |
| 4~5 | `backend/stealth_sos.py` | 차단 + WARNING 로그 + SosResponse 반환 |
| 5~6 | Vision·LLM 모듈 import 연동 | curl 테스트 통과 |
| 6 | `tests/test_api.py` | httpx TestClient 통합 테스트 통과 |

```bash
# Backend Agent 완료 검증
uvicorn backend.main:app --reload &
curl http://localhost:8000/health
python -m pytest tests/test_api.py -v
```

---

#### STEP 3 — Agent 5: Frontend Agent 호출 (Day 3~6)

> **`backend/schemas.py` 커밋 직후 호출 가능.** Day 2 저녁부터 병렬 시작.

**에이전트에게 제공할 컨텍스트:**
- `service_plan.md §5.1 데이터 흐름`, `§3.3 스텔스 SOS`
- `backend/schemas.py` (요청/응답 스키마)

**기대 산출물 및 일정:**

| Day | 파일 | 완료 기준 |
|-----|------|---------|
| 3 | `frontend/state_manager.py` | session_state 기반 화면 전환 로직 |
| 3~4 | `frontend/components/transfer_ui.py` | 이체 입력 폼 렌더링 |
| 4 | `frontend/components/face_ui.py` | 웹캠 스트림 화면 |
| 4~5 | `frontend/components/voice_ui.py` | 대화 화면 (STT/TTS 연동) |
| 5~6 | `frontend/components/stealth_ui.py` | **위장 완료 UI + 백그라운드 /api/sos/trigger 호출** |
| 6 | `frontend/components/result_ui.py`, `frontend/app.py` | `localhost:8501` 정상 접근 |

```bash
# Frontend Agent 완료 검증
streamlit run frontend/app.py &
# 브라우저에서 http://localhost:8501 접근 후 이체 플로우 확인
```

---

#### STEP 4 — Agent 6: Tester Agent 호출 (Day 7)

> **STEP 2+3 전체 완료 후 호출.** 모든 모듈이 동작하는 상태에서 통합 검증을 수행한다.

**에이전트에게 제공할 컨텍스트:**
- `service_plan.md §10 KPI`, `workflow.md §Phase 9 시나리오 A·B·C`
- `backend/schemas.py`, `ai/anchor_prompts.py`

**기대 산출물:**

| 파일 | 완료 기준 |
|------|---------|
| `tests/conftest.py` | FastAPI TestClient fixture, 샘플 오디오 fixture |
| `tests/scenarios/normal.json` | 정상 이체 입력·기대 출력 정의 |
| `tests/scenarios/loan_fraud.json` | 대출사기 입력·기대 출력 정의 |
| `tests/scenarios/agency_fraud.json` | 수사기관사칭 입력·기대 출력 정의 |
| `tests/test_latency.py` | CDD ≤500ms, STT ≤2000ms, LLM ≤3000ms assert |

```bash
# Tester Agent 완료 검증 (E2E)
python -m pytest tests/ -v --tb=short
```

---

### 🔧 Week 2 (Day 8~14): 고도화 및 최종 검증

> Week 1 완료 후, 각 에이전트를 **추가 컨텍스트(테스트 결과, 버그 리포트)** 와 함께 재호출하여 품질을 높인다.

| Day | 재호출 에이전트 | 추가 컨텍스트 | 목표 |
|-----|------------|------------|------|
| 8~9 | Vision | `tests/test_vision.py` 실패 케이스 | 인식률 ≥90%, fallback 강화 |
| 8~9 | LLM | 앵커 질문 테스트 실패 케이스 + `stt_output/` 추가 샘플 | 판별 정확도 ≥85%, Edge Case |
| 8~9 | Backend | `tests/test_api.py` 응답 시간 측정 결과 | 비동기 최적화, 에러 처리 |
| 8~9 | Frontend | UX 피드백 (화면 흐름 어색한 부분) | 스텔스 SOS 자연스러움 개선 |
| 10~11 | Tester | 전체 시나리오 재실행 결과 | 버그 리포트 작성, 재검증 |
| 12~13 | 전체 | 버그 리포트 | 수정 + 재테스트 |
| 14 | Frontend | 최종 확인 상태 | 데모 영상 녹화 |

---

### 병렬 실행 의존성 다이어그램

```
Day 1    Day 2           Day 3~6              Day 7        Day 8~14
  │        │                │                  │              │
[합의]──▶[DevOps]──┬──▶[Vision Agent  ]──┐              │
                   ├──▶[LLM Agent     ]──┤──▶[통합]──▶[고도화]──▶[데모]
                   ├──▶[Backend Agent ]──┤    E2E
                   │        │            │   테스트
                   │   schemas.py완료    │
                   └──────▶[Frontend Agent]──┘
                              (Day 3~)
                   └──────────────────────▶[Tester Agent]
                                                (Day 7)
```

---



### 전체 일정 개요

```
Day  │ DevOps        │ Vision           │ LLM              │ Backend         │ Frontend        │ Tester
─────┼───────────────┼──────────────────┼──────────────────┼─────────────────┼─────────────────┼──────────────────
 1   │ 🛠 환경세팅    │ 📊 데이터파악     │ 📊 데이터파악     │ ⚙ 스키마합의    │ 🎨 UI와이어프레임 │ 📋 시나리오설계
 2   │ 🛠 deps확정    │ 📊 STT배치실행   │ 📊 STT배치실행    │ ⚙ schemas.py    │ 🎨 state_mgr    │ 📋 테스트케이스
─────┼───────────────┼──────────────────┼──────────────────┼─────────────────┼─────────────────┼──────────────────
 3   │ 🛠 README초안  │ 👁 cdd_scorer    │ 🧠 anchor_prompts │ ⚙ main.py       │ 🎨 transfer_ui  │ 🧪 test_cdd작성
 4   │               │ 👁 deepface_auth │ 🧠 whisper_stt    │ ⚙ router.py     │ 🎨 face_ui      │ 🧪 test_llm작성
─────┼───────────────┼──────────────────┼──────────────────┼─────────────────┼─────────────────┼──────────────────
 5   │               │ 👁 단위테스트     │ 🧠 gtts_tts       │ ⚙ stealth_sos   │ 🎨 voice_ui     │ 🧪 test_vision
 6   │               │ 👁 Edge Case      │ 🧠 llm_engine    │ ⚙ API연동검증   │ 🎨 stealth_ui   │ 🧪 test_api작성
─────┼───────────────┼──────────────────┼──────────────────┼─────────────────┼─────────────────┼──────────────────
 7   │ 🛠 통합확인    │ ✅ Vision완료     │ ✅ LLM완료        │ ✅ Backend완료   │ ✅ Frontend완료  │ 🔗 E2E통합테스트
─────┼───────────────┼──────────────────┼──────────────────┼─────────────────┼─────────────────┼──────────────────
 8   │               │ 🔧 정확도향상     │ 🔧 프롬프트고도화 │ 🔧 비동기최적화  │ 🔧 UX개선        │ 🧪 시나리오검증
 9   │               │ 🔧 fallback강화  │ 🔧 Edge Case대응  │ 🔧 에러처리강화  │ 🔧 스텔스SOS완성 │ 🧪 성능측정
─────┼───────────────┼──────────────────┼──────────────────┼─────────────────┼─────────────────┼──────────────────
10   │               │                  │                  │                 │                 │ 🧪 전체시나리오
11   │               │ 🔧 최종검증       │ 🔧 최종검증       │ 🔧 최종검증      │ 🔧 최종검증      │ 🧪 버그리포트
12   │               │                  │                  │                 │                 │ 📋 데모준비
─────┴───────────────┴──────────────────┴──────────────────┴─────────────────┴─────────────────┴──────────────────
```

---

## WBS 상세: 에이전트별 병렬 태스크

### ⚡ Week 1 (Day 1~7): 파이프라인 구축

#### [공통 선행] Day 1~2 — 인터페이스 합의 (전원 참여, 2시간)

> 이 합의가 끝나야 각 에이전트가 독립적으로 병렬 개발을 시작할 수 있다.

```
합의 항목:
  ✔ 위험도 점수 임계값: ≥70 = 고위험
  ✔ LLM 응답 스키마: {"is_phishing": bool, "confidence": float, "phishing_type": str}
  ✔ 스텔스 SOS 트리거: {"ui_mode": "stealth_complete", "blocked": True}
  ✔ 앵커 질문 스키마: {"question_id": int, "text": str, "answer": bool}
  ✔ STT 입력 포맷: bytes (PCM 16kHz or mp3)
```

---

#### 🛠️ DevOps Agent (장원재) — Day 1~2, Day 7

| Day | 작업 | 산출물 | 완료 기준 |
|-----|------|--------|---------|
| 1 | 환경 세팅, uv sync 검증 | `.venv` 정상 | 모든 팀원 import 오류 없음 |
| 2 | `requirements.txt` 정비, `.env.example` 갱신 | 환경파일 | `uv sync` 성공 |
| 7 | `README.md` 초안 작성, E2E 실행 스크립트 확인 | `README.md` | 타팀원 실행 재현 가능 |

#### 👁️ Vision Agent (장원재) — Day 3~7 (DevOps와 병행)

| Day | 작업 | 산출물 | 완료 기준 |
|-----|------|--------|---------|
| 1~2 | STT 배치 실행 (`stt_batch_pipeline.py`), 데이터 현황 확인 | `stt_output/` | 185+227개 txt 생성 |
| 3 | `ai/cdd_scorer.py` 구현 | `cdd_scorer.py` | 위험/비위험 분류 출력 |
| 4 | `ai/deepface_auth.py` PoC | `deepface_auth.py` | 웹캠 인식 성공 |
| 5~6 | Edge Case 처리 (조도·각도), fallback 로직 | 수정본 | 인식률 ≥90% |
| 7 | Vision 단위 테스트 통과 확인 | — | `tests/test_vision.py` 통과 |

#### 🧠 LLM Agent (민채영) — Day 1~7 (Backend와 병행)

| Day | 작업 | 산출물 | 완료 기준 |
|-----|------|--------|---------|
| 1~2 | STT 배치 실행 참여 (Vision과 공동), 앵커 질문 초안 분석 | 패턴 분석 노트 | 앵커 질문 5종 초안 확정 |
| 3 | `ai/anchor_prompts.py` 작성 (판별 기준 포함) | `anchor_prompts.py` | 시나리오별 판별 기준 코드화 |
| 4 | `ai/whisper_stt.py` 구현 | `whisper_stt.py` | 음성→텍스트 변환 성공 |
| 5 | `ai/gtts_tts.py` 구현 | `gtts_tts.py` | 텍스트→음성 출력 성공 |
| 6 | `ai/llm_engine.py` Gemini 연동 | `llm_engine.py` | 판별 정확도 ≥85% |
| 7 | LLM 단위 테스트 통과 확인 | — | `tests/test_llm.py` 통과 |

#### ⚙️ Backend Agent (민채영) — Day 2~7 (LLM과 병행)

| Day | 작업 | 산출물 | 완료 기준 |
|-----|------|--------|---------|
| 2 | `backend/schemas.py` 정의 (인터페이스 합의 반영) | `schemas.py` | Pydantic 스키마 완성 |
| 3 | `backend/main.py` FastAPI 기본 서버 | `main.py` | `/health` 응답 |
| 4 | `backend/router.py` 동적 라우팅 로직 | `router.py` | 저위험/고위험 분기 |
| 5 | `backend/stealth_sos.py` 차단 로직 | `stealth_sos.py` | 차단 이벤트 로그 |
| 6 | Vision·LLM 모듈 API 연동 검증 | — | curl 테스트 통과 |
| 7 | Backend 통합 확인 | — | `tests/test_api.py` 통과 |

#### 🎨 Frontend Agent (김금비) — Day 1~7

| Day | 작업 | 산출물 | 완료 기준 |
|-----|------|--------|---------|
| 1 | UI 와이어프레임 설계 (화면 흐름 확정) | 와이어프레임 스케치 | 5개 화면 정의 완료 |
| 2 | `frontend/state_manager.py` 구현 | `state_manager.py` | 화면 전환 상태 관리 |
| 3 | `frontend/components/transfer_ui.py` | `transfer_ui.py` | 이체 입력 화면 렌더링 |
| 4 | `frontend/components/face_ui.py` | `face_ui.py` | 웹캠 화면 렌더링 |
| 5 | `frontend/components/voice_ui.py` | `voice_ui.py` | 대화 화면 렌더링 |
| 6 | `frontend/components/stealth_ui.py` **[핵심]** | `stealth_ui.py` | 위장 완료 UI 렌더링 |
| 7 | `frontend/app.py` 전체 통합, Streamlit 실행 | `app.py` | `localhost:8501` 전체 흐름 |

#### 🧪 Tester Agent (장원재) — Day 1~7 (Vision과 병행)

| Day | 작업 | 산출물 | 완료 기준 |
|-----|------|--------|---------|
| 1 | 피싱 시나리오 3종 설계 | `tests/scenarios/*.json` | 정상·대출사기·수사기관사칭 |
| 2 | 테스트 케이스 작성 계획 수립 | 테스트 계획서 | 커버리지 항목 확정 |
| 3 | `tests/test_cdd.py` 작성 | `test_cdd.py` | 3개 케이스 정의 |
| 4 | `tests/test_llm.py` 작성 | `test_llm.py` | 3개 케이스 정의 |
| 5 | `tests/test_vision.py` 작성 | `test_vision.py` | 3개 케이스 정의 |
| 6 | `tests/test_api.py` 작성 | `test_api.py` | API 엔드포인트 커버 |
| 7 | **E2E 통합 테스트 실행** | 테스트 결과 | 전체 흐름 작동 확인 |

---

### 🔧 Week 2 (Day 8~14): 고도화 및 최종 검증

> Week 2는 Week 1 산출물을 기반으로 **각 에이전트가 독립적으로 품질을 높이고**, Day 12~14에 최종 통합·데모를 진행한다.

```
Day 8~11: 각 에이전트 독립 고도화 (병렬)
Day 12:   전체 E2E 시나리오 테스트 (Tester 주도)
Day 13:   버그 수정 및 성능 최적화 (전체)
Day 14:   데모 영상 녹화 + 발표 자료 완성 (전체)
```

| Day | DevOps | Vision | LLM | Backend | Frontend | Tester |
|-----|--------|--------|-----|---------|----------|--------|
| 8 | 실행 스크립트 정비 | 인식 정확도 향상 | 앵커 질문 고도화 | 비동기 처리 최적화 | UX 개선 | 시나리오 A·B 검증 |
| 9 | — | fallback 강화 | Edge Case 대응 | 에러 처리 강화 | 스텔스 SOS 완성도 | 시나리오 C 검증 |
| 10 | — | 최종 인식률 측정 | 판별 정확도 측정 | 응답 시간 측정 | 전체 화면 UX 점검 | 전체 시나리오 반복 |
| 11 | README 최종화 | Vision 최종 확인 | LLM 최종 확인 | Backend 최종 확인 | Frontend 최종 확인 | 버그 리포트 작성 |
| 12 | — | 버그 수정 | 버그 수정 | 버그 수정 | 버그 수정 | 재검증 |
| 13 | — | 데모 준비 | 데모 준비 | 데모 준비 | 데모 준비 | 최종 KPI 측정 |
| 14 | 배포 환경 확인 | 발표 자료 | 발표 자료 | 발표 자료 | 데모 영상 녹화 | 검증 결과 정리 |

---

## 병렬 작업 의존성 규칙

```
[Day 1~2] 인터페이스 합의 (필수 선행)
    │
    ├──▶ [Day 3~] Vision Agent: cdd_scorer, deepface_auth 독립 개발
    │
    ├──▶ [Day 3~] LLM Agent: anchor_prompts, whisper_stt, llm_engine 독립 개발
    │
    ├──▶ [Day 2~] Backend Agent: schemas 정의 후 → router, stealth_sos 독립 개발
    │
    ├──▶ [Day 1~] Frontend Agent: 와이어프레임 → 컴포넌트 순차 개발
    │
    └──▶ [Day 1~] Tester Agent: 시나리오 설계 → 단위 테스트 작성

[Day 7] 각 에이전트 Week 1 산출물 완료 → E2E 통합 테스트 (Tester 주도)
    │
    └──▶ [Day 8~11] 병렬 고도화
             │
             └──▶ [Day 12~14] 최종 통합 → 데모 → 발표
```

---

## 목차

1. [환경 세팅](#phase-0-환경-세팅)
2. **[얼굴 등록 (최초 1회)](#phase-00-얼굴-등록--최초-1회)**
3. [오디오 데이터 현황 파악](#phase-1-오디오-데이터-현황-파악)
4. [STT 배치 처리 및 앵커 질문 구조 설계](#phase-2-stt-배치-처리-및-앵커-질문-구조-설계)
5. [CDD 위험도 스코어링 엔진](#phase-3-cdd-위험도-스코어링-엔진)
6. [DeepFace 안면 동작 챌린지 인증 모듈](#phase-4-deepface-안면-동작-챌린지-인증-모듈)
7. [LLM 앵커 보이스 음성 대화 판별 엔진](#phase-5-llm-앵커-보이스-음성-대화-판별-엔진)
8. [FastAPI 백엔드 서버](#phase-6-fastapi-백엔드-서버)
9. [Streamlit 프론트엔드 UI](#phase-7-streamlit-프론트엔드-ui)
10. [스텔스 SOS 모듈](#phase-8-스텔스-sos-모듈)
11. [E2E 통합 테스트](#phase-9-e2e-통합-테스트)

---

## Phase 0: 환경 세팅

> **담당:** 전체 | **목표:** 로컬 실행 가능 상태 만들기

### Step 0-1. 프로젝트 클론 및 의존성 설치

```bash
git clone <repository-url>
cd MAR_pj3_gr4_Anchor-Voice

# 의존성 설치 (uv 권장)
uv sync

# 백엔드 서버 실행
uv run uvicorn backend.main:app --reload --port 8000

# 프론트엔드 실행 (새 터미널)
uv run streamlit run frontend/app.py
```

### Step 0-2. 환경 변수 설정

```bash
copy .env.example .env
# .env 파일에 GEMINI_API_KEY 입력
```

### ✅ Phase 0 완료 기준
- [ ] `uv run uvicorn backend.main:app` 정상 실행
- [ ] `uv run streamlit run frontend/app.py` 정상 실행
- [ ] `http://localhost:8501` 화면 정상 접근

---

## Phase 0-0: 얼굴 등록 (최초 1회)

> **목적:** DeepFace 인증에 필요한 기준 이미지를 최초 1회 등록  
> **주의:** 이 단계를 완료해야 안면 인식 인증을 사용할 수 있음

### 등록 흐름

```
앱 메인 화면
    ├── [이체하기] 탭 → 미등록 상태로 이체 시 비밀번호/공인인증서(돬모) 대체 인증 수행
    └── [얼굴 등록] 탭 → 사용자가 선택적으로 진행
```

### Step 0-0-1. 프론트엔드에서 얼굴 등록 (별도 탭)

1. `http://localhost:8501` 접속
2. 사이드바에서 `[얼굴 등록]` 탭 선택
3. `st.camera_input()`으로 정면 얼굴 촬영 (시연 PC 웹캠 사용)
4. 촬영 버튼 클릭 시 → `POST /api/auth/face/register` 호출
5. 서버가 `registered_face.jpg`로 저장
6. "등록 완료" 메시지 → 이후 이체 시 안면 챌린지 사용 가능

### Step 0-0-2. 등록 상태 확인

```bash
# 등록 파일 존재 확인
ls registered_face.jpg
```

### 등록 시 주의사항

| 항목 | 권장 사항 |
|------|---------|
| 조도 | 밝은 환경에서 촬영 |
| 각도 | 카메라 정면, 얼굴 중앙 위치 |
| 표정 | 자연스러운 중립 표정 |
| 배경 | 단색 배경 권장 |

### ✅ Phase 0-0 완료 기준
- [ ] `registered_face.jpg` 파일 생성 확인
- [ ] face_ui.py에서 등록 완료 메시지 표시
- [ ] 이체 화면으로 정상 이동

---


## Phase 0: 환경 세팅

> **담당:** 전체 | **목표:** 로컬 실행 가능 상태 만들기

### Step 0-1. 프로젝트 클론 및 디렉토리 이동

```bash
git clone <repository-url>
cd MAR_pj3_gr4_Anchor-Voice
```

### Step 0-2. Python 버전 확인

이 프로젝트는 **Python 3.12** 이상을 요구한다 (`pyproject.toml` 기준).

```bash
python --version
# Python 3.12.x 이상이어야 함
```

### Step 0-3. 가상 환경 세팅 (uv 사용 권장)

`pyproject.toml`에 이미 `uv` 기반 의존성이 정의되어 있다.

```bash
# uv가 없는 경우 설치
pip install uv

# 가상환경 생성 및 의존성 설치
uv sync
```

> **대안 (pip 사용 시)**
> ```bash
> python -m venv .venv
> .venv\Scripts\activate        # Windows
> pip install -r requirements.txt
> ```

### Step 0-4. 환경 변수 설정

`.env.example`을 복사하여 `.env` 파일을 만들고 API 키를 입력한다.

```bash
copy .env.example .env
```

`.env` 파일 필수 항목:

```env
# LLM API Keys
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here   # GPT 백업용

# 위험도 판별 임계값 (기본값 사용 가능)
RISK_THRESHOLD_HIGH=70
RISK_THRESHOLD_LOW=30
```

### Step 0-5. 디렉토리 구조 확인

```
MAR_pj3_gr4_Anchor-Voice/
├── scripts/
│   ├── fss_audio_crawler.py     ← Phase 1: FSS 피싱 오디오 크롤러
│   └── stt_batch_pipeline.py    ← Phase 2: STT 배치 처리
├── downloads/                   ← 크롤링된 오디오 저장 경로
├── stt_output/                  ← STT 변환 결과 저장 경로
├── backend/                     ← Phase 6: FastAPI 서버 (생성 예정)
├── ai/                          ← Phase 3~5: AI 모듈 (생성 예정)
├── frontend/                    ← Phase 7: Streamlit UI (생성 예정)
├── tests/                       ← Phase 9: 테스트 케이스 (생성 예정)
├── pyproject.toml
├── requirements.txt
└── .env
```

### ✅ Phase 0 완료 기준

- [ ] Python 3.12+ 환경 확인
- [ ] `uv sync` 또는 `pip install` 완료, import 오류 없음
- [ ] `.env` 파일 생성 및 API 키 입력 완료

---

## Phase 1: 오디오 데이터 현황 파악

> **담당:** 장원재 | **기능:** 실제 보이스피싱 대화 데이터 검증 및 분류 파악  
> **데이터 경로:** `downloads/fss_audio/`

### 보유 데이터 현황 (이미 분류 완료)

실제 보이스피싱범과 피해자의 대화 오디오가 수법 유형별로 분류되어 있다.

| 유형 | 경로 | 파일 수 | 주요 수법 패턴 |
|------|------|--------|---------------|
| **대출사기형** | `downloads/fss_audio/대출사기형/` | **185개** | 저금리 대환대출 미끼, 선입금 유도, 대포통장·인출책 모집 |
| **수사기관사칭형** | `downloads/fss_audio/수사기관사칭형/` | **227개** | 검찰·경찰·금감원 사칭, 명의도용 협박, 안전계좌 이체 유도 |

> 💡 **핵심 파일:** 단계별로 명명된 파일은 사기 흐름 분석에 특히 유용하다.
> - 대출사기: `[대출사기_1단계]_피해자에게_접근` ~ `[대출사기_5단계]_금전편취_시도`
> - 수사기관사칭: `[정부기관사칭_1단계]` ~ `[정부기관사칭_6단계]_은행_창구_직원의_피싱_예방_확인_회피`

### Step 1-1. 데이터 폴더 구조 확인

```bash
# 대출사기형 파일 수 확인
dir "downloads\fss_audio\대출사기형" | find /c ".mp3"

# 수사기관사칭형 파일 수 확인  
dir "downloads\fss_audio\수사기관사칭형" | find /c ".mp3"
```

### Step 1-2. 단계별 파일 우선 목록 작성 (분석 우선순위)

앵커 질문 설계를 위해 **단계명이 명시된 파일**을 먼저 분석한다:

```
[우선 분석 대상 파일]

대출사기형 단계별:
  ├── [대출사기_1단계]_피해자에게_접근.mp3             → 접근 수법
  ├── [대출사기_1단계]_피해자에게_접근_2.mp3
  ├── [대출사기_2단계]_개인정보_탈취_시도.mp3           → 개인정보 요구 수법
  ├── [대출사기_3단계]_심리적_압박_및_신뢰_형성.mp3     → 긴급성·신뢰 조성
  ├── [대출사기_4단계]_피해자_안심시키기.mp3            → 안심 유도
  └── [대출사기_5단계]_금전편취_시도.mp3               → 선입금·이체 유도

수사기관사칭형 단계별:
  ├── [정부기관사칭_1단계]_피해자에게_접근.mp3          → 기관 사칭 접근
  ├── [정부기관사칭_2단계]_심리적_압박_및_주변_도움_차단.wav
  ├── [정부기관사칭_3단계]_피해자_안심시키기1.wav
  ├── [정부기관사칭_3단계]_피해자_안심시키기2.wav
  ├── [정부기관사칭_4단계]_계좌_현황_파악.wav           → 자산 파악 수법
  ├── [정부기관사칭_5단계]_금전_편취_시도.wav           → 이체·현금 요구
  └── [정부기관사칭_6단계]_은행_창구_직원의_피싱_예방_확인_회피.wav → 제3자 차단
```

### ✅ Phase 1 완료 기준

- [ ] `downloads/fss_audio/대출사기형/` 185개 파일 존재 확인
- [ ] `downloads/fss_audio/수사기관사칭형/` 227개 파일 존재 확인
- [ ] 단계별 파일 우선 분석 목록 확정

---

## Phase 2: STT 배치 처리 및 앵커 질문 구조 설계

> **담당:** 장원재, 김금비 | **핵심 목표:** STT 변환 → 유형별 패턴 분석 → 앵커 질문 5종 구조 확정  
> **스크립트:** `scripts/stt_batch_pipeline.py`

### 전체 흐름

```
[오디오 파일 185+227개]
        ↓
[STT 배치 변환 - faster-whisper]
        ↓
[유형별 텍스트 저장 - stt_output/]
        ↓
[단계별 파일 우선 분석]
        ↓
[대출사기형 패턴 도출] + [수사기관사칭형 패턴 도출]
        ↓
[공통 압박 구조 교차 분석]
        ↓
[앵커 질문 5종 구조 확정]
        ↓
[LLM 시스템 프롬프트 작성]
```

### Step 2-1. STT 배치 파이프라인 실행

> **주의:** 첫 실행 시 Whisper 모델 다운로드로 시간이 소요될 수 있다.

```bash
# 전체 배치 실행 (유형별 하위 폴더 포함)
python scripts/stt_batch_pipeline.py
```

출력 구조:
```
stt_output/
├── 대출사기형/
│   ├── [대출사기_1단계]_피해자에게_접근.txt
│   ├── [대출사기_3단계]_심리적_압박_및_신뢰_형성.txt
│   └── ... (185개 txt)
└── 수사기관사칭형/
    ├── [정부기관사칭_2단계]_심리적_압박_및_주변_도움_차단.txt
    ├── [정부기관사칭_6단계]_은행_창구_직원의_피싱_예방_확인_회피.txt
    └── ... (227개 txt)
```

### Step 2-2. 단계별 파일 STT 결과 품질 확인

```bash
# 단계별 우선 파일 결과 확인
type "stt_output\대출사기형\[대출사기_3단계]_심리적_압박_및_신뢰_형성.txt"
type "stt_output\수사기관사칭형\[정부기관사칭_5단계]_금전_편취_시도.txt"
```

| 점검 항목 | 목표 |
|----------|------|
| 한국어 인식 정확도 | ≥ 90% |
| 핵심 키워드 포함 | "검찰", "이체", "비밀", "안전계좌" 등 포함 여부 |
| 대화 구조 재현 | 사기범 발화 vs 피해자 발화 구분 가능 여부 |

> 정확도 부족 시: `whisper.load_model("medium")` 또는 `"large"`로 변경

### Step 2-3. 유형별 언어 패턴 분석 (인수이계: 장원재 → 민채영)

단계별 STT 텍스트를 읽고 다음 항목을 수기 또는 스크립트로 추출한다.

#### [대출사기형] 핵심 패턴 매핑

| 사기 단계 | 주요 발화 패턴 | 심리적 기제 |
|----------|-------------|------------|
| 1단계: 접근 | "저금리 대환대출", "정부지원자금" | 신뢰/기대 형성 |
| 2단계: 개인정보 탈취 | "신분증 사본", "계좌번호 불러주세요" | 개인정보 요구 |
| 3단계: 심리적 압박 | "편법이지만", "지금만 가능", "실적 때문에 특별 케이스" | 긴급성 + 특혜감 조성 |
| 4단계: 안심시키기 | "나중에 환급됩니다", "저도 책임집니다" | 의심 해소 |
| 5단계: 금전 편취 | "인지세", "공증료", "담당자 계좌로 상환" | 선입금 요구 |
| 은폐 공통 | "은행에서 이유 물으면 ~라고 하세요" | 제3자(은행원) 차단 |

#### [수사기관사칭형] 핵심 패턴 매핑

| 사기 단계 | 주요 발화 패턴 | 심리적 기제 |
|----------|-------------|------------|
| 1단계: 접근 | "서울중앙지검", "수사관", "명의도용 사건" | 권위 + 공포 조성 |
| 2단계: 압박·고립 | "발설 금지", "부모님께도 말하지 말 것", "녹취 중" | 주변 도움 차단 |
| 3단계: 안심시키기 | "피해자임을 증명해드리겠습니다" | 협조 유도 |
| 4단계: 자산 파악 | "현재 이용 중인 금융권 상호", "잔액이 얼마나" | 자산 규모 파악 |
| 5단계: 금전 편취 | "안전계좌", "국가보안계좌", "금감원 직원 인계" | 현금 편취 |
| 6단계: 은행 차단 | "창구 직원이 물으면 ~라고 답하세요" | 제3자(은행원) 차단 |

### Step 2-4. 공통 압박 구조 교차 분석 → 앵커 질문 5종 구조 확정

두 유형의 STT 분석에서 **공통으로 반복되는 핵심 압박 구조**를 앵커 질문의 축으로 삼는다.

```
[공통 패턴 교차 분석]

대출사기형              수사기관사칭형
    │                        │
    ├── [공통] 제3자 차단 ────┤  → 앵커 질문 ④: 은행에서 이유 다르게 말하라?
    ├── [공통] 긴급성 압박 ───┤  → 앵커 질문 ②: 지금 당장 하지 않으면 큰일?
    ├── [공통] 비밀 강요 ─────┤  → 앵커 질문 ③: 주변에 말하지 말라고 했나?
    │                        │
    ├── 선입금 유도 (대출)    └── 이체/현금 요구 (수사기관)
    │       │                          │
    │       └── 앵커 질문 ⑤: 돈을 먼저 보내야 해결이 된다고?
    │
    └── 기관 사칭 (수사기관)
            └── 앵커 질문 ①: 공공기관이 직접 이체/현금을 지시했나?
```

#### 최종 앵커 질문 5종 구조

| # | 앵커 질문 | 탐지 수법 유형 | 핵심 근거 파일 |
|---|---------|-------------|---------------|
| **①** | 경찰, 검찰, 금감원 등 공공기관이 직접 이체나 현금 인계를 지시했나요? | 수사기관사칭형 全 단계 | `[정부기관사칭_5단계]_금전_편취_시도` |
| **②** | 지금 당장 하지 않으면 법적 처벌이나 대출 취소 등 큰 불이익이 생긴다고 했나요? | 양 유형 공통 | `[대출사기_3단계]_심리적_압박`, `[정부기관사칭_2단계]_압박` |
| **③** | 이 통화 내용이나 거래 사실을 가족, 지인, 은행 직원에게 절대 말하지 말라고 했나요? | 양 유형 공통 | `절대_검찰조사_받는_것_발설하지_마세요`, `부모님이_물어보셔도_발설하지_마시고` |
| **④** | 은행 창구 직원이 이유를 물으면 다른 이유를 대라고 미리 알려줬나요? | 양 유형 공통 | `[정부기관사칭_6단계]_은행_창구_직원의_피싱_예방_확인_회피` |
| **⑤** | 대출을 받거나 문제를 해결하려면 먼저 돈을 보내야 한다고 했나요? | 대출사기형 선입금 패턴 | `[대출사기_5단계]_금전편취_시도`, `인지세`, `공증료` 관련 파일 |

> **설계 원칙:** 질문 순서는 공포감을 직접 자극하지 않도록 **중립적 어조**로 구성한다.
> 피싱 피해자는 이미 압박받고 있는 상태이므로, 판단력 회복을 돕는 방향으로 질문한다.

### Step 2-5. LLM 프롬프트 구조 작성

`ai/anchor_prompts.py`에 유형별 판별 기준을 포함한 시스템 프롬프트를 작성한다:

```python
# ai/anchor_prompts.py
SYSTEM_PROMPT = """
당신은 보이스피싱 탐지 전문 AI입니다.
사용자의 이체 상황을 파악하기 위해 5가지 앵커 질문을 순서대로 물어보세요.

[판별 기준]
- 대출사기형: Q②(긴급성) + Q④(은행 차단) + Q⑤(선입금) 중 2개 이상 '예' → 피싱 의심
- 수사기관사칭형: Q①(기관 지시) + Q③(비밀 강요) + Q④(은행 차단) 중 2개 이상 '예' → 피싱 의심
- 어느 유형이든 3개 이상 '예' → 즉시 위험 신호

[질문 어조 원칙]
- 중립적이고 안심시키는 어조 유지
- "혹시 ~한 상황인가요?" 형식으로 질문
- 피해자가 대답하기 편하도록 짧고 명확하게
"""

ANCHOR_QUESTIONS = [
    "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
    "지금 당장 보내지 않으면 법적 처벌이나 대출 취소 같은 큰 불이익이 생긴다고 했나요?",
    "이 거래 사실을 가족이나 은행 직원에게 말하지 말라는 당부를 받으셨나요?",
    "은행 창구에서 직원이 이유를 물으면 다른 이유를 대라고 미리 알려줬나요?",
    "대출을 받거나 문제를 해결하기 위해 먼저 돈을 보내야 한다는 말을 들으셨나요?",
]
```

### Step 2-6. 앵커 질문 검증 (시나리오 테스트)

| 시나리오 | Q① | Q② | Q③ | Q④ | Q⑤ | 기대 판별 |
|---------|----|----|----|----|----|---------|
| 정상 이체 | ✗ | ✗ | ✗ | ✗ | ✗ | 정상 |
| 대출사기형 | ✗ | ✓ | ✓ | ✓ | ✓ | **피싱** |
| 수사기관사칭형 | ✓ | ✓ | ✓ | ✓ | ✗ | **피싱** |
| 혼합형 | ✓ | ✓ | ✓ | ✓ | ✓ | **피싱 (최고위험)** |

### ✅ Phase 2 완료 기준

- [ ] `stt_output/` 에 두 유형 모두 텍스트 변환 완료
- [ ] 한국어 인식 정확도 ≥ 90% (단계별 파일 샘플 검토)
- [ ] 대출사기형 / 수사기관사칭형 핵심 패턴 키워드 목록 완성
- [ ] **앵커 질문 5종 구조 및 어조 최종 확정**
- [ ] `ai/anchor_prompts.py` 초안 작성 완료 (판별 기준 포함)

---

## Phase 3: CDD 위험도 스코어링 엔진

> **담당:** 장원재 | **기능 ID:** F-01  
> **생성 파일:** `ai/cdd_scorer.py`

### 목적

이체 요청이 들어올 때 행동 패턴·수취 계좌 정보 등을 기반으로 위험도 점수(0~100)를 산출한다.

### Step 3-1. 스코어링 로직 구현

`ai/cdd_scorer.py`에 다음 입력 변수 기반 스코어링 로직을 구현한다:

| 입력 변수 | 위험도 가중치 | 비고 |
|----------|------------|------|
| 수취 계좌 블랙리스트 등재 여부 | +50 | 최우선 판별 |
| 처음 이체하는 계좌 여부 | +20 | 신규 수취인 |
| 이체 금액 (100만 원 이상) | +15 | 고액 이체 |
| 야간/새벽 거래 (22:00~06:00) | +10 | 비정상 시간대 |
| 짧은 시간 내 반복 이체 시도 | +20 | 압박 상황 가능성 |

```python
# ai/cdd_scorer.py 구조 예시
def calculate_risk_score(account_info: dict, transaction_info: dict) -> int:
    """
    CDD 기반 위험도 점수 산출 (0~100)
    70 이상 → 고위험 (Anchor-Voice 진입)
    70 미만 → 저위험 (DeepFace 인증)
    """
    score = 0
    # 스코어링 로직 구현
    return min(score, 100)
```

### Step 3-2. 단위 테스트

```bash
python -m pytest tests/test_cdd.py -v
```

| 테스트 케이스 | 기대 출력 |
|-------------|---------|
| 블랙리스트 계좌 이체 | score ≥ 70 (고위험) |
| 정기 이체 (기존 계좌) | score < 30 (저위험) |
| 새벽 100만 원 이체 | score ≥ 70 (고위험) |

### ✅ Phase 3 완료 기준

- [ ] `ai/cdd_scorer.py` 구현 완료
- [ ] 위험/비위험 분류 정확도 확인 (테스트 케이스 통과)

---

## Phase 4: DeepFace 안면 동작 챌린지 인증 모듈

> **담당:** Vision Agent | **기능 ID:** F-02  
> **생성 파일:** `ai/deepface_auth.py`, `ai/action_challenge.py`

### 목적

저위험군 사용자에게 **딥페이크 방지 + 라이브니스 검증** 2단계 안면 챌린지로 빠르고 안전하게 이체를 승인한다.

### 전체 인증 흐름

```
[1단계] DeepFace 실사 검증 (딥페이크 방지)
  → 웹캠 사진 캡처 (st.camera_input)
  → POST /api/auth/face
  → DeepFace.verify(캡처 이미지, registered_face.jpg)
      ├── 불일치 or 딥페이크 의심 → voice_auth fallback
      └── 일치 → [2단계]로 진행

[2단계] LLM 2콤보 동작 챌린지
  → POST /api/auth/face/challenge (챌린지 명령 생성)
  → LLM이 액션 풀에서 2가지 무작위 선택
      액션 풀: [고개_오른쪽, 고개_왼쪽, 고개_위로, 오른쪽_눈깜빡임, 왼쪽_눈깜빡임, 미소]
  → 명령 텍스트를 TTS로 읽어주고 화면에도 표시
      예: "오른쪽으로 고개를 돌렸다가, 오른쪽 눈을 깜빡이세요"

  → 동작 1: 웹캠 사진 촬영 → POST /api/auth/face/action
      MediaPipe Face Mesh → 동작 감지
  → 동작 2: 두 번째 웹캠 사진 촬영 → POST /api/auth/face/action
      MediaPipe Face Mesh → 동작 감지

  ├── 2동작 모두 확인 → 인증 통과
  └── 실패 (2회 이상) → voice_auth fallback
```

### Step 4-1. MediaPipe 설치

```bash
uv pip install mediapipe
```

### Step 4-2. 동작 감지 로직 (`ai/action_challenge.py`)

MediaPipe Face Mesh로 각 동작을 감지하는 방법:

| 동작 | 감지 방법 |
|------|---------|
| 고개 오른쪽/왼쪽 | 얼굴 yaw 각도 (코끝·왼쪽볼·오른쪽볼 landmark 비율) |
| 고개 위로 | 얼굴 pitch 각도 |
| 눈 깜빡임 | Eye Aspect Ratio (EAR 공식): EAR < 0.2 = 깜빡임 |
| 미소 | 입꼬리 landmark 좌표의 y 상승 값 |

```python
# EAR 공식
EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
# EAR이 임계값(0.2) 아래로 떨어지면 눈 깜빡임으로 판정
```

### Step 4-3. LLM 챌린지 명령 생성 (`/api/auth/face/challenge`)

```python
# 액션 풀에서 무작위 2개 조합
ACTION_POOL = [
    {"id": "head_right",     "text": "오른쪽으로 고개를 돌리세요"},
    {"id": "head_left",      "text": "왼쪽으로 고개를 돌리세요"},
    {"id": "head_up",        "text": "위를 올려보세요"},
    {"id": "blink_right",    "text": "오른쪽 눈을 깜빡이세요"},
    {"id": "blink_left",     "text": "왼쪽 눈을 깜빡이세요"},
    {"id": "smile",          "text": "미소를 지으세요"},
]
# 콤보 예: "오른쪽으로 고개를 돌렸다가, 왼쪽 눈을 깜빡이세요"
```

### Step 4-4. 신규 엔드포인트 (router.py 추가)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/auth/face` | 1단계: DeepFace 실사 검증 |
| POST | `/api/auth/face/register` | 기준 얼굴 등록 (최초 1회) |
| GET | `/api/auth/face/challenge` | 2단계: LLM 2콤보 챌린지 명령 생성 |
| POST | `/api/auth/face/action` | 동작 사진 → MediaPipe 감지 결과 반환 |

### Step 4-5. Edge Case 처리

| Edge Case | 처리 방법 |
|----------|----------|
| 조도 부족 | 재시도 안내 후 1회 재촬영 권유 |
| 동작 미인식 | 2회 실패 시 voice_auth fallback |
| 딥페이크 의심 | 즉시 voice_auth fallback |
| 카메라 거부 | voice_auth로 자동 전환 |

### ✅ Phase 4 완료 기준

- [ ] DeepFace.verify() 실사 검증 성공 (등록 이미지와 비교)
- [ ] LLM이 2콤보 동작 명령 생성
- [ ] MediaPipe로 동작 2개 감지 확인
- [ ] fallback 로직 동작 확인

---


## Phase 5: LLM 앵커 보이스 판별 엔진

> **담당:** 민채영 | **기능 ID:** F-03, F-04, F-05, F-06  
> **생성 파일:** `ai/anchor_prompts.py`, `ai/whisper_stt.py`, `ai/gtts_tts.py`, `ai/llm_engine.py`

### Step 5-1. STT 모듈 구현 (Whisper)

```bash
# Whisper 설치 확인
python -c "import whisper; print('Whisper OK')"
```

`ai/whisper_stt.py`:

```python
# 마이크 실시간 입력 또는 오디오 파일 → 텍스트 변환
import whisper

def transcribe_audio(audio_path: str = None, use_mic: bool = False) -> str:
    """음성 → 텍스트 변환 (한국어 우선)"""
    model = whisper.load_model("base")
    # 변환 로직
    ...
```

### Step 5-2. TTS 모듈 구현 (gTTS)

`ai/gtts_tts.py`:

```python
from gtts import gTTS
import playsound

def speak(text: str, lang: str = "ko"):
    """텍스트 → 한국어 음성 출력"""
    tts = gTTS(text=text, lang=lang)
    tts.save("response.mp3")
    playsound.playsound("response.mp3")
```

### Step 5-3. 앵커 프롬프트 구성

`ai/anchor_prompts.py`에 5가지 앵커 질문과 LLM 시스템 프롬프트를 정의한다:

```python
SYSTEM_PROMPT = """
당신은 보이스피싱 탐지 전문 AI입니다.
사용자의 이체 상황을 분석하여 피싱 여부를 판단합니다.
다음 5가지 앵커 질문을 순서대로 물어보고, 응답을 종합하여 위험도를 판단하세요.
피싱이 의심되면 즉시 '위험' 신호를 반환하세요.
"""

ANCHOR_QUESTIONS = [
    "공공기관(경찰, 검찰, 금감원)이 직접 이체를 지시했나요?",
    "지금 당장 보내지 않으면 큰일 난다고 했나요?",
    "상대방이 화면 캡처나 공유를 요청했나요?",
    "아무에게도 말하지 말라고 했나요?",
    "오늘 처음 연락이 온 사람에게 돈을 보내는 건가요?",
]
```

### Step 5-4. LLM 판별 엔진 구현

`ai/llm_engine.py`:

```python
import google.generativeai as genai

def analyze_phishing_risk(conversation_log: list) -> dict:
    """
    앵커 질문 응답 기반 피싱 위험도 분석
    Returns: {"is_phishing": bool, "confidence": float, "reason": str}
    """
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-pro")
    # 분석 로직
    ...
```

### Step 5-5. 음성 대화 플로우 테스트

```bash
# 단독 대화 에이전트 테스트
python ai/llm_engine.py --test-mode
```

**테스트 시나리오:**

| 시나리오 | 앵커 질문 응답 패턴 | 기대 결과 |
|---------|-----------------|---------|
| 정상 이체 | 모두 "아니요" | is_phishing: False |
| 기관사칭형 | Q1, Q2, Q4 "예" | is_phishing: True |
| 텔레그램 알바형 | Q5 "예" + Q3 "예" | is_phishing: True |

### ✅ Phase 5 완료 기준

- [ ] STT: 음성 → 텍스트 변환 성공, 한국어 인식 정확도 ≥ 90%
- [ ] TTS: 텍스트 → 한국어 음성 출력 정상 작동
- [ ] LLM: 피싱 시나리오 판별 정확도 ≥ 85%

---

## Phase 6: FastAPI 백엔드 서버

> **담당:** 민채영 | **기능 ID:** F-08, F-09  
> **생성 파일:** `backend/main.py`, `backend/router.py`

### Step 6-1. FastAPI 서버 구현

```bash
# FastAPI 설치 확인
python -c "import fastapi; print('FastAPI OK')"
```

**주요 엔드포인트:**

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/health` | 서버 상태 확인 |
| POST | `/api/transfer/risk-check` | CDD 위험도 스코어링 |
| POST | `/api/auth/face` | DeepFace 안면 인식 |
| POST | `/api/auth/voice/start` | 앵커 보이스 대화 시작 |
| POST | `/api/auth/voice/answer` | 앵커 질문 응답 처리 |
| POST | `/api/sos/trigger` | 스텔스 SOS 발동 |

### Step 6-2. 서버 실행

```bash
# 개발 서버 실행
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 또는
python -m uvicorn backend.main:app --reload
```

### Step 6-3. 서버 상태 확인

```bash
# 브라우저 또는 curl로 확인
curl http://localhost:8000/health
# 기대 응답: {"status": "ok", "version": "0.1.0"}

# API 문서 확인 (자동 생성)
# http://localhost:8000/docs
```

### Step 6-4. 동적 라우팅 로직 검증

```bash
# 위험도 스코어링 API 테스트
curl -X POST http://localhost:8000/api/transfer/risk-check \
  -H "Content-Type: application/json" \
  -d '{"account": "1234-5678", "amount": 1500000, "hour": 2}'
```

### ✅ Phase 6 완료 기준

- [ ] `/health` 엔드포인트 정상 응답
- [ ] 위험도 분기 라우팅 로직 동작 확인
- [ ] API 문서 (`/docs`) 접근 가능

---

## Phase 7: Streamlit 프론트엔드 UI

> **담당:** 김금비 | **기능 ID:** F-07, F-10  
> **생성 파일:** `frontend/app.py`, `frontend/components/`

### Step 7-1. Streamlit 설치 확인

```bash
python -c "import streamlit; print('Streamlit OK')"
```

### Step 7-2. 메인 앱 실행

```bash
streamlit run frontend/app.py
# 브라우저에서 http://localhost:8501 자동 오픈
```

### Step 7-3. UI 구성 요소

| 화면 | 설명 | 파일 |
|------|------|------|
| 이체 입력 화면 | 계좌번호, 금액, 수취인 입력 | `frontend/app.py` |
| 안면 인식 화면 | 웹캠 스트림 + 인식 결과 | `frontend/components/face_ui.py` |
| 앵커 보이스 대화 화면 | 음성 입력 + 질문 응답 흐름 | `frontend/components/voice_ui.py` |
| **스텔스 SOS 위장 화면** | "이체 완료" 위장 UI (실제 차단) | `frontend/components/stealth_ui.py` |
| 이체 완료 화면 | 정상 승인 후 완료 화면 | `frontend/app.py` |

### Step 7-4. 스텔스 SOS UI 핵심 구현 포인트

```python
# frontend/components/stealth_ui.py
def render_stealth_complete_screen(amount: int, account: str):
    """
    실제로는 이체가 차단되었지만,
    가해자의 눈에는 '이체 완료'처럼 보이는 위장 UI 렌더링
    """
    st.success(f"✅ {amount:,}원이 {account}로 이체되었습니다.")
    st.info("이체 완료 시각: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # 백그라운드: 실제 차단 + 신고 처리 (비동기)
```

### Step 7-5. 상태 관리 흐름

```
[이체 입력] → [위험도 판별] → [저위험: 안면 인식] → [이체 완료]
                           ↘ [고위험: 앵커 보이스 대화] → [정상: 이체 완료]
                                                       ↘ [피싱: 스텔스 SOS UI]
```

### ✅ Phase 7 완료 기준

- [ ] Streamlit 앱 정상 실행 (`http://localhost:8501`)
- [ ] 이체 흐름 전체 화면 전환 정상 동작
- [ ] 스텔스 SOS 위장 UI 렌더링 확인

---

## Phase 8: 스텔스 SOS 모듈

> **담당:** 민채영, 김금비 | **기능 ID:** F-07, F-08  
> **생성 파일:** `backend/stealth_sos.py`

### 목적

피싱 탐지 시 가해자의 감시 하에서도 안전하게 차단하기 위한 비밀 개입 메커니즘.

### Step 8-1. 스텔스 SOS 로직 구현

```python
# backend/stealth_sos.py
async def trigger_stealth_sos(transfer_info: dict, phishing_evidence: dict):
    """
    1. 이체 실제 차단
    2. 프론트에는 '이체 완료' 위장 UI 신호 전송
    3. 백그라운드: 금융기관 + 경찰 실시간 알림 (구현 범위 내)
    """
    # Step 1: 이체 차단
    await block_transfer(transfer_info)
    
    # Step 2: 위장 UI 렌더링 신호
    return {"ui_mode": "stealth_complete", "blocked": True}
    
    # Step 3: 알림 (목업 or 로그 출력)
    logger.warning(f"[STEALTH SOS] 피싱 의심 차단: {transfer_info}")
```

### Step 8-2. 스텔스 SOS 시나리오 테스트

```
시나리오: 사용자가 가해자의 지시로 이체 시도
    → CDD 스코어링: 고위험 (score ≥ 70)
    → 앵커 보이스: 3개 이상 긍정 응답
    → LLM 판단: is_phishing = True
    → 스텔스 SOS 발동
    → 화면: "이체 완료" 우장 UI ✅
    → 실제: 이체 차단 + 로그 기록
```

### ✅ Phase 8 완료 기준

- [ ] 이체 차단 로직 작동 확인
- [ ] 위장 UI 정상 렌더링 확인
- [ ] 차단 이벤트 로그 기록 확인

---

## Phase 9: E2E 통합 테스트

> **담당:** 전체 | **최종 목표:** Functional Integrity 증명

### Step 9-1. 백엔드 + 프론트엔드 동시 실행

```bash
# 터미널 1: FastAPI 백엔드
uvicorn backend.main:app --reload --port 8000

# 터미널 2: Streamlit 프론트엔드
streamlit run frontend/app.py
```

### Step 9-2. 핵심 시나리오 체크리스트

#### 🟢 시나리오 A — 정상 이체 (저위험)

```
1. 이체 입력 (기존 계좌, 소액, 주간)
2. CDD 스코어 < 30 → 저위험 판별
3. DeepFace 안면 인식 화면 진입
4. 안면 인식 성공 → 이체 승인
5. 이체 완료 화면 출력
```
- [ ] 전체 플로우 3초 이내 완료
- [ ] 이체 승인 화면 정상 출력

#### 🔴 시나리오 B — 보이스피싱 의심 (고위험)

```
1. 이체 입력 (신규 계좌, 고액, 야간)
2. CDD 스코어 ≥ 70 → 고위험 판별
3. Anchor-Voice 음성 대화 화면 진입
4. 앵커 질문 5가지 순서대로 진행
5. 3개 이상 긍정 응답
6. LLM 판단: is_phishing = True
7. 스텔스 SOS 발동 → 위장 이체 완료 UI 출력
8. 실제 이체 차단 + 로그 기록
```
- [ ] 고위험 라우팅 정확 동작
- [ ] 5가지 앵커 질문 모두 진행
- [ ] 스텔스 SOS 위장 UI 정상 렌더링
- [ ] 이체 차단 로그 확인

#### 🟡 시나리오 C — 안면 인식 실패 → Fallback

```
1. 이체 입력 (저위험)
2. DeepFace 안면 인식 실패 2회
3. 자동으로 Anchor-Voice 음성 인증으로 전환
4. 정상 대화 후 이체 승인
```
- [ ] Fallback 전환 정상 동작

### Step 9-3. 성능 측정

```bash
# 응답 시간 측정
python tests/test_latency.py
```

| 측정 항목 | 목표값 |
|----------|-------|
| CDD 스코어링 응답 | ≤ 500ms |
| DeepFace 인식 | ≤ 1,000ms |
| STT 변환 (5초 음성) | ≤ 2,000ms |
| LLM 판별 응답 | ≤ 3,000ms |
| 전체 E2E (고위험) | ≤ 30초 (대화 포함) |

### Step 9-4. 최종 버그 수정 및 발표 준비

- [ ] 시나리오 A, B, C 모두 통과
- [ ] 성능 목표값 충족
- [ ] 데모 영상 녹화 (시나리오 B 위주)
- [ ] 발표 자료 내 데모 흐름과 동기화

---

## 트러블슈팅 (Troubleshooting)

| 문제 | 원인 | 해결 방법 |
|------|------|---------|
| `uv sync` 실패 | CUDA 버전 불일치 | `pyproject.toml`의 pytorch index URL 확인 |
| DeepFace import 오류 | TensorFlow 미설치 | `pip install tensorflow` 추가 |
| Whisper 모델 다운로드 실패 | 네트워크 이슈 | VPN 사용 또는 모델 수동 다운로드 |
| Gemini API 429 오류 | Rate Limit 초과 | `.env`에서 GPT 백업 API로 전환 |
| Streamlit 포트 충돌 | 8501 포트 사용 중 | `streamlit run app.py --server.port 8502` |
| STT 한국어 인식 불량 | 모델 크기 부족 | `whisper.load_model("medium")` 으로 변경 |

---

## 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 서비스 아이디어 | `service_idea.md` | 기획 배경 및 핵심 컨셉 |
| 서비스 개발 계획서 | `service_plan.md` | 기능 명세, 아키텍처, KPI |
| FSS 크롤러 가이드 | `README_FSS_CRAWLER.md` | 금감원 오디오 크롤러 사용법 |
| 환경 변수 예시 | `.env.example` | API 키 설정 가이드 |
