from __future__ import annotations

from typing import Any

from .retrieval import search_knowledge_bank


def _unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = str(value or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(str(value).strip())
    return result


def build_review_units(clause_map: dict) -> list[dict]:
    clauses = list(clause_map.get("clauses", []) or [])
    by_id = {str(c.get("clause_id", "")): c for c in clauses}
    graph = list(clause_map.get("dependency_graph", []) or [])
    units = []
    for clause in clauses:
        clause_id = str(clause.get("clause_id", ""))
        related_ids = list(clause.get("related_clause_ids", []) or [])
        for edge in graph:
            if edge.get("source_clause_id") == clause_id:
                related_ids.append(str(edge.get("target_clause_id", "")))
            elif edge.get("target_clause_id") == clause_id:
                related_ids.append(str(edge.get("source_clause_id", "")))
        related = [by_id[x] for x in _unique(related_ids) if x in by_id]
        units.append({
            "target_clause": clause,
            "related_clauses": related[:12],
            "definitions": [
                d for d in clause_map.get("definitions", []) or []
                if str(d.get("term", "")) in set(clause.get("defined_terms_used", []) or [])
            ][:30],
            "missing_dependencies": [
                x for x in clause_map.get("missing_dependencies", []) or []
                if clause_id in str(x)
            ],
        })
    return units


def retrieve_authorities_for_unit(unit: dict, confirmed_profile: dict, limit: int = 7) -> list[dict]:
    clause = unit.get("target_clause", {})
    query = (
        f"Saudi law in knowledge base only. Agreement type: {confirmed_profile.get('agreement_type')}. "
        f"Relationship: {confirmed_profile.get('relationship_type')}. Represented party: "
        f"{confirmed_profile.get('represented_party')}. Clause category: {clause.get('category')}. "
        f"Clause heading: {clause.get('heading')}. Clause wording: {str(clause.get('full_text',''))[:3500]}. "
        "Retrieve rules relevant to validity, mandatory requirements, enforceability, regulatory duties, "
        "risk allocation, disclosure, termination, liability, and required protections only when applicable."
    )
    unique: dict[str, dict] = {}
    for hit in search_knowledge_bank(query=query, limit=limit):
        node_id = str(hit.get("node_id", "") or "").strip()
        if node_id:
            unique[node_id] = hit
    return list(unique.values())
