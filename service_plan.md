# Anchor-Voice 서비스 개발 계획서 (Service Plan)

> **20대를 위한 지능형 모바일 뱅킹 에이전트**  
> CDD 기반 안면 인식과 대화형 LLM으로 편의성과 보안을 모두 잡다.

**팀:** 4조 (장원재, 김금비, 민채영)  
**문서 작성일:** 2026-04-02  
**기반 문서:** `service_idea.md`

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [문제 정의 및 타겟 분석](#2-문제-정의-및-타겟-분석)
3. [솔루션 설계](#3-솔루션-설계)
4. [기능 명세](#4-기능-명세)
5. [시스템 아키텍처](#5-시스템-아키텍처)
6. [기술 스택 상세](#6-기술-스택-상세)
7. [개발 로드맵](#7-개발-로드맵)
8. [팀 역할 및 책임](#8-팀-역할-및-책임)
9. [리스크 및 대응 방안](#9-리스크-및-대응-방안)
10. [성공 지표 (KPI)](#10-성공-지표-kpi)

---

## 1. 프로젝트 개요

### 1.1 서비스 정의

**Anchor-Voice**는 20대 사회초년생을 주요 타겟으로, 모바일 뱅킹 이체 과정에서 보이스피싱 위험을 실시간으로 감지·차단하는 **AI 기반 대화형 보안 에이전트**이다.

### 1.2 핵심 슬로건

> *"사용자가 의심 상황에 있을 때, 대신 판단해주는 AI"*

### 1.3 핵심 가치

| # | 가치 | 설명 |
|---|------|------|
| 1 | **사전 예방** | 사후 대응이 아닌 피해 발생 전 차단 |
| 2 | **상황 기반 판단** | 단순 정보 제공이 아닌 맥락(Context) 분석 |
| 3 | **대화형 인터랙션** | 문답형 구조로 판단 정확도 향상 |
| 4 | **즉각 개입** | 스스로 판단하기 어려운 상황에 AI가 자동 개입 |

---

## 2. 문제 정의 및 타겟 분석

### 2.1 시장 현황

보이스피싱은 더 이상 고령층만의 문제가 아니다. 2025년 8월 기준 연령대별 피해 비율을 보면 **20대 이하(25%)와 60대(25%)가 공동 1위**로 나타나 양극화 구조가 형성되어 있다.

| 연도 | 20대 이하 피해 비율 |
|------|-------------------|
| 2022 | 31% |
| 2023 | 47% |
| 2024 | 26% |
| 2025년 8월 | 25% |

> 출처: MBC 기사 (2025년 보도), 경찰청 자료, 금융감독원 (2024.3.8)

### 2.2 타겟: 왜 20대인가?

- 20대 피해자의 **85.2%**가 정부·기관사칭형 수법에 당함 (금융감독원 2024)
- **원인 1 — 모바일 친숙도:** 익숙한 모바일 환경이 오히려 위험 노출을 높임
- **원인 2 — 경험 부족:** 사회초년생으로서 위협적 상황에 대한 대응 경험 없음

### 2.3 기존 방어 수단의 한계

| 기존 방어 수단 | 문제점 |
|--------------|--------|
| 이체 전 동의 체크박스 | 이탈률 0%, 방어율 사실상 0% — 형식에 그침 |
| 경고 문구 팝업 | 사용자가 무시하거나 습관적으로 넘김 |
| 사후 신고 체계 | 범죄 발생 후 대응 → 피해 회복 불가에 가까움 |

---

## 3. 솔루션 설계

### 3.1 접근 방식: CDD 기반 동적 라우팅

UX 편의성과 보안을 동시에 달성하기 위해 **고객확인제도(CDD)** 에 기반한 위험도 점수를 산출하고, 점수에 따라 인증 방식을 동적으로 분기한다.

```
이체 시도
    ↓
[위험도 산출 엔진]
행동 패턴 + 수취 계좌 블랙리스트 + 거래 시간/금액 등 종합 스코어링
    ↓
┌──────────────────────────────────────────────┐
│ 저위험군 (Low Risk)   │ 고위험군 (High Risk)   │
│                      │                       │
│ ✅ 안면 동작 챌린지   │ 🚨 Anchor-Voice        │
│  (DeepFace+MediaPipe)│    음성 대화 인증 강제  │
│  → UX 극대화         │    → 보안 극대화        │
└──────────────────────────────────────────────┘
```

#### 3.1-0 얼굴 등록 (별도 메뉴/탭에서 진행)

앱 최초 실행 시 강제하는 것이 아니라, 사용자가 '안면 인증'의 편의성을 위해 **별도의 등록 메뉴나 탭**에서 미리 본인의 얼굴 이미지를 등록한다. 등록된 이미지는 `registered_face.jpg`로 로컬 스토리지에 저장된다.

#### 3.1-A 저위험군: 안면 동작 챌린지 또는 대체 인증 (2단계)

사용자가 이체를 시도할 때 위험도가 낮으면 인증 과정을 거친다.
이 때, **얼굴이 등록된 사용자**와 **미등록 사용자**를 분기한다:

**미등록 사용자 (대체 인증 진입)**
- 얼굴(기준 이미지)이 등록되어 있지 않으면 카메라를 켜지 않고 기존 뱅킹의 익숙한 방식인 **'비밀번호 입력'** 혹은 **'공인인증서 인증(데모용 UI)'** 화면으로 대체 진행된다.

**등록 사용자 (안면 챌린지 진입)**
단순 사진 비교가 아닌 **딥페이크 방지 + 라이브니스 검증** 구조:

**1단계 — DeepFace 실사 검증**
```
웹캠 사진(st.camera_input) → POST /api/auth/face
DeepFace.verify(캡처 이미지, registered_face.jpg)
    ├── 일치 → 2단계 진입
    └── 불일치 / 딥페이크 의심 → 음성 인증(voice_auth)으로 fallback
```

**2단계 — LLM 동작 챌린지 (2콤보)**
```
LLM이 아래 액션 풀에서 2가지를 무작위 조합하여 명령 생성:
  액션 풀: [고개 오른쪽, 고개 왼쪽, 고개 위로, 오른쪽 눈 깜빡임, 왼쪽 눈 깜빡임, 미소]
  예시 명령: "오른쪽으로 고개를 돌렸다가, 오른쪽 눈을 깜빡이세요"

명령 텍스트를 TTS로 읽어주고 화면에도 표시
    ↓
사용자가 행동 후 웹캠 사진 촬영 (각 동작 1장씩)
    ↓
MediaPipe Face Mesh → 동작 감지:
  - 고개 방향: 얼굴 yaw 각도 분석
  - 눈 깜빡임: Eye Aspect Ratio (EAR) 임계값
  - 미소: 입꼬리 좌표 분석
    ↓
동작 2개 모두 확인 → 인증 통과
동작 미확인 또는 2회 실패 → voice_auth fallback
```

### 3.2 고위험군 대응: Anchor-Voice 음성 대화 인증

고위험으로 분류된 사용자는 AI와의 **실제 음성 대화 인증**을 필수로 거친다.

- **TTS(gTTS)** 로 질문을 시연 PC 스피커로 읽어줌 (화면에도 텍스트 표시)
- **시연 PC 마이크** 로 사용자가 음성으로 대답
- **STT(Whisper)** 로 발화 텍스트 변환 → 화면에 표시
- **LLM(Gemini/GPT)** 이 전체 발화 내용(텍스트)을 분석하여 피싱 여부 판별
- 버튼 클릭(예/아니요) 방식 **완전 제거** — 실제 발화 의미를 분석

5가지 핵심 앵커 질문:
1. *"공공기관(경찰, 검찰, 금감원)이 직접 이체를 지시했나요?"*
2. *"지금 당장 보내지 않으면 큰일 난다고 했나요?"*
3. *"상대방이 화면 캡처나 공유를 요청했나요?"*
4. *"아무에게도 말하지 말라고 했나요?"*
5. *"오늘 처음 연락이 온 사람에게 돈을 보내는 건가요?"*



### 3.3 스텔스 SOS — 위장 이체 완료 UI

피해자가 가해자의 감시 하에 있는 상황을 고려한 **비밀 차단 메커니즘**:

- 이체가 **실제로는 차단**되었지만, 화면에는 **"이체 완료" 위장 UI** 렌더링
- 가해자의 확인 요구에 위장 화면으로 대응 가능
- 백그라운드에서 경찰·금융기관에 실시간 알림 및 차단 처리

---

## 4. 기능 명세

### 4.1 핵심 기능 목록

| 기능 ID | 기능명 | 우선순위 | 담당 |
|---------|--------|---------|------|
| F-01 | CDD 기반 위험도 스코어링 | 🔴 Must | 장원재 |
| F-02 | DeepFace 안면 인식 인증 (저위험) | 🔴 Must | 장원재 |
| F-03 | Anchor-Voice 음성 대화 인증 (고위험) | 🔴 Must | 민채영, 김금비 |
| F-04 | STT (Whisper) 음성→텍스트 변환 | 🔴 Must | 김금비 |
| F-05 | LLM 기반 피싱 패턴 판별 엔진 | 🔴 Must | 민채영 |
| F-06 | TTS (gTTS) 텍스트→음성 안내 | 🔴 Must | 김금비 |
| F-07 | 스텔스 SOS 위장 UI | 🟡 Should | 김금비 |
| F-08 | 실시간 차단 및 경보 알림 | 🟡 Should | 민채영 |
| F-09 | 동적 라우팅 FastAPI 서버 | 🔴 Must | 민채영 |
| F-10 | Streamlit 프론트엔드 상태 관리 | 🔴 Must | 김금비 |

### 4.2 5가지 앵커 질문 (Anchor Questions)

사기 패턴 역엔지니어링을 통해 도출한 핵심 판별 질문:

1. **기관 사칭 탐지** — "공공기관(경찰, 검찰, 금감원)이 직접 이체를 지시했나요?"
2. **긴급성 압박 탐지** — "지금 당장 보내지 않으면 큰일 난다고 했나요?"
3. **화면 감시 탐지** — "상대방이 화면 캡처나 공유를 요청했나요?"
4. **비밀 유지 강요 탐지** — "아무에게도 말하지 말라고 했나요?"
5. **신원 불명 탐지** — "오늘 처음 연락이 온 사람에게 돈을 보내는 건가요?"

---

## 5. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    사용자 (모바일 앱)                      │
│               Streamlit Frontend UI                      │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP Request
                        ↓
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend Server                  │
│                                                         │
│  ┌─────────────────┐    ┌──────────────────────────┐    │
│  │  CDD 위험도      │    │   동적 라우팅 컨트롤러     │    │
│  │  스코어링 엔진   │───▶│  (저위험/고위험 분기)     │    │
│  └─────────────────┘    └──────────────────────────┘    │
│           │                         │                   │
│           ↓                         ↓                   │
│  ┌─────────────────┐    ┌──────────────────────────┐    │
│  │  DeepFace       │    │  Anchor-Voice LLM 엔진    │    │
│  │  안면 인식 모듈  │    │  (Gemini / GPT)          │    │
│  └─────────────────┘    └──────────────────────────┘    │
│                                     │                   │
│                         ┌───────────┴───────────┐       │
│                         ↓                       ↓       │
│                  ┌────────────┐        ┌──────────────┐ │
│                  │ Whisper    │        │ gTTS         │ │
│                  │ STT 모듈   │        │ TTS 모듈     │ │
│                  └────────────┘        └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                        │
                        ↓ 고위험 차단 시
              ┌─────────────────────┐
              │   스텔스 SOS        │
              │   위장 이체 완료 UI  │
              │   + 실시간 알림     │
              └─────────────────────┘
```

### 5.1 데이터 흐름 상세

```
① 사용자 이체 시도
    → 수취 계좌 번호, 금액, 시간, 행동 패턴 수집
        ↓
② CDD 위험도 스코어링
    → 블랙리스트 DB 조회 + 행동 이상치 탐지 → 위험 점수 산출
        ↓
③ 동적 라우팅 분기
    ├── 저위험: DeepFace 안면 인식 → 즉시 이체 승인
    └── 고위험: Anchor-Voice 대화 인증 진입
        ↓
④ 음성 대화 인증 (고위험 케이스)
    → 마이크 음성 입력 → Whisper STT → LLM 피싱 판별 → gTTS 안내
        ↓
⑤ 결과 처리
    ├── 정상: 이체 승인
    └── 피싱 의심: 스텔스 SOS 위장 UI + 실시간 차단 + 알림
```

---

## 6. 기술 스택 상세

### 6.1 레이어별 기술

| 레이어 | 기술 | 역할 | 비고 |
|--------|------|------|------|
| **Frontend** | Streamlit | 동적 UI, 상태 관리 | Python 기반 |
| **Backend** | FastAPI | REST API, 비동기 라우팅 | uvicorn 서버 |
| **Vision** | DeepFace | 실시간 안면 인식 인증 | OpenCV 연동 |
| **Audio (Input)** | OpenAI Whisper STT | 음성→텍스트 변환 | 다국어 지원 |
| **Audio (Output)** | gTTS | 텍스트→음성 안내 | 한국어 최적화 |
| **LLM / Brain** | Google Gemini | 피싱 패턴 분석·판별 | Gemini API |
| **LLM / Brain** | OpenAI GPT | 피싱 패턴 분석 (백업) | GPT API |

### 6.2 사기 패턴 학습 데이터 구축 프로세스

#### 보유 데이터 현황

실제 보이스피싱범과 피해자의 대화 오디오 파일이 유형별로 분류되어 있다.

| 유형 | 경로 | 파일 수 | 주요 수법 |
|------|------|--------|----------|
| **대출사기형** | `downloads/fss_audio/대출사기형/` | **185개** | 저금리 대환대출 미끼, 선입금 유도, 대포통장 모집, 인출책 모집 |
| **수사기관사칭형** | `downloads/fss_audio/수사기관사칭형/` | **227개** | 검찰·경찰·금감원 사칭, 명의도용 협박, 계좌 동결 위협, 안전계좌 이체 유도 |

> 특히 `[대출사기_1~5단계]`, `[정부기관사칭_1~6단계]` 파일은 사기 진행 단계별로 구분되어 있어 수법 흐름 분석에 매우 유용하다.

#### 데이터 처리 파이프라인

```
1. 유형 분류 (완료)
   downloads/fss_audio/
   ├── 대출사기형/     (185개 오디오)
   └── 수사기관사칭형/ (227개 오디오)
        ↓
2. STT 배치 처리 (scripts/stt_batch_pipeline.py)
   faster-whisper 기반 한국어 음성 → 텍스트 변환
   출력: stt_output/ (유형별 하위 폴더 생성)
        ↓
3. 유형별 패턴 분석
   대출사기형  → 선입금 유도 / 심리적 신뢰 형성 패턴
   수사기관사칭형 → 공포 조성 / 비밀 유지 강요 / 자산 이동 유도 패턴
        ↓
4. 공통 언어 패턴 추출
   압박 표현, 권위 표현, 긴급성 표현, 비밀 강요 표현 분류
        ↓
5. 앵커 질문 구조 설계
   수법 유형 × 심리 압박 단계 교차 분석 → 질문 구조 확정
```

#### 수법 유형별 핵심 언어 패턴 (STT 분석 기반)

**[대출사기형] 주요 패턴**

| 단계 | 패턴 키워드 | 사기 의도 |
|------|-----------|----------|
| 접근 | "저금리", "대환대출", "정부지원" | 신뢰 형성 |
| 압박 | "편법이지만", "특별 케이스", "지금만 가능" | 긴급성 조성 |
| 선입금 | "인지세", "공증료", "보증보험료" | 금전 편취 |
| 은폐 | "은행직원이 이유 물으면 ~라고 하세요" | 제3자 차단 |
| 도주 | "담당자 오늘 퇴사함", "환급 일주일 소요" | 피해 지연 |

**[수사기관사칭형] 주요 패턴**

| 단계 | 패턴 키워드 | 사기 의도 |
|------|-----------|----------|
| 접근 | "서울중앙지검", "수사관", "명의도용" | 권위 가장 |
| 공포 | "피의자 신분", "계좌 동결", "소환장" | 심리적 공포 조성 |
| 고립 | "발설 금지", "부모님께도 말하지 말 것" | 주변 도움 차단 |
| 자산이동 | "안전계좌", "국가보안계좌", "금감원 직원 인계" | 현금 편취 |
| 검증 회피 | "은행 창구에서 이유 물으면 ~라고 하세요" | 제3자 개입 차단 |

#### 앵커 질문 도출 근거

두 유형의 STT 분석 결과에서 **공통으로 나타나는 핵심 패턴** 5가지를 앵커 질문으로 설계한다.

| 앵커 질문 | 탐지 대상 수법 | 근거 파일 예시 |
|----------|--------------|---------------|
| ① 공공기관이 직접 이체/현금 인계를 지시했나요? | 수사기관사칭형 全 단계 | `[정부기관사칭_5단계]_금전편취_시도` |
| ② 지금 당장 하지 않으면 큰일 난다고 했나요? | 양 유형 공통 (긴급성 압박) | `[대출사기_3단계]_심리적_압박_및_신뢰_형성` |
| ③ 이 내용을 주변에 말하지 말라고 했나요? | 양 유형 공통 (비밀 강요) | `절대_검찰조사_받는_것_발설하지_마세요` |
| ④ 은행 창구에서 이유를 다르게 말하라고 했나요? | 양 유형 공통 (제3자 차단) | `[정부기관사칭_6단계]_은행_창구_직원의_피싱_예방_확인_회피` |
| ⑤ 돈을 먼저 보내야 대출/문제 해결이 된다고 했나요? | 대출사기형 선입금 패턴 | `[대출사기_5단계]_금전편취_시도` |

---

## 7. 개발 로드맵

### 7.1 스프린트 계획

#### ⚡ Week 1 — 파이프라인 구축 (End-to-End 데이터 흐름 완성)

| 일차 | 작업 항목 | 담당 | 완료 기준 |
|------|----------|------|---------|
| Day 1~2 | 프로젝트 환경 세팅, 패키지 설치, 디렉토리 구조 확정 | 전체 | 로컬 실행 확인 |
| Day 2~3 | FastAPI 서버 기본 라우팅 구성 (F-09) | 민채영 | `/health` 엔드포인트 응답 |
| Day 2~3 | DeepFace 안면 인식 모듈 PoC (F-02) | 장원재 | 웹캠 인식 성공 |
| Day 3~4 | Whisper STT + gTTS 연동 (F-04, F-06) | 김금비 | 음성 입력→텍스트→음성 출력 |
| Day 4~5 | Gemini LLM 연동 및 기본 피싱 판별 프롬프트 (F-05) | 민채영 | 테스트 입력 판별 성공 |
| Day 5~7 | Streamlit 기본 UI 및 대화 인터페이스 (F-10) | 김금비 | 화면 렌더링 확인 |
| Day 6~7 | 기본 CDD 스코어링 로직 구현 (F-01) | 장원재 | 위험/비위험 분류 출력 |
| Day 7 | **E2E 통합 테스트** | 전체 | 이체 시도 → 판별 → 결과까지 흐름 작동 |

#### 🔧 Week 2 — 모델 고도화 및 Edge Case 방어

| 일차 | 작업 항목 | 담당 | 완료 기준 |
|------|----------|------|---------|
| Day 8~9 | 앵커 질문 5종 프롬프트 고도화 | 민채영 | 피싱 시나리오 테스트 통과 |
| Day 8~9 | DeepFace 정확도 향상 (조도/각도 Edge Case) | 장원재 | 시나리오별 인식률 측정 |
| Day 9~10 | 스텔스 SOS 위장 UI 구현 (F-07) | 김금비 | 위장 화면 렌더링 성공 |
| Day 10~11 | 실시간 차단 및 알림 로직 (F-08) | 민채영 | 차단 이벤트 로그 확인 |
| Day 11~12 | 동적 라우팅 정합성 검증 (F-03) | 전체 | 저위험/고위험 분기 정확도 확인 |
| Day 12~13 | UI/UX 개선 및 반응 속도 최적화 | 김금비 | 응답 지연 3초 이내 |
| Day 13~14 | **최종 시나리오 테스트 & 버그 수정** | 전체 | 모든 핵심 시나리오 통과 |
| Day 14 | **발표 자료 준비 및 데모 영상 녹화** | 전체 | 시연 가능 상태 |

### 7.2 마일스톤 요약

```
[Week 1 완료]          [Week 2 완료]          [최종 목표]
    ↓                      ↓                      ↓
E2E 파이프라인        고도화 & 엣지케이스     Functional Integrity
  정상 작동           방어 로직 강화         논리적·기능적 무결성
```

---

## 8. AI 에이전트 구성 (Agent Configuration)

> 서비스 개발은 **6개의 AI 코딩 에이전트**가 각자의 책임 파일과 컨텍스트를 가지고 병렬로 수행한다.  
> 각 에이전트는 독립적으로 코드를 작성하며, 인터페이스 계약을 통해 서로 연동된다.

---

### 🛠️ Agent 1: DevOps Agent

**역할:** 프로젝트 실행 환경 구성 및 공통 인프라 셋업

**호출 시점:** 개발 시작 전 최우선 실행 (모든 에이전트의 선행 조건)

**읽어야 할 컨텍스트:**
- `pyproject.toml` — 현재 의존성 확인
- `.env.example` — 환경 변수 구조 파악
- `service_plan.md` § 6.1 기술 스택

**작성/수정할 파일:**

| 파일 | 작업 내용 |
|------|---------|
| `requirements.txt` | fastapi, streamlit, deepface, whisper, gTTS, google-generativeai 버전 정합 |
| `.env.example` | GEMINI_API_KEY, OPENAI_API_KEY, RISK_THRESHOLD_HIGH/LOW 항목 갱신 |
| `README.md` | 환경 세팅 → 실행 → 테스트 순서 가이드 작성 |
| `backend/__init__.py` | 패키지 초기화 |
| `ai/__init__.py` | 패키지 초기화 |
| `frontend/__init__.py` | 패키지 초기화 |
| `tests/__init__.py` | 패키지 초기화 |

**에이전트 지시 프롬프트 요약:**
```
- pyproject.toml과 service_plan.md §6.1을 읽고 실제 필요한 패키지를 requirements.txt에 정리하라.
- backend/, ai/, frontend/, tests/ 디렉토리와 __init__.py를 생성하라.
- README.md에 uv sync 또는 pip install 후 서버 실행까지의 절차를 작성하라.
- .env.example에 필요한 모든 환경 변수 항목과 설명 주석을 추가하라.
```

---

### 👁️ Agent 2: Vision Agent

**역할:** CDD 위험도 스코어링 엔진 + DeepFace 안면 인식 모듈 개발

**호출 시점:** DevOps Agent 완료 후, Backend Agent와 병렬 실행

**읽어야 할 컨텍스트:**
- `service_plan.md` § 3.1 CDD 동적 라우팅, § 6.1 기술 스택
- `service_plan.md` § 8.3 인터페이스 합의 항목 (위험도 점수 스키마)
- `downloads/fss_audio/` 폴더 구조 파악 (참조용)

**작성할 파일:**

| 파일 | 작업 내용 |
|------|---------|
| `ai/cdd_scorer.py` | `calculate_risk_score(account_info, transaction_info) -> int` 구현 |
| `ai/deepface_auth.py` | `verify_face(registered_image_path) -> dict` 구현, fallback 로직 포함 |
| `tests/test_vision.py` | 위험/비위험/Edge Case 단위 테스트 3종 |

**에이전트 지시 프롬프트 요약:**
```
- ai/cdd_scorer.py: 계좌 블랙리스트(+50), 신규 계좌(+20), 고액(+15), 야간(+10),
  반복 시도(+20) 가중치로 0~100 점수를 반환하는 calculate_risk_score 함수를 구현하라.
  점수 ≥70이면 고위험, <30이면 저위험.
- ai/deepface_auth.py: DeepFace로 웹캠 캡처 후 등록 이미지와 비교하는 verify_face 함수를 구현하라.
  인식 실패 2회 시 {"verified": False, "fallback": True}를 반환하라.
- tests/test_vision.py: pytest로 CDD 스코어링 3케이스, DeepFace 인식 성공/실패를 테스트하라.
```

---

### 🧠 Agent 3: LLM Agent

**역할:** 앵커 질문 프롬프트 + Gemini LLM 연동 + STT/TTS 파이프라인 개발

**호출 시점:** DevOps Agent 완료 후, Backend Agent와 병렬 실행

**읽어야 할 컨텍스트:**
- `service_plan.md` § 3.2 앵커 보이스 인증, § 4.2 앵커 질문 5종
- `workflow.md` § Phase 2 앵커 질문 구조 설계 (5종 질문 + 판별 기준)
- `service_plan.md` § 8.3 인터페이스 합의 (LLM 응답 스키마)
- `stt_output/` 폴더 텍스트 샘플 (참조용)

**작성할 파일:**

| 파일 | 작업 내용 |
|------|---------|
| `ai/anchor_prompts.py` | 5가지 앵커 질문 + 유형별 판별 기준 + 시스템 프롬프트 |
| `ai/llm_engine.py` | `analyze_phishing_risk(conversation_log) -> dict` Gemini 연동 |
| `ai/whisper_stt.py` | `transcribe_realtime(audio_bytes, lang) -> str` 구현 |
| `ai/gtts_tts.py` | `synthesize_speech(text, lang) -> bytes` 구현 |
| `tests/test_llm.py` | 정상/대출사기/수사기관사칭 판별 단위 테스트 3종 |

**에이전트 지시 프롬프트 요약:**
```
- ai/anchor_prompts.py: workflow.md의 앵커 질문 5종과 판별 기준(대출사기형: Q②+Q④+Q⑤ 중 2개↑,
  수사기관사칭형: Q①+Q③+Q④ 중 2개↑)을 SYSTEM_PROMPT와 ANCHOR_QUESTIONS 리스트로 구현하라.
- ai/llm_engine.py: google.generativeai로 Gemini API를 호출하여 대화 로그를 분석하고
  {"is_phishing": bool, "confidence": float, "phishing_type": str}을 반환하는
  analyze_phishing_risk 함수를 구현하라. API 실패 시 GPT로 fallback하라.
- ai/whisper_stt.py: faster-whisper로 bytes 입력을 받아 한국어 텍스트로 변환하라.
- ai/gtts_tts.py: gTTS로 텍스트를 한국어 음성 bytes(mp3)로 변환하라.
- tests/test_llm.py: pytest로 3개 시나리오 판별 정확도 ≥85%를 검증하라.
```

---

### ⚙️ Agent 4: Backend Agent

**역할:** FastAPI 서버, 동적 라우팅, 스텔스 SOS 차단 로직 개발

**호출 시점:** DevOps Agent 완료 후, Vision/LLM Agent와 병렬 실행

**읽어야 할 컨텍스트:**
- `service_plan.md` § 5 시스템 아키텍처, § 8.3 인터페이스 합의
- `service_plan.md` § 3.1 동적 라우팅, § 3.3 스텔스 SOS
- `service_plan.md` § 4.1 핵심 기능 목록 (F-08, F-09)

**작성할 파일:**

| 파일 | 작업 내용 |
|------|---------|
| `backend/config.py` | 환경 변수 로드 (`GEMINI_API_KEY`, `RISK_THRESHOLD_HIGH` 등) |
| `backend/schemas.py` | Pydantic 요청/응답 모델 정의 |
| `backend/main.py` | FastAPI 앱 생성, CORS, 라우터 등록 |
| `backend/router.py` | 동적 라우팅 컨트롤러 (6개 엔드포인트) |
| `backend/stealth_sos.py` | `trigger_stealth_sos()` 비동기 차단 + 위장 UI 신호 |
| `tests/test_api.py` | httpx TestClient로 각 엔드포인트 통합 테스트 |

**에이전트 지시 프롬프트 요약:**
```
- backend/schemas.py: TransferRequest, RiskCheckResponse, FaceAuthResponse,
  VoiceStartRequest, VoiceAnswerRequest, SosResponse Pydantic 모델을 정의하라.
- backend/router.py: POST /api/transfer/risk-check → cdd_scorer 호출,
  POST /api/auth/face → deepface_auth 호출,
  POST /api/auth/voice/start → anchor_prompts에서 첫 질문 반환,
  POST /api/auth/voice/answer → llm_engine 호출,
  POST /api/sos/trigger → stealth_sos 호출 엔드포인트를 구현하라.
- backend/stealth_sos.py: 이체를 실제 차단하고 {"ui_mode": "stealth_complete", "blocked": True}를
  반환하는 비동기 함수를 구현하라. WARNING 레벨 로그를 남겨라.
- tests/test_api.py: httpx.AsyncClient로 각 엔드포인트의 정상/비정상 케이스를 테스트하라.
```

---

### 🎨 Agent 5: Frontend Agent

**역할:** Streamlit UI 전체, 화면 전환 흐름, 스텔스 SOS 위장 화면 개발

**호출 시점:** Backend Agent의 `schemas.py` 완료 후 실행 (화면-API 계약 확정 후)

**읽어야 할 컨텍스트:**
- `service_plan.md` § 5.1 데이터 흐름 (5단계)
- `service_plan.md` § 3.3 스텔스 SOS 위장 UI
- `backend/schemas.py` — API 요청/응답 스키마 (연동 기준)

**작성할 파일:**

| 파일 | 작업 내용 |
|------|---------|
| `frontend/state_manager.py` | Streamlit session_state 기반 화면 상태 관리 |
| `frontend/components/transfer_ui.py` | 계좌번호·금액 입력 폼 |
| `frontend/components/face_ui.py` | OpenCV 웹캠 스트림 + 인식 결과 표시 |
| `frontend/components/voice_ui.py` | 마이크 입력 → STT → 질문 응답 대화 화면 |
| `frontend/components/stealth_ui.py` | **위장 "이체 완료" 화면** (실제 차단 상태) |
| `frontend/components/result_ui.py` | 정상 이체 완료 화면 |
| `frontend/app.py` | 메인 Streamlit 앱, 화면 라우팅 통합 |

**에이전트 지시 프롬프트 요약:**
```
- frontend/state_manager.py: st.session_state로 현재 화면("transfer"→"face"→"voice"→"result"/"stealth")
  전환 로직을 관리하라.
- frontend/components/stealth_ui.py: 이체가 실제로 차단된 상태에서 st.success()로
  "✅ {amount:,}원이 이체되었습니다." 위장 화면을 렌더링하라.
  백그라운드에서는 /api/sos/trigger를 호출하여 차단을 완료하라.
- frontend/app.py: state_manager의 상태에 따라 각 컴포넌트를 순서대로 렌더링하라.
  Backend API는 httpx로 호출하라 (BASE_URL = http://localhost:8000).
```

---

### 🧪 Agent 6: Tester Agent

**역할:** 단위·통합·E2E 테스트 작성 및 시나리오 검증

**호출 시점:** 각 에이전트의 Week 1 개발 완료 후 (Day 7) 통합 실행

**읽어야 할 컨텍스트:**
- `service_plan.md` § 10 성공 지표 (KPI)
- `workflow.md` § Phase 9 E2E 시나리오 A·B·C
- `backend/schemas.py`, `ai/anchor_prompts.py` (테스트 입력 기준)

**작성할 파일:**

| 파일 | 작업 내용 |
|------|---------|
| `tests/conftest.py` | pytest fixture (FastAPI TestClient, 테스트 오디오 샘플) |
| `tests/test_cdd.py` | CDD 스코어링 3케이스 단위 테스트 |
| `tests/test_llm.py` | LLM 판별 3시나리오 단위 테스트 |
| `tests/test_vision.py` | DeepFace 인식 단위 테스트 |
| `tests/test_api.py` | FastAPI 엔드포인트 통합 테스트 |
| `tests/test_latency.py` | E2E 응답 시간 성능 테스트 |
| `tests/scenarios/normal.json` | 정상 이체 시나리오 데이터 |
| `tests/scenarios/loan_fraud.json` | 대출사기형 시나리오 데이터 |
| `tests/scenarios/agency_fraud.json` | 수사기관사칭형 시나리오 데이터 |

**에이전트 지시 프롬프트 요약:**
```
- tests/scenarios/*.json: 각 시나리오별 입력(계좌, 금액, 앵커 질문 응답 배열)과
  기대 출력(is_phishing, risk_score)을 JSON으로 정의하라.
- tests/test_api.py: httpx.AsyncClient로 시나리오 JSON을 입력하여
  /api/transfer/risk-check → /api/auth/voice/answer 체인을 테스트하라.
- tests/test_latency.py: 각 API 엔드포인트 응답 시간이 service_plan.md §10.1의
  목표값(CDD ≤500ms, STT ≤2000ms, LLM ≤3000ms)을 만족하는지 assert하라.
```

---

### 8.2 에이전트 간 의존성 및 실행 순서

```
[Agent 1: DevOps]  ← 필수 선행, 환경·디렉토리 구성 완료
        │
        ├──▶ [Agent 2: Vision]   독립 실행  →  ai/cdd_scorer.py
        │                                      ai/deepface_auth.py
        │
        ├──▶ [Agent 3: LLM]     독립 실행  →  ai/anchor_prompts.py
        │                                      ai/llm_engine.py
        │                                      ai/whisper_stt.py, gtts_tts.py
        │
        ├──▶ [Agent 4: Backend]  독립 실행  →  backend/schemas.py (선행)
        │         │                            backend/router.py, stealth_sos.py
        │         │
        │         └──▶ [Agent 5: Frontend]  schemas.py 완료 후 실행
        │                                   frontend/app.py + components/
        │
        └──▶ [Agent 6: Tester]  Week 1 완료(Day 7) 후 통합 실행
                                 tests/conftest.py, test_*.py, scenarios/
```

### 8.3 에이전트 호출 전 필수 인터페이스 합의

각 에이전트가 독립적으로 개발할 수 있도록 **아래 계약을 먼저 `backend/schemas.py`에 정의**한다:

```python
# backend/schemas.py  ← Agent 4가 작성, 나머지 에이전트가 참조

class RiskCheckRequest(BaseModel):
    account_number: str
    amount: int
    hour: int           # 0~23

class RiskCheckResponse(BaseModel):
    risk_score: int     # 0~100
    risk_level: str     # "low" | "high"

class VoiceAnswerRequest(BaseModel):
    question_id: int    # 1~5
    answer: bool

class PhishingAnalysisResponse(BaseModel):
    is_phishing: bool
    confidence: float
    phishing_type: str  # "loan_fraud" | "agency_fraud" | "normal"

class SosResponse(BaseModel):
    ui_mode: str        # "stealth_complete"
    blocked: bool
```



> 3명의 팀원이 **6개 기능 에이전트**로 역할을 나누어 병렬 개발을 수행한다.  
> 각 에이전트는 독립적인 파일 책임 범위를 가지며, 인터페이스를 합의한 뒤 동시에 개발한다.

### 8.1 에이전트 정의 및 담당 파일

---

#### 🛠️ DevOps Agent
> **담당자:** 장원재 | **핵심:** 환경·의존성·스크립트 관리

| 담당 파일 | 역할 |
|----------|------|
| `pyproject.toml` | 의존성 정의 및 버전 관리 |
| `requirements.txt` | pip 호환 패키지 목록 |
| `.env.example` | 환경 변수 템플릿 관리 |
| `scripts/fss_audio_crawler.py` | FSS 오디오 크롤러 유지보수 |
| `scripts/stt_batch_pipeline.py` | STT 배치 파이프라인 유지보수 |
| `README.md` | 프로젝트 실행 가이드 작성 |

---

#### 🎨 Frontend Agent
> **담당자:** 김금비 | **핵심:** Streamlit UI, 화면 전환 흐름, 스텔스 SOS 위장 화면

| 담당 파일 | 역할 |
|----------|------|
| `frontend/app.py` | Streamlit 메인 앱, 화면 상태 라우팅 |
| `frontend/state_manager.py` | 세션 상태 및 화면 전환 로직 |
| `frontend/components/transfer_ui.py` | 이체 입력 화면 컴포넌트 |
| `frontend/components/face_ui.py` | 안면 인식 카메라 화면 |
| `frontend/components/voice_ui.py` | 앵커 보이스 대화 화면 (STT/TTS 연동) |
| `frontend/components/stealth_ui.py` | **스텔스 SOS 위장 이체 완료 UI** |
| `frontend/components/result_ui.py` | 정상 이체 완료 화면 |

---

#### ⚙️ Backend Agent
> **담당자:** 민채영 | **핵심:** FastAPI 서버, 동적 라우팅, 스텔스 SOS 차단, 비동기 파이프라인

| 담당 파일 | 역할 |
|----------|------|
| `backend/main.py` | FastAPI 앱 엔트리포인트, 서버 설정 |
| `backend/router.py` | 동적 라우팅 컨트롤러 (저위험/고위험 분기) |
| `backend/stealth_sos.py` | 스텔스 SOS 차단 로직 및 위장 신호 처리 |
| `backend/schemas.py` | Pydantic 요청/응답 스키마 정의 |
| `backend/config.py` | 환경 변수 로드 및 설정값 관리 |

**주요 API 엔드포인트 책임:**

| Endpoint | 연동 에이전트 |
|----------|------------|
| `GET /health` | — |
| `POST /api/transfer/risk-check` | Vision Agent |
| `POST /api/auth/face` | Vision Agent |
| `POST /api/auth/voice/start` | LLM Agent |
| `POST /api/auth/voice/answer` | LLM Agent |
| `POST /api/sos/trigger` | Frontend Agent |

---

#### 🧪 Tester Agent
> **담당자:** 장원재 (Vision과 병행) | **핵심:** 단위·통합 테스트, 시나리오 검증

| 담당 파일 | 역할 |
|----------|------|
| `tests/test_cdd.py` | CDD 스코어링 단위 테스트 |
| `tests/test_llm.py` | LLM 판별 엔진 단위 테스트 |
| `tests/test_vision.py` | DeepFace 안면 인식 단위 테스트 |
| `tests/test_api.py` | FastAPI 엔드포인트 통합 테스트 |
| `tests/test_latency.py` | E2E 응답 시간 성능 테스트 |
| `tests/scenarios/normal.json` | 정상 이체 시나리오 |
| `tests/scenarios/loan_fraud.json` | 대출사기형 시나리오 |
| `tests/scenarios/agency_fraud.json` | 수사기관사칭형 시나리오 |

---

#### 🧠 LLM Agent
> **담당자:** 민채영 (Backend와 병행) | **핵심:** 앵커 프롬프트, Gemini/GPT 연동, STT/TTS 파이프라인

| 담당 파일 | 역할 |
|----------|------|
| `ai/anchor_prompts.py` | **5가지 앵커 질문 프롬프트 + 유형별 판별 기준** |
| `ai/llm_engine.py` | Gemini/GPT API 연동 및 피싱 판별 분석 |
| `ai/whisper_stt.py` | Whisper STT 실시간/배치 변환 모듈 |
| `ai/gtts_tts.py` | gTTS 텍스트→음성 변환 모듈 |

**Backend Agent와의 인터페이스 계약:**
```python
def analyze_phishing_risk(conversation_log: list[dict]) -> dict:
    """Returns: {"is_phishing": bool, "confidence": float, "phishing_type": str}"""

def transcribe_realtime(audio_bytes: bytes, lang: str = "ko") -> str:
    """Returns: transcribed text string"""

def synthesize_speech(text: str, lang: str = "ko") -> bytes:
    """Returns: audio bytes (mp3)"""
```

---

#### 👁️ Vision Agent
> **담당자:** 장원재 | **핵심:** CDD 위험도 스코어링, DeepFace 안면 인식, 사기 패턴 데이터 분석

| 담당 파일 | 역할 |
|----------|------|
| `ai/cdd_scorer.py` | **CDD 기반 위험도 점수 산출 (0~100)** |
| `ai/deepface_auth.py` | **DeepFace 실시간 안면 인식 + fallback 처리** |
| `downloads/fss_audio/` | 피싱 오디오 원본 (읽기 전용 참조) |
| `stt_output/` | STT 결과 텍스트 (분석 참조) |

**Backend Agent와의 인터페이스 계약:**
```python
def calculate_risk_score(account_info: dict, transaction_info: dict) -> int:
    """Returns: 0~100 risk score (≥70 = high risk)"""

def verify_face(registered_image_path: str) -> dict:
    """Returns: {"verified": bool, "distance": float, "time_ms": int}"""
```

---

### 8.2 에이전트 간 의존성 맵

```
[DevOps Agent] ──── 환경/패키지/스크립트 기반 ────── 모든 에이전트에 제공

[Vision Agent] ──┐   ai/cdd_scorer.py
                 │   ai/deepface_auth.py
                 ├──▶ [Backend Agent] ──▶ [Frontend Agent]
[LLM Agent]  ───┘      backend/router        frontend/app.py
                        backend/main          frontend/components/
  ai/llm_engine         backend/stealth_sos
  ai/whisper_stt
  ai/gtts_tts

[Tester Agent] ──── tests/ ◀── 모든 에이전트 산출물 검증
```

### 8.3 개발 착수 전 인터페이스 합의 항목

| 항목 | 합의값 | 관련 에이전트 |
|------|--------|------------|
| 위험도 점수 임계값 | ≥70 = 고위험, <30 = 저위험 | Vision ↔ Backend |
| LLM 응답 스키마 | `{"is_phishing": bool, "confidence": float, "phishing_type": str}` | LLM ↔ Backend |
| STT 입력 포맷 | `bytes` (PCM 16kHz 또는 mp3) | LLM ↔ Frontend |
| 스텔스 SOS 트리거 | `{"ui_mode": "stealth_complete", "blocked": True}` | Backend ↔ Frontend |
| 앵커 질문 스키마 | `{"question_id": int, "text": str, "answer": bool}` | LLM ↔ Backend ↔ Frontend |



| 팀원 | 포지션 | 주요 담당 기능 |
|------|--------|--------------|
| **장원재** | AI & Deep Learning | ▸ CDD 기반 피싱 분류 엔진 구축<br>▸ DeepFace 안면 인식 위험도 판별 로직<br>▸ 훈련 데이터 역엔지니어링 |
| **민채영** | Backend / LLM | ▸ FastAPI 라우팅 서버 설계·개발<br>▸ Gemini LLM 연동 및 비동기 처리<br>▸ 실시간 차단 및 위험 판별 파이프라인 |
| **김금비** | Frontend / Voice UI | ▸ Whisper STT 및 gTTS 보이스 인터페이스<br>▸ Streamlit 동적 UI 상태 관리<br>▸ 스텔스 SOS 위장 UI 개발 |

### 8.1 공통 작업

- 피싱 시나리오 설계 및 테스트 케이스 작성
- 코드 리뷰 및 E2E 통합 테스트
- 발표 자료 및 데모 준비

---

## 9. 리스크 및 대응 방안

| 리스크 | 발생 가능성 | 영향도 | 대응 방안 |
|--------|-----------|--------|---------|
| LLM API 응답 지연 (>3초) | 중 | 높음 | 비동기 처리 + 로컬 fallback 룰 기반 필터 |
| DeepFace 조도/각도 인식 실패 | 중 | 중간 | 재시도 로직 + 음성 인증 fallback 전환 |
| Whisper STT 방언/노이즈 인식 오류 | 중 | 중간 | 노이즈 전처리 + 재질문 로직 |
| 스텔스 SOS 위장 UI 발각 | 낮음 | 높음 | UI 자연스러움 개선, 즉시 백그라운드 신고 병행 |
| Gemini API 키 소진 / 비용 초과 | 낮음 | 중간 | GPT API 백업 설정, 캐싱 전략 적용 |
| Edge Case 피싱 패턴 미탐지 | 중 | 높음 | 앵커 질문 지속 고도화, 5가지 질문 추가 확장 |

---

## 10. 성공 지표 (KPI)

### 10.1 기술적 성공 지표

| 지표 | 목표값 | 측정 방법 |
|------|--------|---------|
| 피싱 탐지 정확도 | ≥ 85% | 테스트 시나리오 통과율 |
| 안면 인식 인증 성공률 | ≥ 90% | 정상 조건 테스트 |
| STT 인식 정확도 | ≥ 90% | 한국어 음성 테스트셋 |
| 전체 판별 응답 시간 | ≤ 3초 | End-to-End 레이턴시 측정 |
| E2E 파이프라인 무결성 | 100% | 핵심 시나리오 전체 통과 |

### 10.2 최종 성공 기준

> **Functional Integrity** — 모든 핵심 시나리오에서 논리적·기능적 무결성을 증명한다.

- [ ] 정상 이체 시 저위험 판별 → 안면 인식 패스
- [ ] 보이스피싱 시나리오 → 고위험 판별 → 앵커 보이스 인증 진입
- [ ] 앵커 질문 응답 분석 → 피싱 판단 → 스텔스 SOS 발동
- [ ] 가해자 앞에서도 위장 UI로 자연스러운 차단 시연 가능

---

## 부록

### A. 프로젝트 디렉토리 구조 (권장)

```
MAR_pj3_gr4_Anchor-Voice/
│
├── service_idea.md         # 서비스 아이디어 문서
├── service_plan.md         # 서비스 개발 계획서 (이 파일)
│
├── backend/
│   ├── main.py             # FastAPI 앱 엔트리포인트
│   ├── router.py           # 동적 라우팅 로직
│   ├── cdd_scorer.py       # CDD 위험도 스코어링 엔진
│   ├── llm_engine.py       # Gemini/GPT 연동 피싱 판별
│   └── stealth_sos.py      # 스텔스 SOS 처리 로직
│
├── ai/
│   ├── deepface_auth.py    # DeepFace 안면 인식 모듈
│   ├── whisper_stt.py      # Whisper STT 모듈
│   ├── gtts_tts.py         # gTTS TTS 모듈
│   └── anchor_prompts.py   # 5가지 앵커 질문 프롬프트
│
├── frontend/
│   ├── app.py              # Streamlit 메인 앱
│   ├── components/
│   │   ├── voice_ui.py     # 보이스 인터페이스 컴포넌트
│   │   └── stealth_ui.py   # 위장 이체 완료 UI
│   └── state_manager.py    # 동적 상태 관리
│
├── data/
│   └── phishing_samples/   # 금감원 피싱 오디오 샘플
│
├── tests/
│   ├── test_cdd.py
│   ├── test_llm.py
│   └── scenarios/          # 피싱 시나리오 테스트 케이스
│
├── requirements.txt
└── README.md
```

### B. 환경 설정 (requirements.txt 초안)

```txt
fastapi>=0.110.0
uvicorn>=0.29.0
streamlit>=1.33.0
deepface>=0.0.93
openai-whisper>=20231117
gTTS>=2.5.0
google-generativeai>=0.5.0
openai>=1.23.0
opencv-python>=4.9.0
python-multipart>=0.0.9
httpx>=0.27.0
```

### C. 참고 출처

- MBC 기사 (2025년 보도) — 보이스피싱 연령대별 피해 현황
- 경찰청 자료 (2025년 8월 기준) — 약 6천여 건 발생 통계
- 금융감독원 (2024.3.8) — 20대 85.2% 기관사칭 피해 통계
- 금융감독원 '그놈 목소리' — 실제 피싱 오디오 데이터
