"""
Checks that vision calls ask for no reasoning (/no_think) and text-model
calls are sent as they are (the text model keeps its reasoning).

Run from the repository root:  python test_thinking.py
"""

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
dataiku = sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import llm, vlm_adapter                      # noqa: E402
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
check("a text model call is sent as it is (the text model keeps its reasoning)",
      sent[0] == ("system", "Summarise the page."))
check("the payload is sent unchanged", sent[1] == ("user", '{"page": 1}'))


class _Multipart:
    def __init__(self, owner):
        self.owner = owner

    def with_text(self, text):
        self.owner.texts.append(text)

    def with_inline_image(self, data, mime):
        pass

    def add(self):
        pass


class _VisionCompletion(_Completion):
    def __init__(self):
        super().__init__()
        self.texts = []

    def new_multipart_message(self, role):
        return _Multipart(self)


class _VisionLLM:
    def __init__(self):
        self.completions = []

    def new_completion(self):
        self.completions.append(_VisionCompletion())
        return self.completions[-1]


vision_model = _VisionLLM()
dataiku.api_client = lambda: types.SimpleNamespace(
    get_default_project=lambda: types.SimpleNamespace(get_llm=lambda model_id: vision_model))
vlm_adapter.vision_call("Transcribe the page.", b"png")
check("a vision call starts its instruction with /no_think",
      vision_model.completions[0].texts == ["/no_think\nTranscribe the page."])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
