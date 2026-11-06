"""수동 시험용: 실행 중인 서버(localhost:8000)로 저장 → 목록 → 상세 → 접근 제어 → 삭제를 끝까지 확인한다.

실행 (서버를 켠 상태에서, backend 폴더에서):  .venv\\Scripts\\python -X utf8 scripts\\e2e_history.py
주의: 실제 분석을 1회 실행하므로 Claude API 비용이 든다. 끝나면 시험 데이터는 모두 삭제한다.
"""

import hashlib
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://localhost:8000"
TEXT = (Path(__file__).parent / "payloads" / "sample2.txt").read_text(encoding="utf-8")
failed = 0


def call(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Anon-Token"] = token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def check(name, ok, detail=""):
    global failed
    print(("PASS" if ok else "FAIL"), name, detail)
    failed += not ok


def db_count(sql, **params):
    from sqlalchemy import text

    from app.db.session import get_engine

    with get_engine().connect() as c:
        return c.execute(text(sql), params).scalar()


token = secrets.token_hex(32)
other = secrets.token_hex(32)

started = time.time()
status, posted = call("POST", "/analyses", token, {"text": TEXT, "save": True})
check("저장 요청 분석", status == 200 and posted.get("save_status") == "saved", f"(HTTP {status}, {time.time() - started:.1f}초, save_status={posted.get('save_status')})")
analysis_id = posted.get("analysis_id")
check("analysis_id 반환", bool(analysis_id))

status, items = call("GET", "/analyses", token)
check("목록에 내 기록 1건", status == 200 and [i["id"] for i in items] == [analysis_id], f"(preview={items[0]['preview']!r}, 문장 {items[0]['sentence_count']}, 확인 필요 {items[0]['check_worthy_count']}, 상태 {items[0]['status_counts']})")

status, detail = call("GET", f"/analyses/{analysis_id}", token)
restored = detail["result"]
original = {k: v for k, v in posted.items() if k not in ("save_status", "analysis_id")}
restored_cmp = {k: v for k, v in restored.items() if k not in ("save_status", "analysis_id")}
check("저장 후 읽은 결과가 방금 받은 응답과 완전히 같음", status == 200 and restored_cmp == original and detail["text"] == TEXT)

status, err = call("GET", f"/analyses/{analysis_id}", other)
check("다른 사용자는 404", status == 404 and err["error"]["code"] == "not_found", f"({err['error']['code']})")
status, err = call("GET", f"/analyses/{analysis_id}")
check("토큰 없으면 401", status == 401 and err["error"]["code"] == "missing_token")
status, err = call("GET", "/analyses", "bad token!")
check("형식이 이상한 토큰은 400", status == 400 and err["error"]["code"] == "invalid_token")
status, err = call("DELETE", f"/analyses/{analysis_id}", other)
check("다른 사용자는 삭제도 불가(404)", status == 404)
status, items = call("GET", "/analyses", other)
check("다른 사용자의 목록은 비어 있음", status == 200 and items == [])

sha = hashlib.sha256(token.encode()).hexdigest()
check("DB에 토큰 원본이 없음", db_count("select count(*) from analyses where anon_token_hash = :t", t=token) == 0)
check("DB에는 SHA-256 해시만 있음", db_count("select count(*) from analyses where anon_token_hash = :t", t=sha) == 1)

status, not_saved = call("POST", "/analyses", token, {"text": "에펠탑은 1889년에 지어졌다.", "save": False})
check("save=false는 저장 안 함", status == 200 and not_saved["save_status"] == "not_requested" and not_saved["analysis_id"] is None)
status, items = call("GET", "/analyses", token)
check("저장 안 한 분석은 목록에 없음", len(items) == 1)

status, res = call("DELETE", f"/analyses/{analysis_id}", token)
check("내 기록 삭제", status == 200 and res == {"deleted": 1})
status, err = call("GET", f"/analyses/{analysis_id}", token)
check("삭제 후 조회는 404", status == 404)
status, res = call("DELETE", "/analyses", token)
check("전체 삭제(남은 것 없음)", status == 200 and res == {"deleted": 0})
check("하위 데이터와 출처까지 정리됨", all(db_count(f"select count(*) from {t}") == 0 for t in ("analyses", "claims", "claim_sources", "verifications", "sources")))

print("\n실패:", failed)
sys.exit(1 if failed else 0)
