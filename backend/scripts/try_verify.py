"""수동 시험용: 전체 흐름(분류 → 위키백과 검색 → 근거 비교)을 실행하고 결과와 토큰 사용량을 출력한다.

실행 (backend 폴더에서):  .venv\\Scripts\\python -X utf8 scripts\\try_verify.py [텍스트 파일]
주의: Claude API를 두 종류(분류, 비교) 호출하므로 비용이 든다.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.pipeline import analyze_text  # noqa: E402

SAMPLE = Path(__file__).parent / "payloads" / "sample2.txt"

STATUS_LABEL = {
    "supported": "검색된 출처에서 뒷받침하는 내용 발견",
    "contradicted": "검색된 출처와 상충하는 내용 발견",
    "mixed": "출처 간 내용이 엇갈림",
    "insufficient": "근거 부족",
    "search_failed": "검색 실패",
    "unverified": "검증하지 못함",
    "not_checkable": "검증 대상 아님",
}

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE
    text = path.read_text(encoding="utf-8")

    started = time.time()
    outcome = analyze_text(text)
    elapsed = time.time() - started

    for c in outcome.classification.claims:
        v = outcome.verification[c.sentence.idx]
        if v.status == "not_checkable":
            continue
        print(f"[{c.sentence.idx}] {c.sentence.text}")
        print(f"     상태: {STATUS_LABEL[v.status]} ({v.status}) | 근거 강도: {v.confidence} | 오류: {v.error}")
        print(f"     요약: {v.rationale}")
        ev = outcome.evidence[c.sentence.idx]
        for i, r in enumerate(ev.results):
            if v.source_verdicts:
                sv = v.source_verdicts[i]
                extra = f' 인용="{sv.quote}"' if sv.quote else ""
                down = " [인용 확인 불가로 제외됨]" if sv.downgraded else ""
                print(f"       - {sv.stance:<11} {r.title}{down}{extra}")
            else:
                print(f"       - (비교 안 됨) {r.title}")

    cu, ju = outcome.classification.usage, outcome.judge_usage
    print(f"\n소요 시간 {elapsed:.1f}초")
    print(f"분류 [{settings.extract_model}] 토큰: 입력 {cu.input_tokens:,} / 출력 {cu.output_tokens:,}")
    print(f"비교 [{settings.judge_model}] 토큰: 입력 {ju.input_tokens:,} / 출력 {ju.output_tokens:,}")
