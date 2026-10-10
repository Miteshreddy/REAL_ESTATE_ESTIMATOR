"""Create (draft) + import + activate one extracted schedule through the running app's validated API.
Usage: python load_schedule.py <name>   (reads data/sor/states/<name>.csv and .meta.json)"""
import json
import os
import sys


BASE = os.environ.get("EST_URL", "http://127.0.0.1:8000")
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "sor", "states")
FIELDS = ("name", "authority", "department", "country", "region", "district", "city", "authority_level", "schedule_type",
          "code_system", "year", "financial_year", "revision", "effective_from", "effective_to", "currency", "source", "source_ref", "notes")


def main(name, activate=True):
    import requests
    meta = json.load(open(os.path.join(DIR, name + ".meta.json"), encoding="utf-8"))
    body = {k: meta[k] for k in FIELDS if meta.get(k)}
    body["by"] = "official SOR import (ml/training/import_state_sor.py)"
    r = requests.post(f"{BASE}/api/rate-schedules", json=body)
    if r.status_code != 200:
        print("create:", r.status_code, r.text[:400])
        return
    sid = r.json()["id"]
    with open(os.path.join(DIR, name + ".csv"), "rb") as f:
        r = requests.post(f"{BASE}/api/rate-schedules/{sid}/import", files={"file": (name + ".csv", f, "text/csv")},
                          data={"by": f"official SOR import — {meta.get('source_file')} sha256 {meta.get('source_sha256', '')[:16]}"})
    print("import:", r.status_code, r.text[:300])
    if r.status_code == 200 and activate:
        r = requests.patch(f"{BASE}/api/rate-schedules/{sid}", json={"status": "active"})
        print("activate:", r.status_code, r.text[:200])
    print(sid)


if __name__ == "__main__":
    for n in sys.argv[1:]:
        main(n)
