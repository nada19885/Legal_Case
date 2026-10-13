"""
Checks for users and case isolation (access.py + every route of main.py).

Run from the repository root:  python test_access.py
The real Flask routes of main.py are loaded with Dataiku replaced by
in-memory stand-ins; the signed-in user comes from a test header. Checks
that a user only ever sees and reaches their own cases, whatever case id
they send, on every route that takes one.
"""

import importlib.util
import io
import json
import pathlib
import sys
import types

import flask
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
FILES, DATASETS = {}, {}


class _Folder:
    def __init__(self, *_):
        pass

    def upload_data(self, path, data):
        FILES[path] = data if isinstance(data, bytes) else data.encode()

    def get_download_stream(self, path):
        if path not in FILES:
            raise FileNotFoundError(path)
        return io.BytesIO(FILES[path])

    def list_paths_in_partition(self):
        return list(FILES)


class _Dataset:
    def __init__(self, name, **_):
        self.name, self.spec_item = name, {}

    def get_dataframe(self):
        return DATASETS.get(self.name, pd.DataFrame()).copy()

    def write_with_schema(self, frame):
        if self.spec_item.get("appendMode"):
            DATASETS[self.name] = pd.concat([DATASETS.get(self.name, pd.DataFrame()), frame], ignore_index=True)
        else:
            DATASETS[self.name] = frame


dataiku = types.ModuleType("dataiku")
dataiku.Folder, dataiku.Dataset = _Folder, _Dataset
dataiku.api_client = lambda: None
webapp = types.ModuleType("dataiku.customwebapp")
webapp.app = flask.Flask("test")
webapp.__all__ = ["app"]
dataiku.customwebapp = webapp
sys.modules["dataiku"] = dataiku
sys.modules["dataiku.customwebapp"] = webapp
spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules["legal_platform"] = package
spec.loader.exec_module(package)

from legal_platform import access          # noqa: E402

access.user_from_headers = lambda headers: headers.get("X-Test-User", "")
main_spec = importlib.util.spec_from_file_location("webapp_main", ROOT / "main.py")
main = importlib.util.module_from_spec(main_spec)
main_spec.loader.exec_module(main)
client = webapp.app.test_client()

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


def as_user(user):
    return {"X-Test-User": user} if user else {}


# --- signing in ------------------------------------------------------------------------
check("without a Dataiku sign-in every route is refused", client.get("/cases").status_code == 401
      and client.post("/create_case", json={"case_name": "x"}).status_code == 401)
check("the signed-in user is known to the app", client.get("/me", headers=as_user("nada")).get_json()["user"] == "nada")

# --- creating and listing -------------------------------------------------------------
made = client.post("/create_case", headers=as_user("nada"), json={
    "case_name": "Huda v BSF", "language": "ar", "workflow_type": "litigation", "case_number": "445/2025",
    "client_name": "BSF", "opposing_party": "Huda", "case_type": "account freeze"}).get_json()
nada_case = made["case_id"]
other = client.post("/create_case", headers=as_user("omar"), json={"case_name": "Omar's case"}).get_json()["case_id"]
DATASETS["cases"] = pd.concat([DATASETS["cases"], pd.DataFrame([{"case_id": "CASE_OLD", "case_name": "unowned",
                                                                  "workflow_type": "litigation"}])])
nada_list = client.get("/cases?workflow=litigation", headers=as_user("nada")).get_json()["cases"]
check("a user's case list holds only their own cases (not other users', not unowned old cases)",
      [c["case_id"] for c in nada_list] == [nada_case])
check("the new case's details are kept (case number, client, opposing party, type)",
      nada_list[0]["details"] == {"case_number": "445/2025", "client_name": "BSF", "opposing_party": "Huda",
                                  "case_type": "account freeze"} and nada_list[0]["progress"] == "new")

# --- every case route refuses another user's case -------------------------------------
routes = [(rule.rule, sorted(rule.methods - {"HEAD", "OPTIONS"})) for rule in webapp.app.url_map.iter_rules()
          if rule.endpoint != "static"]
open_routes = {"/me", "/cases", "/create_case", "/bootstrap", "/job_status"}
leaks = []
for path, methods in routes:
    if path in open_routes:
        continue
    for method in methods:
        for case_id in (other, "CASE_OLD", "../../etc"):
            if method == "GET":
                response = client.get(path, headers=as_user("nada"), query_string={"case_id": case_id, "page_id": "P1"})
            elif path in ("/documents/process", "/agreement/process"):
                response = client.post(path, headers=as_user("nada"), data={"case_id": case_id})
            else:
                response = client.post(path, headers=as_user("nada"), json={"case_id": case_id, "row_id": "R1"})
            if response.status_code != 404:
                leaks.append((method, path, case_id, response.status_code))
check(f"all {sum(len(m) for p, m in routes if p not in open_routes)} case routes answer 'not found' for another "
      f"user's case, an unowned case or a forged id", not leaks)
if leaks:
    print("   ", leaks[:10])
check("the owner reaches their own case", client.get("/state/persist", headers=as_user("nada")).status_code == 405
      and client.post("/state/persist", headers=as_user("nada"),
                      json={"case_id": nada_case, "state": {"pleading_language": "ar"}}).status_code == 200)
check("another user cannot archive someone else's case",
      client.post("/case/archive", headers=as_user("omar"), json={"case_id": nada_case}).status_code == 404)
check("the owner can archive and the case leaves the active list",
      client.post("/case/archive", headers=as_user("nada"), json={"case_id": nada_case}).status_code == 200
      and client.get("/cases", headers=as_user("nada")).get_json()["cases"] == []
      and len(client.get("/cases?archived=1", headers=as_user("nada")).get_json()["cases"]) == 1)

# --- background jobs --------------------------------------------------------------------
with main.JOBS_LOCK:
    main.JOBS["J1"] = {"status": "done", "user": "omar", "case_id": other, "stage": "", "progress": {},
                       "result": {"secret": 1}, "error": None, "finished_at": None}
check("another user's job status is not readable",
      client.get("/job_status?job_id=J1", headers=as_user("nada")).status_code == 404
      and client.get("/job_status?job_id=J1", headers=as_user("omar")).status_code == 200)

# --- the ownership records ---------------------------------------------------------------
try:
    access.register_case(nada_case, "omar", "litigation")
    check("a case cannot be re-registered to another user", False)
except ValueError:
    check("a case cannot be re-registered to another user", True)
check("forged ids are rejected before any file is read", not access.valid_id("../x") and access.case_record("../x") is None)
check("no password or secret is stored", not any(b"password" in data.lower() for data in FILES.values()))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
