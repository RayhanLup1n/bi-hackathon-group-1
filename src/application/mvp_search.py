"""
Keyword search engine for MVP recommendations.

Pure Python, no database, no NLP libraries. Searches across in-memory
recommendation dicts produced by the orchestrator's get_priorities().

Scoring strategy (YAGNI — no fuzzy matching, no embeddings):
  - Exact match on commodity name: +10
  - Substring match on commodity/region: +5
  - Match on risk_level: +3
  - Match in evidence label/value: +3
  - Match in missing_information: +2
  - Match on price_condition: +2

Returns ranked results with relevance_score per item.
"""
from __future__ import annotations

from typing import Any


def search_recommendations(
    priorities: list[dict[str, Any]],
    query: str,
    max_results: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search across recommendation dicts by keyword tokens.

    Args:
        priorities: List of recommendation dicts (from get_priorities / model_dump).
        query: Free-text search query. Split by whitespace, matched case-insensitively.
        max_results: Cap results at this count (applied after offset).
        offset: Skip first N results for pagination.

    Returns:
        Dict with keys: results (list[dict]), total (int), query (str), offset (int).
        Each result dict has: recommendation_id, commodity, region, risk_level,
        display_priority_score, relevance_score, matched_terms.
    """
    query_norm = query.strip()
    if not query_norm:
        return {"results": [], "total": 0, "query": query, "offset": offset}

    tokens = [t.lower() for t in query_norm.split()]

    scored: list[dict[str, Any]] = []
    for rec in priorities:
        score = 0
        matched: list[str] = []

        commodity_lower = rec.get("commodity", "").lower()
        region_lower = rec.get("region", "").lower()
        risk_lower = rec.get("risk_level", "").lower()
        price_condition_lower = rec.get("price_condition", "").lower()

        for token in tokens:
            # Exact commodity match
            if token == commodity_lower:
                score += 10
                matched.append(f"komoditas:{token}")
            elif token in commodity_lower:
                score += 5
                matched.append(f"komoditas:~{token}")

            # Region match
            if token in region_lower and f"wilayah:{token}" not in matched:
                score += 5
                matched.append(f"wilayah:{token}")

            # Risk level match
            if token == risk_lower:
                score += 3
                matched.append(f"risiko:{token}")

            # Price condition match
            if token in price_condition_lower:
                score += 2
                matched.append(f"kondisi:{token}")

            # Search evidence labels and values
            for group in ("observed_facts", "model_outputs", "possible_factors"):
                for item in rec.get(group, []):
                    label_lower = item.get("label", "").lower()
                    value_lower = str(item.get("value", "")).lower()
                    if token in label_lower:
                        score += 3
                        matched.append(f"evidence:{token}")
                    if token in value_lower and f"evidence:{token}" not in matched:
                        score += 3
                        matched.append(f"evidence:{token}")

            # Search missing_information strings
            for missing in rec.get("missing_information", []):
                if token in missing.lower():
                    score += 2
                    matched.append(f"missing:{token}")

            # Search next_step
            next_step = (rec.get("next_step") or "").lower()
            if token in next_step and f"next_step:{token}" not in matched:
                score += 2
                matched.append(f"next_step:{token}")

        if score > 0:
            scored.append({
                "recommendation_id": rec.get("recommendation_id", ""),
                "commodity": rec.get("commodity", ""),
                "region": rec.get("region", ""),
                "risk_level": rec.get("risk_level", ""),
                "display_priority_score": rec.get("display_priority_score", 0),
                "relevance_score": score,
                "matched_terms": matched,
            })

    # Sort: relevance desc, then priority score desc
    scored.sort(
        key=lambda r: (r["relevance_score"], r["display_priority_score"]),
        reverse=True,
    )

    total = len(scored)

    # Paginate
    paginated = scored[offset:offset + max_results] if offset < total else []

    return {
        "results": paginated,
        "total": total,
        "query": query,
        "offset": offset,
    }
