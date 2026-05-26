"""
extractor.py
LLM을 사용해 회의록에서 액션 아이템, 보류 항목, 미해결 질문을 추출합니다.
"""

import os
import time
from typing import Literal

from dotenv import load_dotenv
from openai import APIConnectionError, OpenAI, RateLimitError
from pydantic import BaseModel, Field

load_dotenv()



class ActionItem(BaseModel):
    owner: str = Field(description="담당자 이름 (불명확하면 'unknown')")
    task: str = Field(description="구체적인 할 일")
    deadline: str = Field(description="마감일 또는 기간 (불명확하면 'unknown')")
    confidence: Literal["high", "medium", "low"] = Field(
        description="high: 담당자/마감일/근거 모두 명확 | medium: 하나 불명확 | low: 둘 다 불명확"
    )
    evidence_quote: str = Field(description="회의록 원문에서 발췌한 근거 문장 (정확히 인용)")
    notes: str = Field(default="", description="(선택) 추가 맥락")


class DeferredItem(BaseModel):
    item: str = Field(description="보류/제외된 항목")
    reason: str = Field(description="제외 이유")
    evidence_quote: str = Field(description="회의록 원문에서 발췌한 근거 문장")


class OpenQuestion(BaseModel):
    question: str = Field(description="미해결 질문 또는 애매한 부분")
    raised_by: str = Field(description="질문을 제기한 사람 (불명확하면 'unknown')")
    evidence_quote: str = Field(description="회의록 원문에서 발췌한 근거 문장")


class ExtractionResult(BaseModel):
    action_items: list[ActionItem]
    deferred_items: list[DeferredItem]
    open_questions: list[OpenQuestion]


SYSTEM_PROMPT = """당신은 한국어 회의록을 분석해 액션 아이템을 추출하는 전문가입니다.

규칙:
1. 액션 아이템은 회의록에 명시적으로 언급된 것만 추출합니다. 추측하지 마세요.
2. 담당자나 마감일이 명확하지 않으면 "unknown"으로 표시하고 confidence를 low로 설정하세요.
3. evidence_quote는 회의록 원문을 정확히 인용해야 합니다. 요약하거나 변형하지 마세요.
4. 보류 항목은 "이번에는 하지 않는다", "제외한다", "다음 스프린트에" 등의 표현으로 명시된 것입니다.
5. 미해결 질문은 회의에서 답이 나오지 않았거나 애매하게 남은 것입니다.
6. confidence 기준:
   - high: 담당자, 마감일, 근거가 모두 명확
   - medium: 담당자 또는 마감일 중 하나가 불명확
   - low: 둘 다 불명확하거나 근거가 약함"""

USER_PROMPT_TEMPLATE = """다음 회의록을 분석해 액션 아이템, 보류 항목, 미해결 질문을 추출하세요.

회의록:
{transcript}"""



def extract_action_items(transcript: str) -> dict:
    """
    OpenAI gpt-4o를 사용해 회의록에서 구조화된 정보를 추출합니다.
    Structured Outputs로 confidence를 물리적으로 제한하고, 재시도 로직으로 일시적 오류 대응합니다.

    Args:
        transcript: 회의록 전체 텍스트

    Returns:
        action_items, deferred_items, open_questions를 포함한 dict

    Raises:
        Exception: API 호출 최종 실패 시
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
            ".env 파일을 확인하거나 export OPENAI_API_KEY=your_key를 실행하세요."
        )

    client = OpenAI(api_key=api_key)
    user_prompt = USER_PROMPT_TEMPLATE.format(transcript=transcript)

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = client.beta.chat.completions.parse(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=ExtractionResult,
                temperature=0,
            )

            parsed_result = response.choices[0].message.parsed
            if parsed_result is None:
                raise ValueError("LLM 파싱 실패")

            return {
                "action_items": [item.model_dump() for item in parsed_result.action_items],
                "deferred_items": [item.model_dump() for item in parsed_result.deferred_items],
                "open_questions": [item.model_dump() for item in parsed_result.open_questions],
            }

        except (APIConnectionError, RateLimitError, TimeoutError) as e:
            if attempt == max_attempts - 1:
                raise
            wait_time = 2 ** attempt
            print(f"⚠️  API 오류 (시도 {attempt + 1}/{max_attempts}): {type(e).__name__}")
            print(f"   {wait_time}초 후 재시도...")
            time.sleep(wait_time)



