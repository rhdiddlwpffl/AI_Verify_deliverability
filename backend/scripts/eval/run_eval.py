"""분류/근거 비교 모델 평가 (실제 Claude 호출, 비용 발생).

기본은 '예상 비용만 출력'한다. 실제로 호출하려면 --yes를 붙인다.

  .venv\\Scripts\\python -X utf8 scripts\\eval\\run_eval.py --stage all --runs 3            (예상 비용)
  .venv\\Scripts\\python -X utf8 scripts\\eval\\run_eval.py --stage all --runs 3 --yes      (실제 실행)

먼저 scripts\\eval\\fetch_evidence.py를 실행해 발췌문 캐시를 만들어야 한다. (두 모델이 같은 발췌문을 본다)
정답(expected)은 '발췌문(도입부 약 400자)만 보고' 사람이 정한 값이라 주관이 섞일 수 있다.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402
from app.services.claim_extractor import classify_sentences  # noqa: E402
from app.services.searcher import SearchRateLimitedError, SearchResult, get_provider  # noqa: E402
from app.services.sentence_splitter import split_sentences  # noqa: E402
from app.services.verifier import judge_claims  # noqa: E402

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "results"

# 가격표(100만 토큰당 USD, 입력/출력). 2026-10-06 기준 캐시된 값이라 실제 청구와 다를 수 있다.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}

dataset = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
CHECKABLE, NONCHECKABLE = dataset["checkable"], dataset["noncheckable"]


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = PRICES[model]
    return tokens_in * p_in / 1e6 + tokens_out * p_out / 1e6


# ------------------------------------------------------------------ 검색 (캐시 + 한도 대응)

_search_cache: dict[str, list[str]] = {}


def search_titles(query: str) -> list[str]:
    """같은 검색어는 한 번만 검색한다. 위키백과가 요청 한도(429)를 걸면 기다렸다가 다시 시도한다."""
    if query in _search_cache:
        return _search_cache[query]
    for wait in (4, 8, 16, 0):
        try:
            time.sleep(0.8)  # 연달아 보내지 않는다 (위키백과 429 방지)
            _search_cache[query] = [r.title for r in get_provider().search(query)]
            return _search_cache[query]
        except SearchRateLimitedError:
            if wait == 0:
                raise
            print(f"   (위키백과 요청 한도에 걸려 {wait}초 기다립니다)")
            time.sleep(wait)
    raise AssertionError("도달할 수 없음")


# ------------------------------------------------------------------ 분류 평가


def classification_eval(model: str, runs: int) -> dict:
    # 문장마다 한 줄. (확인 대상과 아닌 문장을 섞어서 한 번에 분류한다 = 실제 사용과 같은 방식)
    lines = [i["sentence"] for i in CHECKABLE] + [i["sentence"] for i in NONCHECKABLE]
    lines = lines[::2] + lines[1::2]  # 순서를 섞어서 앞쪽/뒤쪽 편향을 줄인다
    sentences = split_sentences("\n".join(lines))
    assert len(sentences) == len(lines), f"문장 분리 결과가 평가 세트와 다릅니다: {len(sentences)} != {len(lines)}"

    out = {"model": model, "runs": [], "tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
    settings.extract_model = model
    for _ in range(runs):
        started = time.time()
        result = classify_sentences(sentences)
        out["seconds"] += time.time() - started
        out["tokens_in"] += result.usage.input_tokens
        out["tokens_out"] += result.usage.output_tokens
        # 분리기가 제목 기호('## ') 같은 것을 떼어 내므로 글자가 아니라 '줄 순서'로 원래 문장과 대응시킨다.
        by_text = {line: claim for line, claim in zip(lines, result.claims, strict=True)}

        tp = sum(by_text[i["sentence"]].check_worthy for i in CHECKABLE)  # 확인 대상을 확인 대상으로
        tn = sum(not by_text[i["sentence"]].check_worthy for i in NONCHECKABLE)  # 아닌 것을 아니라고
        wrong_non = [i["id"] for i in NONCHECKABLE if by_text[i["sentence"]].check_worthy]
        missed = [i["id"] for i in CHECKABLE if not by_text[i["sentence"]].check_worthy]

        query_hits, query_total, queries = 0, 0, {}
        for i in CHECKABLE:
            c = by_text[i["sentence"]]
            queries[i["id"]] = c.search_query
            if not i["titles"] or not c.check_worthy:
                continue
            query_total += 1
            found = search_titles(c.search_query)
            query_hits += any(t in found for t in i["titles"])
        out["runs"].append(
            {"recall": tp, "recall_total": len(CHECKABLE), "specificity": tn, "specificity_total": len(NONCHECKABLE),
             "wrongly_checkable": wrong_non, "missed": missed, "query_hits": query_hits, "query_total": query_total,
             "queries": queries}
        )
    return out


# ------------------------------------------------------------------ 근거 비교 평가


def load_items() -> list[tuple[int, str, list[SearchResult]]]:
    cache = json.loads((HERE / "evidence_cache.json").read_text(encoding="utf-8"))
    return [
        (n, item["sentence"], [SearchResult(r["title"], r["url"], r["snippet"], r["source"]) for r in cache[item["query"]]])
        for n, item in enumerate(CHECKABLE)
    ]


def judge_eval(model: str, runs: int) -> dict:
    items = load_items()
    out = {"model": model, "runs": [], "tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
    settings.judge_model = model
    for _ in range(runs):
        started = time.time()
        result = judge_claims(items)
        out["seconds"] += time.time() - started
        out["tokens_in"] += result.usage.input_tokens
        out["tokens_out"] += result.usage.output_tokens
        preds, downgraded, verified_quotes = {}, 0, 0
        for n, item in enumerate(CHECKABLE):
            if n in result.judgments:
                j = result.judgments[n]
                preds[item["id"]] = j.status
                downgraded += sum(v.downgraded for v in j.source_verdicts)
                verified_quotes += sum(bool(v.quote) for v in j.source_verdicts)
            else:
                preds[item["id"]] = "FAILED:" + result.failed.get(n, "?")
        out["runs"].append({"preds": preds, "downgraded": downgraded, "verified_quotes": verified_quotes})
    return out


def judge_metrics(res: dict) -> dict:
    gold = {i["id"]: i["expected"] for i in CHECKABLE if i["expected"] != "ambiguous"}
    runs = res["runs"]
    n_pred = len(gold) * len(runs)
    correct = false_contra = false_support = missed_contra = missed_support = failed = 0
    confusion: Counter = Counter()
    for r in runs:
        for cid, exp in gold.items():
            pred = r["preds"][cid]
            confusion[(exp, pred)] += 1
            failed += pred.startswith("FAILED")
            correct += pred == exp
            false_contra += pred == "contradicted" and exp != "contradicted"
            false_support += pred == "supported" and exp != "supported"
            missed_contra += exp == "contradicted" and pred != "contradicted"
            missed_support += exp == "supported" and pred != "supported"
    unstable = sum(len({r["preds"][cid] for r in runs}) > 1 for cid in r_ids(gold))
    return {
        "accuracy": correct / n_pred, "correct": correct, "total": n_pred,
        "false_contradicted": false_contra, "false_supported": false_support,
        "missed_contradiction": missed_contra, "missed_support": missed_support, "failed": failed,
        "unstable_claims": unstable, "claims": len(gold), "confusion": confusion,
        "downgraded": sum(r["downgraded"] for r in runs), "verified_quotes": sum(r["verified_quotes"] for r in runs),
    }


def r_ids(gold: dict) -> list[str]:
    return list(gold)


# ------------------------------------------------------------------ 출력


def estimate(models: list[str], runs: int, stage: str) -> float:
    n_check, n_all = len(CHECKABLE), len(CHECKABLE) + len(NONCHECKABLE)
    total = 0.0
    for m in models:
        if stage in ("classify", "all"):
            total += runs * cost(m, 1_100 + 100 * n_all, 60 * n_all)  # 분류 1회 추정 (고정 입력 약 1,100 + 문장당 약 100 / 출력 문장당 약 60)
        if stage in ("judge", "all"):
            total += runs * cost(m, 1_100 + 1_000 * n_check, 190 * n_check * (2.2 if "haiku" in m else 1))  # 비교 1회 추정 (Haiku는 출력이 더 길었다)
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["classify", "judge", "all"], default="all")
    ap.add_argument("--models", default="claude-haiku-5-5,claude-sonnet-5-5")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--effort", default=None, help="비교(judge) 호출의 추론 강도를 덮어쓴다: low|medium|high|xhigh|max")
    ap.add_argument("--yes", action="store_true", help="실제로 Claude를 호출한다 (비용 발생)")
    args = ap.parse_args()
    if args.effort:
        settings.judge_effort = args.effort
    models = args.models.split(",")

    est = estimate(models, args.runs, args.stage)
    print(f"모델 {models} | 단계 {args.stage} | 반복 {args.runs}회 | 비교 추론 강도 {settings.judge_effort} | 예상 비용 약 ${est:.2f} (추정치)")
    if not args.yes:
        print("실제로 실행하려면 --yes를 붙이세요.")
        return

    RESULTS_DIR.mkdir(exist_ok=True)
    report: dict = {"classify": {}, "judge": {}}
    spent = 0.0

    if args.stage in ("classify", "all"):
        print("\n=== 분류 평가 (확인 대상 구분, 검색어 품질) ===")
        for m in models:
            res = classification_eval(m, args.runs)
            report["classify"][m] = res
            c = cost(m, res["tokens_in"], res["tokens_out"])
            spent += c
            r = res["runs"]
            n = len(r)
            print(f"[{m}] 토큰 입력 {res['tokens_in']:,} / 출력 {res['tokens_out']:,} | 약 ${c:.4f} | {res['seconds'] / n:.1f}초/회")
            print(f"   확인 대상을 확인 대상으로(재현율): {sum(x['recall'] for x in r)}/{sum(x['recall_total'] for x in r)}")
            print(f"   아닌 문장을 아니라고(특이도)   : {sum(x['specificity'] for x in r)}/{sum(x['specificity_total'] for x in r)}")
            print(f"   검색어로 정답 문서를 찾음        : {sum(x['query_hits'] for x in r)}/{sum(x['query_total'] for x in r)}")
            wrong = Counter(w for x in r for w in x["wrongly_checkable"])
            missed = Counter(w for x in r for w in x["missed"])
            if wrong:
                print(f"   확인 대상 아닌데 확인 대상으로 분류: {dict(wrong)}")
            if missed:
                print(f"   확인 대상인데 놓침: {dict(missed)}")

    if args.stage in ("judge", "all"):
        print("\n=== 근거 비교 평가 (같은 발췌문, 정답 대비) ===")
        for m in models:
            res = judge_eval(m, args.runs)
            report["judge"][m] = res
            met = judge_metrics(res)
            res["metrics"] = {k: v for k, v in met.items() if k != "confusion"}
            res["metrics"]["confusion"] = {f"{a}->{b}": n for (a, b), n in met["confusion"].items()}
            c = cost(m, res["tokens_in"], res["tokens_out"])
            spent += c
            n = len(res["runs"])
            print(f"[{m}] 토큰 입력 {res['tokens_in']:,} / 출력 {res['tokens_out']:,} | 약 ${c:.4f} | {res['seconds'] / n:.1f}초/회")
            print(f"   정확도: {met['correct']}/{met['total']} = {met['accuracy']:.0%}")
            print(f"   [심각] 없는 반박을 만듦(false contradicted): {met['false_contradicted']}  | 없는 근거를 만듦(false supported): {met['false_supported']}")
            print(f"   [놓침] 틀린 주장을 못 잡음: {met['missed_contradiction']}  | 맞는 주장의 근거를 못 찾음: {met['missed_support']}  | 비교 실패: {met['failed']}")
            print(f"   인용 검증: 통과 {met['verified_quotes']}건, 근거에서 제외(인용 확인 불가/범위 불일치) {met['downgraded']}건")
            print(f"   회차마다 결과가 달라진 문장: {met['unstable_claims']}/{met['claims']}")

        print("\n--- 문장별 판정 (정답 | 회차별 예측) ---")
        for item in CHECKABLE:
            row = []
            for m in models:
                preds = [r["preds"][item["id"]] for r in report["judge"][m]["runs"]]
                row.append(f"{m.split('-')[1]}:" + ",".join(p[:5] for p in preds))
            print(f"  {item['id']:3} 정답={item['expected'][:5]:5} | " + " | ".join(row) + f"  {item['sentence'][:30]}")

    (RESULTS_DIR / f"eval-{int(time.time())}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n이번 평가의 토큰 기준 추정 비용 합계: 약 ${spent:.3f}")


if __name__ == "__main__":
    main()
