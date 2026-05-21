#!/usr/bin/env python3
"""
회의록 액션 아이템 추출기 CLI
Usage: python main.py <meeting_transcript.md> [--output output.json]
"""

import argparse
import json
import sys
from pathlib import Path

from extractor import extract_action_items
from validator import validate_with_rules


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
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다 → {transcript_path}", file=sys.stderr)
        sys.exit(1)

    transcript = transcript_path.read_text(encoding="utf-8")

    print(f"\n📄 회의록 로드 완료: {transcript_path} ({len(transcript)} 글자)")
    print("🤖 LLM 분석 중...")

    # Step 1: LLM 추출
    try:
        result = extract_action_items(transcript)
    except Exception as e:
        print(f"\n❌ LLM 호출 실패: {e}", file=sys.stderr)
        print("OPENAI_API_KEY가 설정되어 있는지 확인해주세요.", file=sys.stderr)
        sys.exit(1)

    action_items = result.get("action_items", [])
    deferred_items = result.get("deferred_items", [])
    open_questions = result.get("open_questions", [])

    # Step 2: Deterministic rule 검증
    validation_results = validate_with_rules(transcript, action_items)

    # Step 3: 결과 출력
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