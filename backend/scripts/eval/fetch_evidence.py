"""평가 세트의 정답 검색어로 위키백과 발췌문을 가져와 캐시한다. (무료, Claude 호출 없음)
두 모델이 '완전히 같은 발췌문'을 보게 하려고 한 번만 가져와 파일로 고정한다.

실행 (backend 폴더에서):  .venv\\Scripts\\python -X utf8 scripts\\eval\\fetch_evidence.py [--show]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.searcher import get_provider  # noqa: E402

HERE = Path(__file__).parent
dataset = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
provider = get_provider()

cache: dict[str, list[dict]] = {}
for item in dataset["checkable"]:
    query = item["query"]
    if query not in cache:
        cache[query] = [
            {"title": r.title, "url": r.url, "snippet": r.snippet, "source": r.source} for r in provider.search(query)
        ]

(HERE / "evidence_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"검색어 {len(cache)}개의 발췌문을 evidence_cache.json에 저장했습니다.")

if "--show" in sys.argv:
    for item in dataset["checkable"]:
        print(f"\n[{item['id']}] ({item['expected']}) {item['sentence']}")
        for i, r in enumerate(cache[item["query"]]):
            print(f"   {i}. {r['title']}: {r['snippet']}")
