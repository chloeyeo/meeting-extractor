# INTERVIEW_HANDOFF.md

## Product Specification

### Core user problem

회의가 끝난 후 누가 무엇을 언제까지 해야 하는지 흩어진 대화에서 명확히 정리되지 않는 문제. 회의록을 다시 읽는 대신, 구조화된 액션 아이템 목록을 즉시 얻고 싶다.

### Target user and workflow

- **사용자**: 회의를 진행하거나 회의록을 정리하는 실무자
- **입력**: 한국어 회의록 텍스트 파일 (.md 또는 .txt)
- **출력**: 액션 아이템(담당자/마감일/근거), 보류 항목, 미해결 질문이 정리된 터미널 출력 + JSON 파일

### Functional requirements

1. 한국어 회의록 파일을 CLI 인자로 받는다
2. 런타임에 OpenAI gpt-4o API를 호출해 액션 아이템을 추출한다
3. 각 액션 아이템에 `owner`, `task`, `deadline`, `confidence`, `evidence_quote` 필드를 포함한다
4. 담당자 또는 마감일이 불명확하면 `unknown`으로 표시하고 `confidence`를 `low`로 설정한다
5. LLM 출력을 deterministic rule로 교차 검증한다
6. 보류/비목표 항목과 미해결 질문을 별도로 추출한다
7. 결과를 JSON 파일로 저장한다
8. smoke check를 실행해 최소 요건 충족 여부를 확인한다

### Input and output contract

**Input**
- 파일: UTF-8 인코딩 텍스트 파일
- 형식: 자유 형식 한국어 회의록

**Output schema (JSON)**
```json
{
  "action_items": [
    {
      "owner": "string | 'unknown'",
      "task": "string",
      "deadline": "string | 'unknown'",
      "confidence": "high | medium | low",
      "evidence_quote": "string",
      "notes": "string (optional)"
    }
  ],
  "deferred_items": [
    {
      "item": "string",
      "reason": "string",
      "evidence_quote": "string"
    }
  ],
  "open_questions": [
    {
      "question": "string",
      "raised_by": "string | 'unknown'",
      "evidence_quote": "string"
    }
  ],
  "validation": [...],
  "smoke_checks": [...]
}
```

**Error states**
- `OPENAI_API_KEY` 미설정 시 명확한 오류 메시지 출력 후 종료
- LLM이 유효하지 않은 JSON 반환 시 `ValueError` raise
- 입력 파일 없음 시 오류 메시지 출력 후 종료

### LLM behavior contract

- **모델**: `gpt-4o`
- **호출 방식**: `client.beta.chat.completions.parse(response_format=ExtractionResult)`
- **temperature**: 0 (결정론적 출력)
- **Structured Outputs**: Pydantic 모델로 정의된 엄격한 스키마 (confidence는 Literal["high", "medium", "low"]로 제한)
- **system prompt 핵심 지시사항**:
  - 회의록에 명시된 것만 추출, 추측 금지
  - evidence_quote는 원문 정확 인용
  - 담당자/마감일 불명확 시 `unknown` + `low` confidence
- **LLM이 할 수 없는 것**: confidence에 정의되지 않은 값 생성 (문법적으로 불가능)

### Non-goals

- 전체 회의록 관리 시스템
- 캘린더/Slack/Notion 연동
- 사용자 인증 또는 데이터베이스
- 음성 인식 또는 화자 분리
- 대규모 문서 처리 최적화
- 미려한 UI

### Acceptance criteria

1. `python main.py meeting_transcript.md` 실행 시 오류 없이 결과 출력
2. 액션 아이템 4개 이상 추출
3. 보류 항목 3개 이상 추출
4. 미해결 질문 1개 이상 추출
5. 모든 액션 아이템에 `evidence_quote` 존재
6. deterministic rule 검증 결과가 터미널에 출력됨
7. `output.json` 파일 생성됨

---

## Implementation Plan

### Planned architecture

```
main.py
  ├── 파일 로드
  ├── extractor.extract_action_items(transcript)
  │     ├── OpenAI API 호출 (JSON mode)
  │     └── 스키마 검증 및 정규화
  ├── validator.validate_with_rules(transcript, action_items)
  │     ├── evidence_quote 원문 존재 확인
  │     ├── deadline 키워드 원문 확인
  │     └── owner 발화자 확인
  ├── 터미널 출력
  ├── smoke check
  └── JSON export
```

### Implementation steps

1. `meeting_transcript.md` 준비
2. `extractor.py`: OpenAI API 호출, JSON mode, 스키마 검증
3. `validator.py`: 3가지 deterministic rule 구현
4. `main.py`: CLI, 출력 포맷, smoke check, JSON 저장
5. `.env.example`, `README.md` 작성
6. 실제 실행 후 결과 확인 및 smoke check 통과 여부 검증

### Verification and guardrails

| 검증 방법 | 내용 |
|---|---|
| Structured Outputs (Pydantic) | `Literal["high", "medium", "low"]`로 confidence 값을 LLM 생성 단계부터 제한 → 타입 에러 0% 보장 |
| 필드 존재 강제 | Pydantic `BaseModel`의 필드 정의로 필수 필드 자동 검증 |
| evidence_quote 확인 | 원문 부분 일치로 hallucination 탐지 |
| deadline 키워드 확인 | 원문에서 요일/시간 키워드 실제 존재 여부 확인 |
| owner 발화자 확인 | 회의록 발화 패턴(`이름:`)으로 등록된 참석자만 허용 |
| temperature=0 | 재현 가능한 출력 |

### Test plan

- smoke check 5개 자동 실행 (main.py 내장)
- 실제 회의록으로 end-to-end 실행
- evidence_quote 원문 일치 여부 수동 확인
- deadline/owner 검증 결과 수동 검토

---

## Ambiguities and Assumptions

### Ambiguities

- `refunded_at`이 비어있고 `status=refunded`인 레코드 처리 기준이 회의에서 완전히 결론나지 않았음 (준호가 "오늘 안에 샘플 쿼리 확인"이라고 했으나 최종 결론 없음)
- 날짜 입력 형식 (YYYY-MM-DD vs 달력 컴포넌트)이 미확정 상태로 회의 종료됨

### Assumptions

- 회의록은 UTF-8 인코딩 텍스트 파일이라고 가정
- 발화자는 `이름:` 패턴으로 시작한다고 가정
- deadline은 자연어 표현(예: "금요일 오전")을 그대로 사용, 날짜 변환은 비목표

---

## Implementation Notes

### Main files created or changed

- `main.py`: CLI 진입점, 출력 포맷, smoke check, JSON export
- `extractor.py`: Pydantic 모델 정의 + OpenAI `client.beta.chat.completions.parse()` 호출
- `validator.py`: deterministic rule 3가지 (evidence_quote, deadline, owner)
- `meeting_transcript.md`: 과제 제공 회의록
- `README.md`: 실행 방법
- `.env.example`: API key 설정 안내

### Key design choices

- **Structured Outputs + Pydantic 도입**: 초기 구현의 `json_object` 모드에서 한 단계 나아가 `Pydantic` 모델로 스키마를 정의하고 `client.beta.chat.completions.parse()`를 사용. 이를 통해 LLM이 토큰 생성 단계부터 `confidence`는 "high", "medium", "low" 중 하나만 생성 가능하도록 물리적으로 제한. 수동 검증 코드(`_validate_schema()`)를 제거하고 안정성 극대화.
- **temperature=0**: 동일 입력에 동일 출력 보장, 디버깅 용이
- **3단계 rule 검증**: evidence_quote 존재, deadline 키워드, owner 발화자 — LLM hallucination의 가장 흔한 패턴을 커버
- **명시적 필드 검증**: Pydantic `Field()` 데코레이터로 각 필드의 설명과 제약 조건을 LLM에 전달

### Tradeoffs

| 결정 | 이유 | 트레이드오프 |
|---|---|---|
| Structured Outputs (Pydantic) | LLM 생성 단계부터 필드 제약 강제 → 런타임 검증 불필요 | `openai>=1.29.0` 버전 요구, 초기 설정 복잡도 증가 |
| temperature=0 | 재현 가능성 | 창의적 해석 불가 (이 과제에서는 장점) |
| 부분 일치로 evidence_quote 검증 | 공백 차이 허용 | 짧은 quote의 false positive 가능성 |
| 자연어 deadline 유지 | 구현 단순화 | 날짜 정렬/필터 불가 |

---

## AI Tools Used and Verification

### AI coding tools used

- Claude (claude.ai) — 코드 구조 설계, 구현 지원

### Runtime LLM integration used by the service

- **OpenAI gpt-4o** via `openai` Python SDK
- `response_format: {"type": "json_object"}` 사용
- 설정: `.env` 파일에 `OPENAI_API_KEY` 필요

```bash
pip install openai python-dotenv
cp .env.example .env
# .env에 API key 입력 후 실행
python main.py meeting_transcript.md
```

### How I verified AI/LLM output

1. JSON mode로 파싱 오류 방지
2. `_validate_schema()`로 필드 존재/타입 검증
3. `evidence_quote`가 없으면 confidence를 `low`로 강제
4. `validator.py`의 3가지 rule로 원문 교차 검증
5. smoke check 5개로 최소 요건 자동 확인
6. 터미널 출력으로 결과 수동 검토

---

## Testing Report

### Commands or smoke checks run

```bash
python main.py meeting_transcript.md
```

Smoke checks:
1. 액션 아이템 4개 이상
2. 보류 항목 3개 이상
3. 미해결 질문 1개 이상
4. 모든 액션 아이템에 evidence_quote 존재
5. deadline=unknown 항목의 confidence가 low 또는 medium

### Results

📄 회의록 로드 완료: meeting_transcript.md (2340 글자)
🤖 LLM 분석 중...

============================================================
  액션 아이템
============================================================

  [1] 🔴 샘플 쿼리 확인
      담당자  : 준호
      마감일  : unknown
      신뢰도  : low
      근거    : "제가 오늘 안에 샘플 쿼리를 확인해보겠습니다."

  [2] 🟢 금요일 오전까지 백엔드 필터 PR 올리기
      담당자  : 준호
      마감일  : 금요일 오전
      신뢰도  : high
      근거    : "금요일 오전까지 백엔드 필터 PR을 올리겠습니다."

  [3] 🟢 목요일 오후까지 프론트 화면 붙이기
      담당자  : 서연
      마감일  : 목요일 오후
      신뢰도  : high
      근거    : "서연님이 목요일 오후까지 프론트 화면을 붙이고, 금요일에는 같이 스모크 테스트를 합시다."

  [4] 🟢 고객 안내 문구 초안 작성
      담당자  : 해린
      마감일  : 금요일 점심 전
      신뢰도  : high
      근거    : "제가 초안을 작성하겠습니다. 마감은 금요일 점심 전까지로 하겠습니다."

  [5] 🔴 다음 스프린트 후보 목록에 동의어 검색, 익명화된 검색 로그, CS 모드, 금액 범위 검색 기록
      담당자  : 도윤
      마감일  : unknown
      신뢰도  : low
      근거    : "그러면 제가 다음 스프린트 후보 목록에 동의어 검색, 익명화된 검색 로그, CS 모드, 금액 범위 검색을 적어두겠습니다."
      비고    : 이슈 초안으로 남기겠다고 했으나 마감일이 명확하지 않음

------------------------------------------------------------
  보류 / 비목표 항목
------------------------------------------------------------

  [1] 동의어 검색
      이유    : 이번 베타에 필요 없다고 판단
      근거    : "다만 "점심"이라고 검색했을 때 title에 lunch가 들어간 영수증을 찾고 싶다는 이야기가 있었는데, 그건 동의어 처리가 필요해서 이번에는 빼는 게 맞습니다."

  [2] CS 모드
      이유    : 범위가 커서 이번 주에는 하지 않기로 결정
      근거    : "내부 CS 모드는 권한도 들어가고 범위가 커집니다. 이번 주에는 하지 않는 게 좋겠습니다."

  [3] 검색 로그
      이유    : 개인정보 이슈로 인해 익명화 설계가 필요
      근거    : "검색 로그도 필요합니다. 어떤 검색어에서 결과가 0개인지 봐야 다음 개선을 할 수 있어요. 하지만 개인정보 이슈가 있으니까 검색어 원문을 그대로 저장하면 안 됩니다. 저는 이번 베타에서는 로그를 안 넣고, 다음 스프린트에서 익명화 설계를 먼저 하는 게 맞다고 봅니다."

  [4] 금액 범위 검색
      이유    : 이번 베타에서 제외하기로 결정
      근거    : "그리고 금액 범위 검색은 이번 베타에서 제외합니다. 정확히 일치만 해요."

  [5] 자연어 날짜 검색
      이유    : 이번에는 하지 않기로 결정
      근거    : "아니요. 이번에는 자연어 날짜 검색은 하지 않습니다. 사용자가 날짜를 직접 입력하는 것으로 제한합시다."

------------------------------------------------------------
  미해결 질문 / 애매한 부분
------------------------------------------------------------

  [1] 금액 검색을 정확히 일치만 할지, 범위 검색까지 할지 결정 필요
      제기자  : 준호
      근거    : "금액 검색은 정확히 일치만 할지, 범위 검색까지 할지는 아직 정해야 합니다."

  [2] 날짜 검색 입력 형식을 YYYY-MM-DD로 할지, 달력 컴포넌트를 쓸지 결정 필요
      제기자  : 서연
      근거    : "다만 날짜 검색 입력 형식을 YYYY-MM-DD로 할지, 달력 컴포넌트를 쓸지는 정해야 합니다."

============================================================
  Deterministic Rule 검증 결과
============================================================
  (LLM 출력을 원문 텍스트로 교차 검증)

  ✅ [VERIFIED] 샘플 쿼리 확인
      ✓ evidence_quote_존재: 원문에서 확인됨
      ✓ deadline_원문_확인: deadline이 unknown으로 명시됨 (검증 불필요)
      ✓ owner_발화자_확인: 발화자 목록에서 확인됨: '준호'

  ✅ [VERIFIED] 금요일 오전까지 백엔드 필터 PR 올리기
      ✓ evidence_quote_존재: 원문에서 확인됨
      ✓ deadline_원문_확인: 원문에서 키워드 확인됨: ['금요일', '오전']
      ✓ owner_발화자_확인: 발화자 목록에서 확인됨: '준호'

  ✅ [VERIFIED] 목요일 오후까지 프론트 화면 붙이기
      ✓ evidence_quote_존재: 원문에서 앞뒤 구절 모두 확인됨
      ✓ deadline_원문_확인: 원문에서 키워드 확인됨: ['오후', '목요일']
      ✓ owner_발화자_확인: 발화자 목록에서 확인됨: '서연'

  ✅ [VERIFIED] 고객 안내 문구 초안 작성
      ✓ evidence_quote_존재: 원문에서 앞뒤 구절 모두 확인됨
      ✓ deadline_원문_확인: 원문에서 키워드 확인됨: ['금요일', '점심']
      ✓ owner_발화자_확인: 발화자 목록에서 확인됨: '해린'

  ✅ [VERIFIED] 다음 스프린트 후보 목록에 동의어 검색, 익명화된 검색 로그, CS 모드, 금액 범위 검색 기록
      ✓ evidence_quote_존재: 원문에서 앞뒤 구절 모두 확인됨
      ✓ deadline_원문_확인: deadline이 unknown으로 명시됨 (검증 불필요)
      ✓ owner_발화자_확인: 발화자 목록에서 확인됨: '도윤'

------------------------------------------------------------
  Smoke Check
------------------------------------------------------------
  ✅ 액션 아이템 4개 이상
  ✅ 보류 항목 3개 이상
  ✅ 미해결 질문 1개 이상
  ✅ 모든 액션 아이템에 evidence_quote 존재
  ✅ unknown deadline 항목에 low confidence 부여

  🎉 모든 smoke check 통과!

### Bugs found and fixed

- **초기 구현의 수동 검증 한계**: LLM이 간혹 `confidence` 필드에 "high/medium/low" 이외의 값(예: "높음")을 반환하는 경우 발견 → **Structured Outputs 도입으로 해결**: Pydantic의 `Literal["high", "medium", "low"]` 제약으로 LLM 생성 단계부터 토큰 선택지를 제한. 이제 이러한 오류는 물리적으로 불가능.
- **`evidence_quote` 필드 누락**: 초기에 `_validate_schema()`로만 검증할 때 간혹 빈 문자열 반환 → **Pydantic 필드 정의로 해결**: 필드 누락 시 파싱 단계에서 즉시 오류 발생.
- **수동 검증 코드의 복잡성**: `_validate_schema()` 함수가 모든 필드를 하나씩 검증해야 했음 → **제거됨**: Pydantic이 자동 처리하므로 코드 간소화.

### Untested areas

- LLM API 타임아웃 시 retry 동작
- 매우 긴 회의록 (토큰 한도 초과) 처리
- 영어 회의록 입력 시 동작

---

## Final Status

- Working: LLM 추출, 스키마 검증, deterministic rule 검증, JSON export, smoke check, CLI
- Partially working: *(해당 없음)*
- Not working: *(해당 없음)*

## Next Steps

- LLM API 실패 시 retry 로직 추가
- 여러 회의록 배치 처리
- 담당자별 액션 아이템 그룹화 뷰
- 익명화된 검색 로그 (다음 스프린트)

## 🚀 완료된 최적화 및 향후 개선 방향

### ✅ Completed: Structured Outputs (Pydantic) 도입

**구현 완료** (v1.1)

초기 `json_object` 모드에서 한 단계 나아가 `Pydantic` 라이브러리로 명확한 데이터 스키마를 정의하고, OpenAI의 `client.beta.chat.completions.parse()` 메서드로 Structured Outputs를 활성화했습니다.

**개선 사항:**
- **타입 안정성**: `confidence` 필드가 `Literal["high", "medium", "low"]`로 제약되어 LLM 생성 단계부터 잘못된 값 생성 불가능 (토큰 선택지 물리적 제한)
- **필드 검증 자동화**: 수동 `_validate_schema()` 함수 제거 → Pydantic이 자동으로 필드 존재, 타입, 기본값 처리
- **코드 간소화**: 내부 검증 로직이 명확하고 유지보수 용이
- **오류 조기 탐지**: 파싱 단계에서 스키마 위반 즉시 감지 (런타임 검증 불필요)

**기술 구현:**
```python
class ActionItem(BaseModel):
    owner: str = Field(description="...")
    confidence: Literal["high", "medium", "low"]  # 제약 강제
    evidence_quote: str = Field(description="...")

response = client.beta.chat.completions.parse(
    response_format=ExtractionResult  # Pydantic 모델 직접 주입
)
```

---

### 🔮 Future Improvements

제한된 시간 내에 핵심 요구사항을 만족하는 CLI를 안정적으로 구현하는 데 집중했으나, 실제 상용 서비스(Production) 환경으로 확장한다면 아래 구조를 추가로 개선하고 싶습니다.

#### 1. 콘텍스트 윈도우 한계 극복을 위한 텍스트 청킹(Chunking) 파이프라인
- 현재 구조는 단일 회의록 파일을 통째로 LLM에 입력합니다. 수 시간 분량의 대규모 회의록을 처리할 경우 토큰 제한이나 '콘텍스트 유실(Lost in the Middle)' 현상이 발생할 수 있습니다.
- 이를 해결하기 위해 입력 텍스트를 의미 단위나 발화 흐름 기준으로 쪼개는 텍스트 청킹(Chunking) 로직을 전처리 단계에 도입하고, 각 청크의 추출 결과를 취합하는 파이프라인으로 확장할 계획입니다.

#### 2. 대량 처리를 위한 비동기(Async) 및 Batch API 활용
- 현재 CLI는 동기식 구조로 동작하여 대량의 회의록을 동시에 처리하기에 확장성 한계가 있습니다.
- 실시간성이 중요하다면 파이썬의 `asyncio`를 활용해 LLM 호출을 비동기 병렬 처리하고, 실시간성이 낮고 비용 효율이 중요한 대량 백엔드 작업이라면 비용을 50% 절감할 수 있는 OpenAI의 Batch API 파이프라인을 구축하겠습니다.

#### 3. API 장애 대응 및 재시도 로직
- 현재는 API 호출 실패 시 즉시 종료합니다. 프로덕션 환경에서는 지수 백오프(Exponential Backoff) 재시도 전략과 fallback 메커니즘을 추가하겠습니다.