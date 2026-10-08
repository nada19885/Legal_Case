from __future__ import annotations

from typing import Any

from .config import (
    LEGAL_KB_ID,
    DEFAULT_RETRIEVAL_LIMIT,
    DEFAULT_EXPANDED_LIMIT,
)

from .data_access import (
    load_legal_nodes,
    load_legal_relationships,
    dataframe_to_records,
)

from .graph import LegalGraph
from .legal_filters import node_is_applicable
from .research_log import build_log_entries


VALID_SEARCH_TYPES = {
    "SIMILARITY",
    "SIMILARITY_THRESHOLD",
    "MMR",
    "HYBRID",
}


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)

    except Exception:
        return float(default)


def _document_text(
    document: Any,
) -> str:
    """
    Extract the retrieved document text across Dataiku response variants.
    """
    if document is None:
        return ""

    if isinstance(
        document,
        dict,
    ):
        for key in (
            "text",
            "page_content",
            "content",
            "canonical_text",
        ):
            value = document.get(
                key
            )

            if value not in (
                None,
                "",
            ):
                return str(
                    value
                )

        return ""

    for attribute_name in (
        "text",
        "page_content",
        "content",
    ):
        value = getattr(
            document,
            attribute_name,
            None,
        )

        if value not in (
            None,
            "",
        ):
            return str(
                value
            )

    return str(
        document
    )


def _document_metadata(
    document: Any,
) -> dict:
    """
    Extract metadata across Dataiku response variants.
    """
    if document is None:
        return {}

    if isinstance(
        document,
        dict,
    ):
        metadata = document.get(
            "metadata",
            {},
        )

        if isinstance(
            metadata,
            dict,
        ):
            return dict(
                metadata
            )

        return {}

    metadata = getattr(
        document,
        "metadata",
        {},
    )

    if isinstance(
        metadata,
        dict,
    ):
        return dict(
            metadata
        )

    return {}


def _document_score(
    document: Any,
    fallback: float = 0.0,
) -> float:
    """
    Dataiku Knowledge Bank results may expose score, distance or relevance.
    Preserve the available numeric value for logging.
    """
    if document is None:
        return float(
            fallback
        )

    if isinstance(
        document,
        dict,
    ):
        for key in (
            "score",
            "similarity",
            "relevance",
            "distance",
        ):
            if key in document:
                return _safe_float(
                    document.get(
                        key
                    ),
                    fallback,
                )

        return float(
            fallback
        )

    for attribute_name in (
        "score",
        "similarity",
        "relevance",
        "distance",
    ):
        value = getattr(
            document,
            attribute_name,
            None,
        )

        if value is not None:
            return _safe_float(
                value,
                fallback,
            )

    return float(
        fallback
    )


def _normalise_search_type(
    search_type: str,
) -> str:
    value = str(
        search_type
        or "SIMILARITY"
    ).strip().upper()

    if value not in VALID_SEARCH_TYPES:
        raise ValueError(
            "Invalid Knowledge Bank search type "
            f"{search_type!r}. Expected one of "
            f"{sorted(VALID_SEARCH_TYPES)!r}."
        )

    return value


def search_knowledge_bank(
    query: str,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
    search_type: str = "SIMILARITY",
    similarity_threshold: float | None = None,
    filter_expression: Any = None,
) -> list[dict]:
    """
    Search the Dataiku Knowledge Bank using the supported DSS search API.

    DSS 14.7.1 expects:
      - uppercase search_type values;
      - max_documents rather than LangChain's k.

    The function returns the same hit shape previously consumed by the rest of
    the application, so research_issue(), research logging and graph expansion
    do not need to change.
    """
    import dataiku

    query = str(
        query or ""
    ).strip()

    if not query:
        return []

    try:
        limit = int(
            limit
        )

    except Exception as error:
        raise ValueError(
            "Knowledge Bank retrieval limit must be an integer."
        ) from error

    if limit < 1:
        raise ValueError(
            "Knowledge Bank retrieval limit must be at least 1."
        )

    resolved_search_type = (
        _normalise_search_type(
            search_type
        )
    )

    client = dataiku.api_client()
    project = client.get_default_project()

    knowledge_bank = (
        project.get_knowledge_bank(
            LEGAL_KB_ID
        )
    )

    search_kwargs = {
        "query": query,
        "max_documents": limit,
        "search_type": (
            resolved_search_type
        ),
    }

    if (
        resolved_search_type
        == "SIMILARITY_THRESHOLD"
    ):
        threshold = (
            0.0
            if similarity_threshold
            is None
            else float(
                similarity_threshold
            )
        )

        search_kwargs[
            "similarity_threshold"
        ] = threshold

    if filter_expression is not None:
        search_kwargs[
            "filter"
        ] = filter_expression

    print(
        "[legal retrieval] "
        f"kb_id={LEGAL_KB_ID} "
        f"search_type={resolved_search_type} "
        f"max_documents={limit} "
        f"query={query!r}"
    )

    result = knowledge_bank.search(
        **search_kwargs
    )

    documents = getattr(
        result,
        "documents",
        None,
    )

    if documents is None:
        if isinstance(
            result,
            dict,
        ):
            documents = result.get(
                "documents",
                [],
            )

        else:
            documents = []

    documents = list(
        documents or []
    )

    print(
        "[legal retrieval] "
        f"documents_returned={len(documents)}"
    )

    hits = []

    for rank, document in enumerate(
        documents,
        start=1,
    ):
        metadata = (
            _document_metadata(
                document
            )
        )

        text = _document_text(
            document
        )

        # Use canonical_text from metadata when Dataiku returns the embedded
        # search representation as document.text.
        canonical_text = str(
            metadata.get(
                "canonical_text",
                "",
            )
            or ""
        ).strip()

        if canonical_text:
            text = canonical_text

        score = _document_score(
            document,
            fallback=0.0,
        )

        hit = {
            "node_id": str(
                metadata.get(
                    "node_id",
                    "",
                )
                or ""
            ),
            "document_id": str(
                metadata.get(
                    "document_id",
                    "",
                )
                or ""
            ),
            "parent_id": str(
                metadata.get(
                    "parent_id",
                    "",
                )
                or ""
            ),
            "node_type": str(
                metadata.get(
                    "node_type",
                    "",
                )
                or ""
            ),
            "node_number": str(
                metadata.get(
                    "node_number",
                    "",
                )
                or ""
            ),
            "title": str(
                metadata.get(
                    "title",
                    "",
                )
                or ""
            ),
            "document_title": str(
                metadata.get(
                    "document_title",
                    "",
                )
                or ""
            ),
            "heading_path": str(
                metadata.get(
                    "heading_path",
                    "",
                )
                or ""
            ),
            "source_url": str(
                metadata.get(
                    "source_url",
                    "",
                )
                or ""
            ),
            "language": str(
                metadata.get(
                    "language",
                    "",
                )
                or ""
            ),
            "review_status": str(
                metadata.get(
                    "review_status",
                    "",
                )
                or ""
            ),
            "extraction_confidence": (
                _safe_float(
                    metadata.get(
                        "extraction_confidence",
                        0.0,
                    ),
                    0.0,
                )
            ),
            "text": text,
            "score": score,
            "rank": rank,
            "retrieval_method": (
                resolved_search_type.lower()
            ),
            "metadata": metadata,
        }

        hits.append(
            hit
        )

    return hits


def research_issue(
    query,
    filters,
    research_run_id="",
    case_id="",
    issue_id="",
    question_id="",
    created_by="",
    persist_log=False,
):
    """
    Retrieve applicable legal nodes, apply matter filters and expand the legal
    graph. The public return shape is preserved.
    """
    nodes_df = load_legal_nodes()

    relationships_df = (
        load_legal_relationships()
    )

    node_records = dataframe_to_records(
        nodes_df
    )

    node_lookup = {
        str(
            node.get(
                "node_id",
                "",
            )
        ): node
        for node in node_records
        if node.get(
            "node_id"
        )
    }

    raw_hits = search_knowledge_bank(
        query=query,
        limit=DEFAULT_RETRIEVAL_LIMIT,
        search_type="SIMILARITY",
    )

    filtered_hits = []

    for hit in raw_hits:
        node = node_lookup.get(
            hit.get(
                "node_id"
            )
        )

        if not node:
            continue

        if node_is_applicable(
            node,
            filters,
        ):
            filtered_hits.append(
                hit
            )

    graph = LegalGraph(
        nodes=node_records,
        relationships=dataframe_to_records(
            relationships_df
        ),
    )

    expanded_nodes = graph.expand_hits(
        [
            hit[
                "node_id"
            ]
            for hit in filtered_hits
            if hit.get(
                "node_id"
            )
        ],
        max_total=(
            DEFAULT_EXPANDED_LIMIT
        ),
    )

    log_rows = build_log_entries(
        research_run_id=(
            research_run_id
        ),
        case_id=case_id,
        issue_id=issue_id,
        question_id=question_id,
        query_text=query,
        retrieved_hits=(
            filtered_hits
        ),
        expanded_nodes=(
            expanded_nodes
        ),
        filters=filters,
        created_by=created_by,
    )

    if (
        persist_log
        and log_rows
    ):
        from .storage import (
            append_rows,
        )

        from .config import (
            LEGAL_RESEARCH_LOG_DATASET,
        )

        append_rows(
            LEGAL_RESEARCH_LOG_DATASET,
            log_rows,
        )

    return {
        "query": query,
        "hits": filtered_hits,
        "expanded_nodes": (
            expanded_nodes
        ),
        "log_rows": log_rows,
    }
