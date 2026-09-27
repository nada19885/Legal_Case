"""
Hierarchical contract-wide consolidation — Stage 2 of the agreement
clause-map pipeline (see agreement_workbench.extract_clause_map). Takes the
per-page structures from agreement_page_extraction.structure_agreement_pages
and produces the single consolidated clause_map the rest of the agreement
workflow (agreement_retrieval, agreement_analysis, discuss_agreement, and
Legal.js's clause/review tabs) all depend on.

Three stages:
  A. Per-chunk consolidation (parallel LLM calls) — stitches clause
     fragments into complete clauses within one chunk of pages.
  B. Deterministic chunk-boundary stitching (no LLM) — a clause split
     across two chunks is merged in Python, not re-guessed by a model.
  C. One final LLM call over compact clause summaries (not full text) for
     the package-level dependency graph, missing dependencies,
     cross-document conflicts, contract overview and summary.
Location: lib/python/legal_platform/agreement_consolidation.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .agreement_llm import agreement_complete_json
from .config import AGREEMENT_CHUNK_MAX_WORKERS
from .context_budget import make_char_chunks, select_with_char_budget

CHUNK_CONSOLIDATION_PROMPT = """
You are consolidating one contiguous chunk of page-by-page structured
extractions from a legal agreement package, in page order.

Stitch clause fragments that continue across pages WITHIN this chunk into
single complete clauses. If the chunk's very first clause fragment is
marked continues_from_previous_page, mark the resulting clause
continues_from_previous_chunk=true instead of inventing new content for
what came before this chunk — the previous chunk's output already covers
it, and it will be merged afterward. Likewise, if the chunk's last clause
fragment is marked continues_on_next_page, mark that clause
continues_into_next_chunk=true.

Deduplicate definitions introduced more than once in this chunk. Note any
section that looks referenced but is not present.

Return JSON only:
{
  "clauses": [
    {
      "clause_number": "",
      "heading": "",
      "full_text": "",
      "category": "",
      "exceptions_or_carve_outs": [],
      "source_page_ids": [],
      "continues_from_previous_chunk": false,
      "continues_into_next_chunk": false
    }
  ],
  "definitions": [
    {"term": "", "definition": "", "source_page_ids": []}
  ],
  "missing_or_unclear_sections": []
}
""".strip()

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


def _consolidate_one_chunk(chunk_index: int, chunk: list[dict]) -> dict:
    result = agreement_complete_json(
        CHUNK_CONSOLIDATION_PROMPT,
        {"page_structures": chunk},
        operation=f"agreement chunk consolidation {chunk_index}",
    )
    result.setdefault("clauses", [])
    result.setdefault("definitions", [])
    result.setdefault("missing_or_unclear_sections", [])
    return result


def _stitch_chunk_boundaries(chunk_results: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Stage B: deterministic merge of clauses split across chunk
    boundaries. Chunks are processed in page order, so a trailing
    continues_into_next_chunk clause and the next chunk's leading
    continues_from_previous_chunk clause are the same clause.
    """
    merged_clauses: list[dict] = []
    all_definitions: dict[str, dict] = {}
    missing_sections: list[str] = []
    pending: dict | None = None

    for chunk_result in chunk_results:
        clauses = list(chunk_result.get("clauses", []) or [])
        for index, clause in enumerate(clauses):
            is_first = index == 0
            is_last = index == len(clauses) - 1

            if is_first and pending is not None and clause.get("continues_from_previous_chunk"):
                # The chunk consolidation prompt already stitches fragments
                # WITHIN a chunk; only a chunk's first/last clause can ever
                # be a continuation of the previous/next chunk.
                pending["full_text"] = (pending.get("full_text", "") + "\n" + clause.get("full_text", "")).strip()
                pending["exceptions_or_carve_outs"] = list(dict.fromkeys(
                    (pending.get("exceptions_or_carve_outs") or []) + (clause.get("exceptions_or_carve_outs") or [])
                ))
                pending["source_page_ids"] = list(dict.fromkeys(
                    (pending.get("source_page_ids") or []) + (clause.get("source_page_ids") or [])
                ))
                if not pending.get("clause_number"):
                    pending["clause_number"] = clause.get("clause_number", "")
                if not pending.get("heading"):
                    pending["heading"] = clause.get("heading", "")
                if not pending.get("category"):
                    pending["category"] = clause.get("category", "")
                current = pending
            else:
                if pending is not None:
                    merged_clauses.append(pending)
                    pending = None
                current = dict(clause)

            if is_last and clause.get("continues_into_next_chunk"):
                pending = current  # carry forward; do not flush yet
            else:
                merged_clauses.append(current)
                pending = None

        for definition in chunk_result.get("definitions", []) or []:
            term = str(definition.get("term", "")).strip()
            if not term:
                continue
            key = term.casefold()
            if key not in all_definitions:
                all_definitions[key] = {
                    "term": term,
                    "definition": definition.get("definition", ""),
                    "source_page_ids": list(definition.get("source_page_ids", []) or []),
                }
            else:
                all_definitions[key]["source_page_ids"] = list(dict.fromkeys(
                    all_definitions[key]["source_page_ids"] + list(definition.get("source_page_ids", []) or [])
                ))

        missing_sections.extend(chunk_result.get("missing_or_unclear_sections", []) or [])

    if pending is not None:
        merged_clauses.append(pending)

    return merged_clauses, list(all_definitions.values()), missing_sections


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

    chunks = make_char_chunks(page_structures, target_chars=25200, hard_limit_chars=32200)
    if not chunks:
        chunks = [page_structures]

    chunk_results: list[tuple[int, dict]] = []
    workers = max(1, min(int(AGREEMENT_CHUNK_MAX_WORKERS or 1), len(chunks)))
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_consolidate_one_chunk, index, chunk): index
            for index, chunk in enumerate(chunks, start=1)
        }
        for future in as_completed(futures):
            index = futures[future]
            chunk_results.append((index, future.result()))
            completed += 1
            if chunk_progress_callback:
                chunk_progress_callback(completed, len(chunks), f"chunk_{index}")

    chunk_results.sort(key=lambda item: item[0])
    ordered_chunk_maps = [result for _, result in chunk_results]

    raw_clauses, definitions, missing_or_unclear_sections = _stitch_chunk_boundaries(ordered_chunk_maps)
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
