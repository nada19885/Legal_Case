"""
Checks that every model call asks for no reasoning (/no_think).

Run from the repository root:  python test_thinking.py
"""

import importlib.util
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

from legal_platform import llm                                   # noqa: E402
from legal_platform.thinking import no_think, report_thinking    # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


check("an instruction gets /no_think at its start", no_think("Read the page.") == "/no_think\nRead the page.")
check("/no_think is never added twice", no_think("/no_think\nRead the page.") == "/no_think\nRead the page.")
check("a reasoning block in an answer is reported", report_thinking("<think>long reasoning</think>{}", "test") > 0)
check("an answer without reasoning reports nothing", report_thinking("<think>\n\n</think>{\"a\": 1}", "test") == 0)


class _Response:
    success = True
    text = '{"ok": true}'


class _Completion:
    def __init__(self):
        self.messages = []
        self.settings = {}

    def with_message(self, text, role):
        self.messages.append((role, text))

    def execute(self):
        return _Response()


class _LLM:
    def __init__(self):
        self.completions = []

    def new_completion(self):
        self.completions.append(_Completion())
        return self.completions[-1]


model = _LLM()
llm._execute(model, "test-llm", [("Summarise the page.", "system"), ('{"page": 1}', "user")], 0.0)
sent = model.completions[0].messages
check("a text model call starts its instruction with /no_think", sent[0] == ("system", "/no_think\nSummarise the page."))
check("the payload is sent unchanged", sent[1] == ("user", '{"page": 1}'))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
