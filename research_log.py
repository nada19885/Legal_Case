from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from .ids import stable_id


@dataclass
class ResearchLogEntry:
    research_run_id: str
    case_id: str
    issue_id: str
    question_id: str
    query_text: str

    retrieved_node_id: str
    document_id: str
    node_type: str
    heading_path: str
    source_url: str

    language: str = ""
    matter_date: str = ""
    customer_type: str = ""
    regulated_entity_type: str = ""

    parent_id: str = ""
    retrieval_score: float = 0.0
    retrieval_rank: int = 0
    retrieval_method: str = "vector"

    expansion_type: str = "retrieved"
    seed_node_id: str = ""

    applicability_status: str = "not_checked"
    selected_for_analysis: bool = False
    review_status: str = "not_reviewed"

    created_by: str = ""
    created_at: str = ""

    def to_dict(self):
        row = asdict(self)

        if not row["created_at"]:
            row["created_at"] = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

        row[
            "research_log_id"
        ] = stable_id(
            "RLOG",
            self.research_run_id,
            self.question_id,
            self.retrieved_node_id,
            self.expansion_type,
        )

        return row


def build_log_entries(
    research_run_id,
    case_id,
    issue_id,
    question_id,
    query_text,
    retrieved_hits,
    expanded_nodes,
    filters,
    created_by="",
):
    rows = []

    hit_lookup = {
        hit["node_id"]: hit
        for hit in retrieved_hits
        if hit.get("node_id")
    }

    for rank, node in enumerate(
        expanded_nodes,
        start=1,
    ):
        node_id = str(
            node.get("node_id", "")
        )

        hit = hit_lookup.get(
            node_id,
            {},
        )

        entry = ResearchLogEntry(
            research_run_id=research_run_id,
            case_id=case_id,
            issue_id=issue_id,
            question_id=question_id,
            query_text=query_text,
            retrieved_node_id=node_id,
            document_id=str(
                node.get(
                    "document_id",
                    "",
                )
            ),
            parent_id=str(
                node.get(
                    "parent_id",
                    "",
                )
            ),
            node_type=str(
                node.get(
                    "node_type",
                    "",
                )
            ),
            heading_path=str(
                node.get(
                    "heading_path",
                    "",
                )
            ),
            source_url=str(
                node.get(
                    "source_url",
                    "",
                )
            ),
            language=filters.language,
            matter_date=(
                filters.matter_date.isoformat()
                if filters.matter_date
                else ""
            ),
            customer_type=(
                filters.customer_type
                or ""
            ),
            regulated_entity_type=(
                filters.regulated_entity_type
                or ""
            ),
            retrieval_score=float(
                hit.get(
                    "score",
                    0.0,
                )
            ),
            retrieval_rank=rank,
            retrieval_method=str(
                hit.get(
                    "retrieval_method",
                    "graph_expansion",
                )
            ),
            expansion_type=str(
                node.get(
                    "_expansion_type",
                    "retrieved",
                )
            ),
            seed_node_id=str(
                node.get(
                    "_seed_node_id",
                    node_id,
                )
            ),
            created_by=created_by,
        )

        rows.append(
            entry.to_dict()
        )

    return rows
