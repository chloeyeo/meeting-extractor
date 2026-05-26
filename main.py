#!/usr/bin/env python3
"""
회의록 액션 아이템 추출기 CLI
Usage: python main.py <meeting_transcript.md> [--output output.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Windows 환경에서 UTF-8 출력 지원
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from extractor import extract_action_items
from validator import validate_with_rules


def chunk_transcript_by_speaker(
    transcript: str, chunk_size: int = 5000, overlap: int = 500
) -> list[str]:
    """
    발화자 기준으로 회의록을 청크로 분할합니다.
    청크 경계에서 문장이 잘리지 않도록 오버랩을 설정합니다.

    Args:
        transcript: 전체 회의록
        chunk_size: 각 청크의 목표 크기 (글자)
        overlap: 청크 간 오버랩 크기

    Returns:
        청크 목록
    """
    if len(transcript) <= chunk_size:
        return [transcript]

    chunks = []
    lines = transcript.split("\n")
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > chunk_size and current_chunk:
            chunks.append(current_chunk)
            # 오버랩: 이전 청크의 마지막 일부를 다음 청크에 포함
            if overlap > 0:
                lines_in_chunk = current_chunk.split("\n")
                overlap_lines = "\n".join(lines_in_chunk[-3:])  # 마지막 3줄
                current_chunk = overlap_lines + "\n" + line
            else:
                current_chunk = line
        else:
            current_chunk += ("\n" if current_chunk else "") + line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def deduplicate_items(items: list, key_fields: list[str]) -> list:
    """같은 내용의 항목 중복 제거."""
    seen = set()
    deduplicated = []
    for item in items:
        key = tuple(item.get(field, "") for field in key_fields)
        if key not in seen:
            seen.add(key)
            deduplicated.append(item)
    return deduplicated


def merge_results(results_list: list[dict]) -> dict:
    """
    여러 청크에서 추출한 결과를 통합하고 중복을 제거합니다.

    Args:
        results_list: extract_action_items() 결과 목록

    Returns:
        통합된 결과
    """
    merged = {"action_items": [], "deferred_items": [], "open_questions": []}

    # 액션 아이템 통합 (task, owner, deadline로 중복 제거)
    all_action_items = []
    for result in results_list:
        all_action_items.extend(result.get("action_items", []))
    merged["action_items"] = deduplicate_items(
        all_action_items, ["task", "owner", "deadline"]
    )

    # 보류 항목 통합 (item으로 중복 제거)
    all_deferred = []
    for result in results_list:
        all_deferred.extend(result.get("deferred_items", []))
    merged["deferred_items"] = deduplicate_items(all_deferred, ["item"])

    # 미해결 질문 통합 (question으로 중복 제거)
    all_questions = []
    for result in results_list:
        all_questions.extend(result.get("open_questions", []))
    merged["open_questions"] = deduplicate_items(all_questions, ["question"])

    return merged



def print_section(title: str, char: str = "="):
    width = 60
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def print_action_items(items: list):
    for i, item in enumerate(items, 1):
        confidence = item.get("confidence", "unknown")
        conf_emoji = "🟢" if confidence == "high" else "🟡" if confidence == "medium" else "🔴"
        print(f"\n  [{i}] {conf_emoji} {item.get('task', 'N/A')}")
        print(f"      담당자  : {item.get('owner', 'unknown')}")
        print(f"      마감일  : {item.get('deadline', 'unknown')}")
        print(f"      신뢰도  : {confidence}")
        print(f"      근거    : \"{item.get('evidence_quote', 'N/A')}\"")
        if item.get("notes"):
            print(f"      비고    : {item['notes']}")


def print_deferred_items(items: list):
    for i, item in enumerate(items, 1):
        print(f"\n  [{i}] {item.get('item', 'N/A')}")
        print(f"      이유    : {item.get('reason', 'N/A')}")
        print(f"      근거    : \"{item.get('evidence_quote', 'N/A')}\"")


def print_open_questions(items: list):
    for i, item in enumerate(items, 1):
        print(f"\n  [{i}] {item.get('question', 'N/A')}")
        print(f"      제기자  : {item.get('raised_by', 'unknown')}")
        print(f"      근거    : \"{item.get('evidence_quote', 'N/A')}\"")


def print_validation_results(results: list):
    for item in results:
        status = item.get("status", "unknown")
        emoji = "✅" if status == "verified" else "❌" if status == "failed" else "⚠️"
        print(f"\n  {emoji} [{status.upper()}] {item.get('task', 'N/A')}")
        checks = item.get("checks", {})
        for check_name, check_result in checks.items():
            mark = "✓" if check_result.get("passed") else "✗"
            print(f"      {mark} {check_name}: {check_result.get('detail', '')}")


def main():
    parser = argparse.ArgumentParser(
        description="한국어 회의록에서 액션 아이템을 추출합니다."
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        default="meeting_transcript.md",
        help="회의록 파일 경로 (기본값: meeting_transcript.md)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="JSON 결과 저장 경로 (예: output.json)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="청크 크기 (글자, 기본값: 5000)",
    )
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다 → {transcript_path}", file=sys.stderr)
        sys.exit(1)

    transcript = transcript_path.read_text(encoding="utf-8")

    print(f"\n📄 회의록 로드 완료: {transcript_path} ({len(transcript)} 글자)")

    # 청킹 필요 여부 판단
    chunks = chunk_transcript_by_speaker(transcript, chunk_size=args.chunk_size)
    if len(chunks) > 1:
        print(f"📋 대규모 회의록 감지: {len(chunks)}개 청크로 분할 처리")

    print("🤖 LLM 분석 중...")

    # Step 1: 청크별 LLM 추출
    results_list = []
    for i, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            print(f"   [{i}/{len(chunks)}] 청크 처리 중...")
        try:
            result = extract_action_items(chunk)
            results_list.append(result)
        except Exception as e:
            print(f"\n❌ LLM 호출 실패 (청크 {i}): {e}", file=sys.stderr)
            print("OPENAI_API_KEY가 설정되어 있는지 확인해주세요.", file=sys.stderr)
            sys.exit(1)

    # Step 2: 결과 통합 및 중복 제거
    result = merge_results(results_list)
    action_items = result.get("action_items", [])
    deferred_items = result.get("deferred_items", [])
    open_questions = result.get("open_questions", [])

    # Step 3: Deterministic rule 검증
    validation_results = validate_with_rules(transcript, action_items)

    # Step 4: 결과 출력
    print_section("액션 아이템")
    if action_items:
        print_action_items(action_items)
    else:
        print("  추출된 액션 아이템이 없습니다.")

    print_section("보류 / 비목표 항목", "-")
    if deferred_items:
        print_deferred_items(deferred_items)
    else:
        print("  보류 항목이 없습니다.")

    print_section("미해결 질문 / 애매한 부분", "-")
    if open_questions:
        print_open_questions(open_questions)
    else:
        print("  미해결 질문이 없습니다.")

    print_section("Deterministic Rule 검증 결과")
    print("  (LLM 출력을 원문 텍스트로 교차 검증)")
    print_validation_results(validation_results)

    # 최소 요건 smoke check
    print_section("Smoke Check", "-")
    checks = [
        ("액션 아이템 4개 이상", len(action_items) >= 4),
        ("보류 항목 3개 이상", len(deferred_items) >= 3),
        ("미해결 질문 1개 이상", len(open_questions) >= 1),
        ("모든 액션 아이템에 evidence_quote 존재",
         all(item.get("evidence_quote") for item in action_items)),
        ("unknown deadline 항목에 low confidence 부여",
         all(
             item.get("confidence") in ("low", "medium")
             for item in action_items
             if item.get("deadline") == "unknown"
         )),
    ]
    all_passed = True
    for label, passed in checks:
        mark = "✅" if passed else "❌"
        print(f"  {mark} {label}")
        if not passed:
            all_passed = False

    print(f"\n  {'🎉 모든 smoke check 통과!' if all_passed else '⚠️  일부 smoke check 실패'}")

    # JSON export
    output_data = {
        "action_items": action_items,
        "deferred_items": deferred_items,
        "open_questions": open_questions,
        "validation": validation_results,
        "smoke_checks": [
            {"label": label, "passed": passed} for label, passed in checks
        ],
    }

    output_path = args.output or "output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 결과 저장 완료: {output_path}\n")


if __name__ == "__main__":
    main()