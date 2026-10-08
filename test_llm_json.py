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

# Reasoning and prose around the answer
answer = json.dumps(GOOD, ensure_ascii=False)
check("a closed reasoning block is removed", read("<think>let me think {about it}</think>\n" + answer) == GOOD)
check("reasoning before a lone closing tag is removed",
      read('the format is {"issue_id": ""} so...</think>\n' + answer) == GOOD)
check("an answer still reasoning when it stopped has no answer", llm.strip_think("<think>the issues are {") == "")
check("prose with an example object before the answer: the answer is read",
      read('Use the format {"issue_id": ""} as asked.\n' + answer) == GOOD)
check("an object nested in a cut-off answer is not taken for the answer",
      isinstance(read(pretty[:pretty.index('"opponent_position"')]).get("issues"), list))


def refused(text, keys):
    try:
        llm.parse_json_lenient(text, keys)
        return False
    except llm.MissingFields:
        return True


check("expected fields: an answer with none of them is refused", refused('{"error": "no"}', ("issues",)))
check("expected fields: an answer with them is read", not refused(answer, ("issues",)))


# complete_json: what the second call carries
class _Response:
    def __init__(self, text):
        self.text, self.success = text, True


class _Completion:
    def __init__(self, owner):
        self.owner, self.settings, self.messages = owner, {}, []

    def with_message(self, text, role="user"):
        self.messages.append((role, text))

    def execute(self):
        self.owner.sent.append(self.messages)
        return _Response(self.owner.answers.pop(0))


class _Model:
    def __init__(self, answers):
        self.answers, self.sent = list(answers), []

    def new_completion(self):
        return _Completion(self)


def run(answers, keys=()):
    model = _Model(answers)
    project = types.SimpleNamespace(get_llm=lambda llm_id: model)
    llm.dataiku.api_client = lambda: types.SimpleNamespace(get_default_project=lambda: project)
    try:
        result = llm.complete_json("SYSTEM", {"issues": ["x" * 5000]}, llm_id="m", expect_keys=keys)
    except Exception as error:
        result = error
    return result, model.sent


result, sent = run(["<think>" + "reasoning " * 500, answer])
check("an answer cut off while reasoning: the same request again, without reasoning, not bigger",
      result == GOOD and len(sent) == 2 and sent[1][0][1].startswith("/no_think")
      and len(sent[1]) == 2 and len(sent[1][1][1]) < len(sent[0][1][1]) + 200)
result, sent = run(["{\n", answer])
check("unreadable JSON: only the answer is sent back to be fixed, never the request",
      result == GOOD and len(sent) == 2 and sent[1][0][1] == llm.FIX_JSON_PROMPT and sent[1][1][1] == "{")
result, sent = run(['{"error": "no"}', answer], ("issues",))
check("an answer without the expected fields: asked again", result == GOOD and len(sent) == 2)
result, sent = run(["no json here", "still nothing"])
check("two unusable answers: the first error is raised", isinstance(result, ValueError) and len(sent) == 2)
result, sent = run([answer])
check("a good answer takes one call", result == GOOD and len(sent) == 1)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
