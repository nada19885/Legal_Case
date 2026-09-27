from collections import defaultdict
from typing import Iterable, Optional


class LegalGraph:

    def __init__(
        self,
        nodes: Iterable[dict],
        relationships: Iterable[dict],
    ):
        self.nodes = {}
        self.children_lookup = defaultdict(list)
        self.parent_lookup = {}
        self.outgoing = defaultdict(list)
        self.incoming = defaultdict(list)

        for node in nodes:
            node_id = self._text(
                node.get("node_id")
            )

            if not node_id:
                continue

            self.nodes[node_id] = node

            parent_id = self._text(
                node.get("parent_id")
            )

            if parent_id:
                self.parent_lookup[
                    node_id
                ] = parent_id

                self.children_lookup[
                    parent_id
                ].append(node_id)

        for relationship in relationships:
            source_id = self._text(
                relationship.get(
                    "source_node_id"
                )
            )

            target_id = self._text(
                relationship.get(
                    "target_node_id"
                )
            )

            if not source_id or not target_id:
                continue

            self.outgoing[
                source_id
            ].append(relationship)

            self.incoming[
                target_id
            ].append(relationship)

    @staticmethod
    def _text(value) -> str:
        if value is None:
            return ""

        return str(value).strip()

    def get_node(
        self,
        node_id: str,
    ) -> Optional[dict]:
        return self.nodes.get(
            node_id
        )

    def get_parent(
        self,
        node_id: str,
    ) -> Optional[dict]:
        parent_id = self.parent_lookup.get(
            node_id
        )

        if not parent_id:
            return None

        return self.get_node(
            parent_id
        )

    def get_children(
        self,
        node_id: str,
        node_types=None,
    ) -> list[dict]:
        children = []

        for child_id in self.children_lookup.get(
            node_id,
            [],
        ):
            child = self.get_node(
                child_id
            )

            if not child:
                continue

            if node_types:
                child_type = self._text(
                    child.get("node_type")
                ).lower()

                if child_type not in node_types:
                    continue

            children.append(child)

        return children

    def get_ancestors(
        self,
        node_id: str,
        max_depth: int = 10,
    ) -> list[dict]:
        ancestors = []
        current_id = node_id
        seen = set()

        while (
            current_id
            and len(ancestors) < max_depth
        ):
            parent_id = self.parent_lookup.get(
                current_id
            )

            if (
                not parent_id
                or parent_id in seen
            ):
                break

            parent = self.get_node(
                parent_id
            )

            if not parent:
                break

            ancestors.append(parent)
            seen.add(parent_id)
            current_id = parent_id

        return ancestors

    def get_siblings(
        self,
        node_id: str,
    ) -> list[dict]:
        parent_id = self.parent_lookup.get(
            node_id
        )

        if not parent_id:
            return []

        return [
            node
            for node in self.get_children(
                parent_id
            )
            if self._text(
                node.get("node_id")
            ) != node_id
        ]

    def get_related_nodes(
        self,
        node_id: str,
        allowed_relationship_types=None,
    ) -> list[dict]:
        results = []

        for relationship in self.outgoing.get(
            node_id,
            [],
        ):
            relationship_type = self._text(
                relationship.get(
                    "relationship_type"
                )
            ).lower()

            if (
                allowed_relationship_types
                and relationship_type
                not in allowed_relationship_types
            ):
                continue

            target = self.get_node(
                self._text(
                    relationship.get(
                        "target_node_id"
                    )
                )
            )

            if target:
                results.append({
                    "relationship": relationship,
                    "node": target,
                })

        return results

    def expand_hits(
        self,
        node_ids,
        include_parent=True,
        include_ancestors=True,
        include_children=True,
        include_siblings=False,
        include_related=True,
        max_children=10,
        max_total=50,
    ) -> list[dict]:
        expanded = {}

        def add_node(
            node,
            expansion_type,
            seed_node_id,
        ):
            if not node:
                return

            node_id = self._text(
                node.get("node_id")
            )

            if not node_id:
                return

            if node_id not in expanded:
                copied = dict(node)

                copied[
                    "_expansion_type"
                ] = expansion_type

                copied[
                    "_seed_node_id"
                ] = seed_node_id

                expanded[node_id] = copied

        for seed_node_id in node_ids:
            seed = self.get_node(
                seed_node_id
            )

            add_node(
                seed,
                "retrieved",
                seed_node_id,
            )

            if include_parent:
                add_node(
                    self.get_parent(
                        seed_node_id
                    ),
                    "parent",
                    seed_node_id,
                )

            if include_ancestors:
                for ancestor in self.get_ancestors(
                    seed_node_id
                ):
                    add_node(
                        ancestor,
                        "ancestor",
                        seed_node_id,
                    )

            if include_children:
                children = self.get_children(
                    seed_node_id
                )

                for child in children[
                    :max_children
                ]:
                    add_node(
                        child,
                        "child",
                        seed_node_id,
                    )

            if include_siblings:
                for sibling in self.get_siblings(
                    seed_node_id
                ):
                    add_node(
                        sibling,
                        "sibling",
                        seed_node_id,
                    )

            if include_related:
                related = self.get_related_nodes(
                    seed_node_id,
                    allowed_relationship_types={
                        "references",
                        "amends",
                        "replaces",
                        "defines",
                        "applies_to",
                        "related_to",
                    },
                )

                for item in related:
                    add_node(
                        item["node"],
                        item[
                            "relationship"
                        ].get(
                            "relationship_type"
                        ),
                        seed_node_id,
                    )

            if len(expanded) >= max_total:
                break

        return list(
            expanded.values()
        )
