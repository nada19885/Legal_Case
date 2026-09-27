from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class MatterFilters:
    language: str = "ar"
    matter_date: Optional[date] = None
    customer_type: Optional[str] = None
    regulated_entity_type: Optional[str] = None
    product_type: Optional[str] = None
    activity_type: Optional[str] = None
    current_only: bool = True


@dataclass
class RetrievalHit:
    node_id: str
    score: float
    query_text: str
    retrieval_method: str = "vector"
    metadata: dict = field(default_factory=dict)
