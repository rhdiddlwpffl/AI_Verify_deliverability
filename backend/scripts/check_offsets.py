"""수동 시험용: API 응답의 start/end가 JavaScript의 text.slice(start, end)와 맞는지 검증한다.

사용: python -X utf8 scripts/check_offsets.py <요청 JSON 파일> <응답 JSON 파일>
"""

import json
import sys
from pathlib import Path

text = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["text"]
resp = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
units = text.encode("utf-16-le")  # JavaScript 문자열과 같은 UTF-16 코드 단위

bad = 0
for c in resp["claims"]:
    js_slice = units[c["start"] * 2 : c["end"] * 2].decode("utf-16-le")
    ok = js_slice == c["text"]
    bad += not ok
    flag = ",".join(c["flags"]) or "-"
    print(f'[{c["idx"]}] {"OK " if ok else "BAD"} {c["claim_type"]:<8} 확인필요={c["check_worthy"]!s:<5} flags={flag}')
    print(f'      {c["text"]}')
    print(f'      이유: {c["reason"]}')
print(f'\n위치 불일치: {bad}개 / 전체 {len(resp["claims"])}개, 모델: {resp["model"]}')
