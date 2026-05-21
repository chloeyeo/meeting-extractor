# 회의록 액션 아이템 추출기

한국어 회의록을 입력받아 LLM으로 액션 아이템, 보류 항목, 미해결 질문을 추출하고, deterministic rule로 교차 검증합니다.

## 요구사항

- Python 3.9+
- OpenAI API key

## 설치

```bash
pip install openai python-dotenv
```

## 설정

```bash
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY 값을 입력하세요
```

## 실행

```bash
# 기본 실행 (meeting_transcript.md 사용, output.json 저장)
python main.py

# 파일 직접 지정
python main.py meeting_transcript.md

# 출력 파일 경로 지정
python main.py meeting_transcript.md --output result.json
```

## 출력 예시

```
============================================================
  액션 아이템
============================================================

  [1] 🟢 백엔드 필터 PR 올리기
      담당자  : 준호
      마감일  : 금요일 오전
      신뢰도  : high
      근거    : "금요일 오전까지 백엔드 필터 PR을 올리겠습니다"

...

============================================================
  Deterministic Rule 검증 결과
============================================================

  ✅ [VERIFIED] 백엔드 필터 PR 올리기
      ✓ evidence_quote_존재: 원문에서 확인됨
      ✓ deadline_원문_확인: 원문에서 키워드 확인됨: ['금요일', '오전']
      ✓ owner_발화자_확인: 발화자 목록에서 확인됨: '준호'
```

## 파일 구조

```
├── main.py                 # CLI 진입점
├── extractor.py            # LLM 호출 + 스키마 검증
├── validator.py            # Deterministic rule 검증
├── meeting_transcript.md   # 입력 회의록
├── output.json             # 실행 후 생성되는 결과
├── .env.example            # 환경변수 예시
└── INTERVIEW_HANDOFF.md    # 구현 스펙 및 계획
```

## 설계 원칙

- LLM 출력을 그대로 믿지 않고 3가지 rule로 교차 검증
- 담당자/마감일이 불명확하면 추측 없이 `unknown` + `low confidence` 표시
- `evidence_quote`는 원문 인용 필수, 없으면 confidence 강제 `low`
- JSON export 기본 포함

## 📑 과제 상세 설계 및 구현 아키텍처
본 프로젝트의 세부 스펙, 기술 스택 선정 이유(JSON Mode, Temperature 설정 등), 그리고 검증 레이어에 대한 자세한 설명은 [INTERVIEW_HANDOFF.md](./INTERVIEW_HANDOFF.md) 문서에 상세히 기록되어 있습니다. 면접 검토 시 해당 문서를 참고해 주시면 감사하겠습니다.