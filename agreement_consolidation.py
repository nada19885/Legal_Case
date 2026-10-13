"""
Hierarchical contract-wide consolidation — Stage 2 of the agreement
clause-map pipeline (see agreement_workbench.extract_clause_map). Takes the
per-page structures from agreement_page_extraction.structure_agreement_pages
and produces the single consolidated clause_map the rest of the agreement
workflow (agreement_retrieval, agreement_analysis, discuss_agreement, and
Legal.js's clause/review tabs) all depend on.

Two stages:
  A. Stitching in code (no LLM): the page structures already carry each
     clause fragment's text and whether it continues from the previous
     page or onto the next one, so fragments are joined in page order.
     (This used to be one LLM call per ~10 pages that re-typed every
     clause; on a 25-page contract those calls ran past the endpoint's
     5-minute limit and failed.) The text stays exactly as read from the
     page, which the review's page marks rely on.
  B. One final LLM call over compact clause summaries (not full text) for
     the package-level dependency graph, missing dependencies,
     cross-document conflicts, contract overview and summary.
Location: lib/python/legal_platform/agreement_consolidation.py
"""

from __future__ import annotations

from typing import Callable

from .agreement_llm import agreement_complete_json
from .context_budget import select_with_char_budget

PACKAGE_SYNTHESIS_PROMPT = """
You are synthesizing the package-level view of a legal agreement from its
already-consolidated clauses. Use only the supplied clause summaries,
definitions, and confirmed classification profile. Do not invent clause
content beyond what is summarized.

Identify:
- dependency_graph: edges between clause_ids that reference or depend on
  each other (e.g. a liability cap clause referencing the indemnity
  clause). relationship is a short label (e.g. "references",
  "limits", "conditions").
- missing_dependencies: clauses that reference a schedule, annex, exhibit,
  or defined term that is not present in the supplied material. Each entry
  must mention the clause_id it affects.
- cross_document_conflicts: contradictions between clauses or between
  separate documents in the package (e.g. master agreement vs. an annex).
- contract_overview: a short structured overview (parties, effective_date,
  term_summary, key_obligations_summary) grounded in the supplied clauses.
- package_summary: a short plain-language summary of the whole package.

Return JSON only:
{
  "dependency_graph": [
    {"source_clause_id": "", "target_clause_id": "", "relationship": ""}
  ],
  "missing_dependencies": [],
  "cross_document_conflicts": [],
  "contract_overview": {
    "parties": "", "effective_date": "", "term_summary": "",
    "key_obligations_summary": ""
  },
  "package_summary": ""
}
""".strip()


def stitch_page_structures(page_structures: list[dict]) -> dict:
    """Join the clause fragments of the page structures, in reading order,
    into whole clauses (same shape the chunk consolidation returned)."""
    pages = sorted((p for p in page_structures or [] if isinstance(p, dict)),
                   key=lambda p: (str(p.get("document_id", "")), int(p.get("page_number", 0) or 0)))
    clauses: list[dict] = []
    definitions: list[dict] = []
    notes: list[str] = []
    open_clause: dict | None = None
    previous_document = None
    for page in pages:
        page_id = str(page.get("page_id", "") or "")
        document = str(page.get("document_id", "") or "")
        if document != previous_document:
            open_clause = None                      # a clause never runs into another document
            previous_document = document
        fragments = [f for f in page.get("clause_fragments") or [] if isinstance(f, dict)]
        for index, fragment in enumerate(fragments):
            text = str(fragment.get("text", "") or "").strip()
            number = str(fragment.get("clause_number", "") or "").strip()
            heading = str(fragment.get("heading", "") or "").strip()
            continues = bool(fragment.get("continues_from_previous_page")) or (
                index == 0 and open_clause is not None and open_clause.get("_open")
                and not number and not heading)
            if continues and index == 0 and open_clause is not None:
                open_clause["full_text"] = (open_clause["full_text"] + "\n" + text).strip()
                if page_id and page_id not in open_clause["source_page_ids"]:
                    open_clause["source_page_ids"].append(page_id)
                open_clause["exceptions_or_carve_outs"] = list(dict.fromkeys(
                    open_clause["exceptions_or_carve_outs"] + list(fragment.get("exceptions_or_carve_outs") or [])))
                for key, value in (("clause_number", number), ("heading", heading),
                                   ("category", str(fragment.get("category", "") or ""))):
                    if not open_clause.get(key) and value:
                        open_clause[key] = value
                current = open_clause
            else:
                if fragment.get("continues_from_previous_page") and index == 0:
                    notes.append("Page {} starts in the middle of a clause whose start was not found.".format(
                        page.get("page_number", "")))
                current = {
                    "clause_number": number, "heading": heading, "full_text": text,
                    "category": str(fragment.get("category", "") or "other"),
                    "exceptions_or_carve_outs": list(fragment.get("exceptions_or_carve_outs") or []),
                    "source_page_ids": [page_id] if page_id else [],
                    "continues_from_previous_chunk": False, "continues_into_next_chunk": False,
                }
                clauses.append(current)
            current["_open"] = bool(fragment.get("continues_on_next_page"))
            open_clause = current
        if not fragments:
            open_clause = open_clause if open_clause and open_clause.get("_open") else None
        for definition in page.get("definitions_introduced") or []:
            if isinstance(definition, dict) and str(definition.get("term", "")).strip():
                definitions.append({"term": str(definition["term"]).strip(),
                                    "definition": definition.get("definition", ""),
                                    "source_page_ids": [page_id] if page_id else []})
    for clause in clauses:
        clause.pop("_open", None)
    return {"clauses": [c for c in clauses if c["full_text"] or c["heading"]],
            "definitions": definitions, "missing_or_unclear_sections": notes}


def _assign_clause_ids(clauses: list[dict], definitions: list[dict]) -> list[dict]:
    finalized = []
    terms = [d["term"] for d in definitions if d.get("term")]
    for index, clause in enumerate(clauses, start=1):
        clause_id = f"CL_{index:04d}"
        full_text = str(clause.get("full_text", "") or "")
        text_casefold = full_text.casefold()
        defined_terms_used = [term for term in terms if term.casefold() in text_casefold]
        finalized.append({
            "clause_id": clause_id,
            "clause_number": clause.get("clause_number", ""),
            "heading": clause.get("heading", ""),
            "full_text": full_text,
            "category": clause.get("category", "other"),
            "completeness_status": (
                "spans_multiple_pages"
                if clause.get("continues_from_previous_chunk") or clause.get("continues_into_next_chunk")
                or len(clause.get("source_page_ids") or []) > 1
                else "complete"
            ),
            "exceptions_or_carve_outs": clause.get("exceptions_or_carve_outs", []) or [],
            "source_page_ids": clause.get("source_page_ids", []) or [],
            "defined_terms_used": defined_terms_used,
            "related_clause_ids": [],
        })
    return finalized


def _compact_clause_summaries(clauses: list[dict]) -> list[dict]:
    return [{
        "clause_id": c["clause_id"],
        "clause_number": c.get("clause_number", ""),
        "heading": c.get("heading", ""),
        "category": c.get("category", ""),
        "excerpt": str(c.get("full_text", ""))[:400],
    } for c in clauses]


def consolidate_page_structures(
    page_structures: list[dict],
    confirmed_profile: dict,
    chunk_progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[list[dict], dict]:
    if not page_structures:
        raise ValueError("No page structures are available to consolidate.")

    stitched = stitch_page_structures(page_structures)
    ordered_chunk_maps = [stitched]
    if chunk_progress_callback:
        chunk_progress_callback(1, 1, "stitched")

    raw_clauses = stitched["clauses"]
    missing_or_unclear_sections = stitched["missing_or_unclear_sections"]
    by_term: dict[str, dict] = {}
    for definition in stitched["definitions"]:
        key = definition["term"].casefold()
        if key in by_term:
            by_term[key]["source_page_ids"] = list(dict.fromkeys(
                by_term[key]["source_page_ids"] + definition["source_page_ids"]))
        else:
            by_term[key] = dict(definition)
    definitions = list(by_term.values())
    clauses = _assign_clause_ids(raw_clauses, definitions)

    synthesis = agreement_complete_json(
        PACKAGE_SYNTHESIS_PROMPT,
        {
            "confirmed_profile": confirmed_profile or {},
            "clauses": select_with_char_budget(_compact_clause_summaries(clauses), max_chars=29400),
            "definitions": [{"term": d["term"]} for d in definitions],
        },
        operation="agreement package synthesis",
    )

    dependency_graph = synthesis.get("dependency_graph", []) or []
    related_by_clause: dict[str, list[str]] = {c["clause_id"]: [] for c in clauses}
    for edge in dependency_graph:
        source = str(edge.get("source_clause_id", "") or "")
        target = str(edge.get("target_clause_id", "") or "")
        if source in related_by_clause and target and target not in related_by_clause[source]:
            related_by_clause[source].append(target)
        if target in related_by_clause and source and source not in related_by_clause[target]:
            related_by_clause[target].append(source)
    for clause in clauses:
        clause["related_clause_ids"] = related_by_clause.get(clause["clause_id"], [])

    clause_map = {
        "clauses": clauses,
        "definitions": definitions,
        "dependency_graph": dependency_graph,
        "missing_dependencies": synthesis.get("missing_dependencies", []) or [],
        "missing_or_unclear_sections": missing_or_unclear_sections,
        "cross_document_conflicts": synthesis.get("cross_document_conflicts", []) or [],
        "contract_overview": synthesis.get("contract_overview", {}) or {},
        "package_summary": synthesis.get("package_summary", "") or "",
    }
    return ordered_chunk_maps, clause_map
