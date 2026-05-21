"""
validator.py
Deterministic rule 기반으로 LLM 추출 결과를 원문 텍스트와 교차 검증합니다.

검증 항목:
1. evidence_quote가 원문에 실제로 존재하는지
2. deadline 키워드가 원문에서 확인되는지
3. owner(담당자)가 회의록 발화자로 등장하는지
"""

import re


def validate_with_rules(transcript: str, action_items: list) -> list:
    """
    각 액션 아이템에 대해 deterministic rule 검증을 수행합니다.

    Args:
        transcript: 원본 회의록 텍스트
        action_items: LLM이 추출한 액션 아이템 목록

    Returns:
        각 아이템의 검증 결과 목록
    """
    speakers = _extract_speakers(transcript)
    results = []

    for item in action_items:
        checks = {}

        # 검증 1: evidence_quote가 원문에 존재하는지
        checks["evidence_quote_존재"] = _check_evidence_quote(
            transcript, item.get("evidence_quote", "")
        )

        # 검증 2: deadline 키워드가 원문에서 확인되는지
        checks["deadline_원문_확인"] = _check_deadline_in_transcript(
            transcript, item.get("deadline", "unknown"), item.get("evidence_quote", "")
        )

        # 검증 3: owner가 회의록에 등장하는 발화자인지
        checks["owner_발화자_확인"] = _check_owner_is_speaker(
            speakers, item.get("owner", "unknown")
        )

        # 전체 상태 판정
        all_passed = all(c["passed"] for c in checks.values())
        any_failed = any(not c["passed"] for c in checks.values())
        status = "verified" if all_passed else ("failed" if any_failed else "partial")

        results.append({
            "task": item.get("task", "N/A"),
            "owner": item.get("owner", "unknown"),
            "status": status,
            "checks": checks,
            "llm_confidence": item.get("confidence", "unknown"),
        })

    return results


def _extract_speakers(transcript: str) -> set:
    """회의록에서 발화자 이름을 추출합니다. (예: '민아:', '준호:' 패턴)"""
    pattern = re.compile(r"^([가-힣a-zA-Z]{1,10}):", re.MULTILINE)
    matches = pattern.findall(transcript)
    return set(matches)


def _check_evidence_quote(transcript: str, quote: str) -> dict:
    """evidence_quote의 핵심 구절이 원문에 존재하는지 확인합니다."""
    if not quote:
        return {"passed": False, "detail": "evidence_quote가 비어있음"}

    # 공백 정규화 후 부분 일치 확인
    normalized_transcript = re.sub(r"\s+", " ", transcript)
    normalized_quote = re.sub(r"\s+", " ", quote).strip()

    # 긴 quote는 앞뒤 15자 핵심 구절로 검증
    if len(normalized_quote) > 30:
        head = normalized_quote[:15]
        tail = normalized_quote[-15:]
        head_found = head in normalized_transcript
        tail_found = tail in normalized_transcript
        if head_found and tail_found:
            return {"passed": True, "detail": "원문에서 앞뒤 구절 모두 확인됨"}
        elif head_found:
            return {"passed": False, "detail": f"앞부분만 확인됨, 뒷부분 미확인: '{tail}'"}
        else:
            return {"passed": False, "detail": f"원문에서 찾을 수 없음: '{head}'"}
    else:
        found = normalized_quote in normalized_transcript
        return {
            "passed": found,
            "detail": "원문에서 확인됨" if found else f"원문에서 찾을 수 없음: '{normalized_quote}'",
        }


def _check_deadline_in_transcript(transcript: str, deadline: str, evidence_quote: str) -> dict:
    """deadline 키워드가 원문(또는 evidence_quote 주변)에 존재하는지 확인합니다."""
    if deadline == "unknown":
        return {"passed": True, "detail": "deadline이 unknown으로 명시됨 (검증 불필요)"}

    # deadline에서 핵심 키워드 추출
    deadline_keywords = _extract_deadline_keywords(deadline)
    if not deadline_keywords:
        return {"passed": False, "detail": f"deadline '{deadline}'에서 키워드를 추출할 수 없음"}

    found_keywords = [kw for kw in deadline_keywords if kw in transcript]
    if found_keywords:
        return {
            "passed": True,
            "detail": f"원문에서 키워드 확인됨: {found_keywords}",
        }
    else:
        return {
            "passed": False,
            "detail": f"원문에서 deadline 키워드를 찾을 수 없음: {deadline_keywords}",
        }


def _extract_deadline_keywords(deadline: str) -> list:
    """deadline 문자열에서 검증에 사용할 핵심 키워드를 추출합니다."""
    keywords = []
    # 요일
    days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    for day in days:
        if day in deadline or day[:1] in deadline:
            keywords.append(day)
    # 시간 단위
    for kw in ["오전", "오후", "점심", "저녁", "아침", "오늘", "내일", "이번 주", "다음 주"]:
        if kw in deadline:
            keywords.append(kw)
    # 날짜 패턴 (예: 목요일, 금요일)
    pattern = re.compile(r"[가-힣]+요일")
    matches = pattern.findall(deadline)
    keywords.extend(matches)

    return list(set(keywords))


def _check_owner_is_speaker(speakers: set, owner: str) -> dict:
    """owner가 회의록에 등장하는 발화자인지 확인합니다."""
    if owner == "unknown":
        return {"passed": True, "detail": "owner가 unknown으로 명시됨 (검증 불필요)"}

    # 부분 일치 허용 (예: "준호" in speakers)
    for speaker in speakers:
        if owner in speaker or speaker in owner:
            return {"passed": True, "detail": f"발화자 목록에서 확인됨: '{speaker}'"}

    return {
        "passed": False,
        "detail": f"'{owner}'가 발화자 목록에 없음. 발화자: {sorted(speakers)}",
    }