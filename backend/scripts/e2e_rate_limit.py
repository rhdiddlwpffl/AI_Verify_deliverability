"""수동 시험용: 실행 중인 서버로 호출 횟수 제한을 끝까지 확인한다.

서버는 비용이 들지 않도록 '잘못된 ANTHROPIC_API_KEY'로 띄운다. 요청은 횟수 확인을 통과한 뒤
Claude 인증 단계(502 llm_auth_error)에서 거절되므로, 한도 로직만 검증되고 토큰은 쓰이지 않는다.

사용: python -X utf8 scripts/e2e_rate_limit.py <시나리오> <서버 주소>
  minute : 분당 한도, X-Forwarded-For 위조 방어, 잘못된 입력은 횟수 미소모, 기록 조회 한도
  daily  : IP별 24시간 한도, 전체 24시간 한도 (이어서 서버를 재시작하고 same-after-restart 실행)
  after-restart : 재시작 후에도 한도가 유지되는지
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

scenario, base = sys.argv[1], sys.argv[2].rstrip("/")
TEXT = (Path(__file__).parent / "payloads" / "normal.json").read_text(encoding="utf-8")
failed = 0


def call(method, path, xff=None, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if xff:
        headers["X-Forwarded-For"] = xff
    if token:
        headers["X-Anon-Token"] = token
    data = body.encode("utf-8") if isinstance(body, str) else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8")), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8")), e.headers


def analyze(xff, text_json=TEXT):
    status, body, headers = call("POST", "/analyses", xff=xff, body=text_json)
    return status, (body.get("error") or {}).get("code"), headers


def check(name, ok, detail=""):
    global failed
    print(("PASS" if ok else "FAIL"), name, detail)
    failed += not ok


ADMITTED = (502, "llm_auth_error")  # 횟수 확인을 통과했고, 가짜 키라서 Claude 인증에서 거절됨


def expect(name, result, status, code):
    ok = (result[0], result[1]) == (status, code)
    check(name, ok, f"(HTTP {result[0]}, {result[1]})")
    return result


def real(n):
    return f"198.51.100.{n}"


if scenario == "minute":
    # 가짜 헤더로 맨 왼쪽 값을 바꿔도 '실제 클라이언트'(오른쪽 값)는 같다
    for i in range(3):
        expect(f"{i + 1}번째 요청은 통과", analyze(f"9.9.9.{i}, {real(1)}"), *ADMITTED)
    blocked = expect("4번째는 분당 한도", analyze(f"1.2.3.4, {real(1)}"), 429, "rate_limited")
    check("Retry-After 헤더가 있음", blocked[2].get("Retry-After", "").isdigit() and int(blocked[2]["Retry-After"]) > 0, f"({blocked[2].get('Retry-After')}초)")
    expect("맨 왼쪽 값을 계속 바꿔도 우회되지 않음", analyze(f"7.7.7.7, {real(1)}"), 429, "rate_limited")
    expect("다른 실제 클라이언트는 영향 없음", analyze(f"1.2.3.4, {real(2)}"), *ADMITTED)

    for i in range(5):
        r = analyze(real(3), json.dumps({"text": "   \n "}))
        if i == 0:
            expect("빈 입력은 422", r, 422, "empty_input")
    for i in range(3):
        expect(f"빈 입력 5번 뒤에도 {i + 1}번째 요청 통과(횟수 미소모)", analyze(real(3)), *ADMITTED)
    expect("분석 3번 뒤에는 한도", analyze(real(3)), 429, "rate_limited")

    token = "a" * 64
    statuses = [call("GET", "/analyses", xff=real(4), token=token)[0] for _ in range(4)]
    check("기록 조회는 3번 통과 후 4번째가 429", statuses == [200, 200, 200, 429], f"({statuses})")

elif scenario == "daily":
    for i in range(3):
        expect(f"A의 {i + 1}번째 요청 통과", analyze(real(1)), *ADMITTED)
    r = expect("A의 4번째는 24시간 한도", analyze(real(1)), 429, "daily_limit_reached")
    ra = int(r[2].get("Retry-After", "0"))
    check("Retry-After가 약 24시간 이내", 0 < ra <= 86400, f"({ra}초)")
    for i in range(2):
        expect(f"B의 {i + 1}번째 요청 통과", analyze(real(2)), *ADMITTED)
    expect("서비스 전체 한도(5회) 도달: 새 사용자 C도 거절", analyze(real(3)), 429, "service_daily_limit")

elif scenario == "after-restart":
    # 전체 한도가 이미 가득 찬 상태라, A에게도 전체 한도 메시지가 먼저 나간다. (전체 확인이 IP별 확인보다 먼저)
    expect("서버를 재시작해도 전체 한도 유지: A도 거절", analyze(real(1)), 429, "service_daily_limit")
    expect("서버를 재시작해도 전체 한도 유지: 새 사용자 D도 거절", analyze(real(4)), 429, "service_daily_limit")

elif scenario == "ip-day":
    # 전체 한도는 높게 두고 IP별 한도만 확인한다.
    for i in range(3):
        expect(f"A의 {i + 1}번째 요청 통과", analyze(real(1)), *ADMITTED)
    expect("A의 4번째는 24시간 한도", analyze(real(1)), 429, "daily_limit_reached")
    expect("B는 영향 없음", analyze(real(2)), *ADMITTED)

elif scenario == "ip-day-after-restart":
    expect("서버를 재시작해도 A는 여전히 IP별 24시간 한도", analyze(real(1)), 429, "daily_limit_reached")
    expect("서버를 재시작해도 B는 자기 한도(3회) 안에서 통과", analyze(real(2)), *ADMITTED)
    expect("새 사용자 E는 통과", analyze(real(5)), *ADMITTED)

print("\n실패:", failed)
sys.exit(1 if failed else 0)
