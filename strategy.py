from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import pandas as pd

from .config import ANALYSIS_LLM_ID, STRATEGY_DATASET
from .ids import random_id
from .llm import complete_json
from .storage import append_rows


STRATEGY_PROMPT = r"""
You are a defence-strategy planning service assisting a qualified attorney who represents Banque Saudi Fransi (BSF / البنك السعودي الفرنسي).
All primary and alternative theories must defend and protect BSF. Never formulate the claimant's or customer's case as the recommended strategy.

Use only the supplied approved/candidate analysis, facts, evidence status, and
legal authorities. Produce lawful, practical strategy options. Do not recommend
concealment, alteration, destruction, fabrication, intimidation, or misleading
a court, regulator, client, witness, or opponent.

The plan must:
- identify a primary and alternative defence theory
- identify what to admit, deny, challenge, or investigate
- identify evidence challenges: authenticity, completeness, relevance,
  reliability, causation, and weight
- request missing documents one by one where possible
- propose interview and expert questions
- assign purpose and priority to each action
- cite legal node IDs and fact/evidence IDs
- expressly identify uncertainty and attorney decisions

Return only JSON.

Schema:
{
  "primary_theory": {
    "description": "",
    "legal_node_ids": [],
    "fact_ids": [],
    "risks": []
  },
  "alternative_theories": [
    {
      "description": "",
      "legal_node_ids": [],
      "fact_ids": [],
      "trigger_conditions": [],
      "risks": []
    }
  ],
  "positions": {
    "admit": [],
    "deny": [],
    "challenge": [],
    "investigate": []
  },
  "evidence_challenge_matrix": [
    {
      "evidence_id": "",
      "challenge_type": "authenticity|completeness|relevance|reliability|causation|weight",
      "basis": "",
      "required_action": ""
    }
  ],
  "actions": [
    {
      "issue_id": "",
      "action_type": "request_document|interview|expert_question|procedural_action|analysis|settlement_consideration",
      "description": "",
      "owner": "",
      "purpose": "",
      "priority": "critical|high|medium|low",
      "legal_node_ids": [],
      "fact_ids": [],
      "evidence_ids": [],
      "risk": ""
    }
  ],
  "missing_documents": [],
  "attorney_decisions_required": [],
  "strategy_limitations": []
}
"""


def _json_safe(value: Any) -> Any:
    """
    Convert common Python / pandas / numpy-like objects into JSON-safe values.

    This does NOT change the business meaning of the data.
    It only makes the payload safe to serialize before sending it to the LLM.
    """

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, pd.DataFrame):
        return json.loads(
            value.fillna("").to_json(
                orient="records",
                force_ascii=False,
            )
        )

    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(item)
            for item in value
        ]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    # Handles many numpy scalar types such as np.int64 / np.float64.
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass

    # Handles timestamps / datetimes and similar objects.
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    # Final safe fallback.
    return str(value)


def generate_defence_strategy(
    case_record,
    analysis,
    facts,
    evidence,
    authority_nodes,
):
    """
    Generate and persist the defence strategy for a case.

    Inputs:
        case_record:
            Case metadata / case dictionary.

        analysis:
            Legal issue analysis already produced for the case.

        facts:
            Case facts. Can be a pandas DataFrame or JSON-like structure.

        evidence:
            Case evidence. Can be a pandas DataFrame or JSON-like structure.

        authority_nodes:
            Legal authority / knowledge-base nodes retrieved for the case.

    Output:
        Full defence-strategy JSON returned by the LLM.
    """

    # -------------------------------------------------------------------------
    # 1. Build a JSON-safe payload
    # -------------------------------------------------------------------------
    payload = {
        "representation_mandate": {
            "represented_party":
                "Banque Saudi Fransi (BSF) / البنك السعودي الفرنسي",
            "instruction":
                "Develop the defence exclusively for BSF.",
        },
        "case": _json_safe(case_record),
        "analysis": _json_safe(analysis),
        "facts": _json_safe(facts),
        "evidence": _json_safe(evidence),
        "authority_nodes": _json_safe(authority_nodes),
    }

    # -------------------------------------------------------------------------
    # 2. Validate serialization before calling the LLM
    # -------------------------------------------------------------------------
    try:
        json.dumps(
            payload,
            ensure_ascii=False,
        )
        print("[strategy] payload serialization OK")

    except Exception as exc:
        raise RuntimeError(
            f"Defence strategy payload is not JSON serializable: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    # -------------------------------------------------------------------------
    # 3. Call the LLM
    # -------------------------------------------------------------------------
    result = complete_json(
        system_prompt=STRATEGY_PROMPT,
        user_payload=payload,
        llm_id=ANALYSIS_LLM_ID,
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            "Defence strategy LLM returned an unexpected result type: "
            f"{type(result).__name__}"
        )

    # -------------------------------------------------------------------------
    # 4. Persist strategy rows
    # -------------------------------------------------------------------------
    rows = []

    if isinstance(case_record, dict):
        case_id = str(case_record.get("case_id", "") or "")
    else:
        safe_case = _json_safe(case_record)

        if isinstance(safe_case, dict):
            case_id = str(safe_case.get("case_id", "") or "")
        else:
            case_id = ""

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    # -------------------------------------------------------------------------
    # Primary + alternative theories
    # -------------------------------------------------------------------------
    theories = [
        (
            "primary",
            result.get(
                "primary_theory",
                {},
            ),
        )
    ]

    theories.extend(
        (
            "alternative",
            theory,
        )
        for theory in result.get(
            "alternative_theories",
            [],
        )
        if isinstance(theory, dict)
    )

    for theory_type, theory in theories:
        if not isinstance(theory, dict):
            continue

        if not theory:
            continue

        rows.append({
            "strategy_action_id":
                random_id("STRAT"),

            "case_id":
                case_id,

            "issue_id":
                "",

            "theory_type":
                theory_type,

            "theory_description":
                theory.get(
                    "description",
                    "",
                ),

            "facts_supporting_json":
                json.dumps(
                    theory.get(
                        "fact_ids",
                        [],
                    ),
                    ensure_ascii=False,
                ),

            "legal_node_ids_json":
                json.dumps(
                    theory.get(
                        "legal_node_ids",
                        [],
                    ),
                    ensure_ascii=False,
                ),

            "evidence_ids_json":
                "[]",

            "action_type":
                "defence_theory",

            "action_description":
                theory.get(
                    "description",
                    "",
                ),

            "owner":
                "Attorney",

            "purpose":
                "Defence theory selection",

            "priority":
                "high",

            "due_date":
                "",

            "risk":
                json.dumps(
                    theory.get(
                        "risks",
                        [],
                    ),
                    ensure_ascii=False,
                ),

            "review_status":
                "not_reviewed",

            "approved_by":
                "",

            "approved_at":
                "",

            "created_at":
                created_at,
        })

    # -------------------------------------------------------------------------
    # Individual strategy actions
    # -------------------------------------------------------------------------
    actions = result.get(
        "actions",
        [],
    )

    if not isinstance(actions, list):
        actions = []

    for action in actions:
        if not isinstance(action, dict):
            continue

        rows.append({
            "strategy_action_id":
                random_id("STRAT"),

            "case_id":
                case_id,

            "issue_id":
                action.get(
                    "issue_id",
                    "",
                ),

            "theory_type":
                "",

            "theory_description":
                "",

            "facts_supporting_json":
                json.dumps(
                    action.get(
                        "fact_ids",
                        [],
                    ),
                    ensure_ascii=False,
                ),

            "legal_node_ids_json":
                json.dumps(
                    action.get(
                        "legal_node_ids",
                        [],
                    ),
                    ensure_ascii=False,
                ),

            "evidence_ids_json":
                json.dumps(
                    action.get(
                        "evidence_ids",
                        [],
                    ),
                    ensure_ascii=False,
                ),

            "action_type":
                action.get(
                    "action_type",
                    "",
                ),

            "action_description":
                action.get(
                    "description",
                    "",
                ),

            "owner":
                action.get(
                    "owner",
                    "",
                ),

            "purpose":
                action.get(
                    "purpose",
                    "",
                ),

            "priority":
                action.get(
                    "priority",
                    "medium",
                ),

            "due_date":
                "",

            "risk":
                action.get(
                    "risk",
                    "",
                ),

            "review_status":
                "not_reviewed",

            "approved_by":
                "",

            "approved_at":
                "",

            "created_at":
                created_at,
        })

    # -------------------------------------------------------------------------
    # 5. Persist
    # -------------------------------------------------------------------------
    if rows:
        append_rows(
            STRATEGY_DATASET,
            rows,
        )

    return result