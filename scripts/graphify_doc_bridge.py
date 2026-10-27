#!/usr/bin/env python3
"""graphify 문서↔코드 브리지 (Docs ↔ Code bridge for graphify-out/graph.json).

graphify 의 AST 추출은 코드만, 시맨틱 추출은 문서만 본다. 둘의 노드 ID 체계가 달라
문서 레이어가 코드 그래프와 끊긴 섬으로 남는다(측정: giant component 79.6%,
code↔doc 엣지 90개 — 전부 package.json 자기참조). 그 결과 "이 스펙을 구현한 코드가
무엇인가" 를 그래프가 구조적으로 답하지 못한다.

이 스크립트는 문서 본문에 실제로 등장하는 코드 심볼을 찾아 `mentions` 엣지를 붙인다.
LLM 없이 결정적으로 동작하므로 `graphify update` 뒤에 매번 다시 돌리면 된다.

희소성(IDF) 상위 TOP_K 개만 연결한다 — 전부 연결하면 문서 노드가 out-degree 155 의
새 허브가 되어 BFS 폭발을 되살린다(TOP_K=5: giant 94.6%, 문서 max out-degree 15).

사용:
    python3 scripts/graphify_doc_bridge.py            # graph.json 에 브리지 적용
    python3 scripts/graphify_doc_bridge.py --selftest # 자체 검사
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

GRAPH = Path("graphify-out/graph.json")
DOC_TYPES = ("document", "concept")
RELATION = "mentions"
TOP_K = 5
MIN_SYMBOL_LEN = 6
SYMBOL_RE = re.compile(rf"[A-Za-z_][A-Za-z0-9_]{{{MIN_SYMBOL_LEN - 1},}}")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def unique_code_symbols(nodes: list[dict]) -> dict[str, str]:
    """label -> node id, 코드 노드 중 라벨이 전역 유일한 것만.

    라벨이 중복인 심볼(`.__init__()` 169개 등)은 어느 노드를 가리키는지 결정할 수
    없으므로 버린다. 잘못된 엣지를 만드는 것보다 안 만드는 편이 낫다.
    """
    by_label: dict[str, list[str]] = collections.defaultdict(list)
    for n in nodes:
        if n.get("file_type") != "code":
            continue
        label = (n.get("label") or "").strip().rstrip("()")
        if len(label) >= MIN_SYMBOL_LEN and IDENT_RE.fullmatch(label):
            by_label[label].append(n["id"])
    return {label: ids[0] for label, ids in by_label.items() if len(ids) == 1}


def bridge_edges(nodes: list[dict], read_text) -> list[dict]:
    symbols = unique_code_symbols(nodes)
    doc_nodes_by_file: dict[str, list[dict]] = collections.defaultdict(list)
    for n in nodes:
        if n.get("file_type") in DOC_TYPES and n.get("source_file"):
            doc_nodes_by_file[n["source_file"]].append(n)

    mentions: dict[str, set[str]] = {}
    for src in doc_nodes_by_file:
        text = read_text(src)
        if text is None:
            continue
        mentions[src] = {t for t in set(SYMBOL_RE.findall(text)) if t in symbols}

    # 문서 코퍼스 전체에서 드물게 쓰인 심볼일수록 강한 신호.
    doc_freq = collections.Counter(t for found in mentions.values() for t in found)

    edges: list[dict] = []
    for src, found in mentions.items():
        # 파일당 대표 노드 하나에만 건다. 파일의 모든 문서 노드에 걸면 엣지가
        # 문서 노드 수만큼 곱해지고 허브가 생긴다.
        lead = min(doc_nodes_by_file[src], key=lambda n: str(n.get("source_location")))
        for symbol in sorted(found, key=lambda t: (doc_freq[t], t))[:TOP_K]:
            edges.append(
                {
                    "source": lead["id"],
                    "target": symbols[symbol],
                    "relation": RELATION,
                    "confidence": "INFERRED",
                    "confidence_score": 0.6,
                    "weight": 1.0,
                    "source_file": src,
                    "source_location": "L1",
                    "_origin": "doc_bridge",
                }
            )
    return edges


def apply(graph_path: Path = GRAPH) -> int:
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    node_ids = {n["id"] for n in nodes}

    def read(src: str) -> str | None:
        p = Path(src)
        return p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else None

    # 재실행 가능하도록 이전 브리지를 먼저 걷어낸다.
    kept = [link for link in data["links"] if link.get("_origin") != "doc_bridge"]
    new = [
        e for e in bridge_edges(nodes, read) if e["source"] in node_ids and e["target"] in node_ids
    ]
    data["links"] = kept + new
    graph_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"doc bridge: {len(new)} mentions edges ({len(data['links'])} links total)")
    return len(new)


def selftest() -> None:
    nodes = [
        {"id": "c1", "file_type": "code", "label": "RunAggregate", "source_file": "app/a.py"},
        {"id": "c2", "file_type": "code", "label": "Everywhere", "source_file": "app/b.py"},
        {"id": "c3", "file_type": "code", "label": "dup_name", "source_file": "app/c.py"},
        {"id": "c4", "file_type": "code", "label": "dup_name", "source_file": "app/d.py"},
        {
            "id": "d1",
            "file_type": "document",
            "label": "spec",
            "source_file": "docs/x.md",
            "source_location": "L1",
        },
        {
            "id": "d2",
            "file_type": "document",
            "label": "sec",
            "source_file": "docs/x.md",
            "source_location": "L9",
        },
        {
            "id": "d3",
            "file_type": "document",
            "label": "other",
            "source_file": "docs/y.md",
            "source_location": "L1",
        },
    ]
    texts = {
        "docs/x.md": "RunAggregate 를 쓴다. Everywhere 도. dup_name 도 나온다. short 는 무시.",
        "docs/y.md": "Everywhere 만 언급.",
    }
    edges = bridge_edges(nodes, texts.get)
    pairs = {(e["source"], e["target"]) for e in edges}

    assert ("d1", "c1") in pairs, "문서 본문의 유일 심볼이 연결되어야 한다"
    assert not any(s == "d2" for s, _ in pairs), "파일당 대표 노드에만 걸려야 한다"
    assert not any(t in ("c3", "c4") for _, t in pairs), "중복 라벨 심볼은 제외되어야 한다"
    assert ("d3", "c2") in pairs, "다른 문서도 각자 연결되어야 한다"
    assert all(e["relation"] == RELATION for e in edges)

    # IDF 상한: 희소 심볼이 흔한 심볼보다 먼저 선택된다.
    many = [
        {"id": f"c{i}", "file_type": "code", "label": f"Symbol{i:03d}", "source_file": "app/z.py"}
        for i in range(20)
    ]
    doc = [
        {
            "id": "dz",
            "file_type": "document",
            "label": "z",
            "source_file": "docs/z.md",
            "source_location": "L1",
        }
    ]
    body = " ".join(f"Symbol{i:03d}" for i in range(20))
    capped = bridge_edges(many + doc, {"docs/z.md": body}.get)
    assert len(capped) == TOP_K, f"파일당 {TOP_K} 개로 제한되어야 한다 (got {len(capped)})"

    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        apply()
