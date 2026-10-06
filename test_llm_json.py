"""
Checks for reading model answers that are almost JSON (llm.py).

Run from the repository root:  python test_llm_json.py
"""

import importlib.util
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import llm                    # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


GOOD = {"overall_posture": "moderate", "executive_summary": "ملخص: البنك نفّذ التجميد بناءً على بلاغ.",
        "issues": [{"issue_id": "I1", "issue_title": "تجميد الحساب", "applicable_rules": [
            {"proposition": "يجوز للبنك التحفظ على المبلغ", "node_ids": ["KB_12", "KB_40"]}],
            "our_position": "x", "opponent_position": "y", "response": "z", "conclusion": "unresolved",
            "residual_risk": "r"}]}
pretty = json.dumps(GOOD, ensure_ascii=False, indent=2)


def read(text):
    try:
        return llm.parse_json_lenient(text)
    except Exception as error:
        return error


broken = {
    "missing comma between fields": pretty.replace('"our_position": "x",', '"our_position": "x"'),
    "missing comma between objects": pretty.replace('"KB_40"\n          ]\n        }',
                                                    '"KB_40"\n          ]\n        }').replace('},\n', '}\n'),
    "quote inside Arabic text": pretty.replace("بناءً على بلاغ", 'بناءً على "بلاغ احتيال", كما ورد'),
    "unquoted node ids": pretty.replace('"KB_12", "KB_40"', "KB_12, KB_40").replace('"KB_12",\n            "KB_40"', "KB_12,\n            KB_40"),
    "unquoted enum value": pretty.replace('"conclusion": "unresolved"', '"conclusion": unresolved'),
    "comment after a value": pretty.replace('"residual_risk": "r"', '"residual_risk": "r"  // to confirm'),
    "trailing comma": pretty.replace('"residual_risk": "r"', '"residual_risk": "r",'),
    "single quotes": pretty.replace('"conclusion": "unresolved"', "'conclusion': 'unresolved'"),
    "Python None": pretty.replace('"residual_risk": "r"', '"residual_risk": None'),
    "text after the JSON": pretty + "\n\nI hope this analysis helps.",
}
for label, text in broken.items():
    result = read(text)
    check(f"read despite: {label}",
          isinstance(result, dict) and result.get("overall_posture") == "moderate"
          and result["issues"][0]["issue_title"] == "تجميد الحساب")
quoted = read(broken["quote inside Arabic text"])
check("a quote inside the text is kept as text", 'بناءً على "بلاغ احتيال", كما ورد' in quoted["executive_summary"])
check("unquoted ids are read as the same ids", read(broken["unquoted node ids"])["issues"][0]["applicable_rules"][0]["node_ids"]
      == ["KB_12", "KB_40"])
cut = read(pretty[:pretty.index('"opponent_position"')])
check("an answer cut off at the end keeps what was written",
      isinstance(cut, dict) and cut["issues"][0]["our_position"] == "x")
check("valid JSON is read exactly as before", read(pretty) == GOOD)
check("an answer with no JSON at all still fails clearly", isinstance(read("I cannot help with that."), ValueError))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
