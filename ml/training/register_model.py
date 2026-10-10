"""Register a newly trained model only if it is not worse than the production one.

    python ml/training/register_model.py <model_name> <file> <metric> <test_value> [notes]

The production entry is replaced only when test_value >= the current test score for the same metric; otherwise the
candidate is recorded under 'rejected' with both scores, and the production file is untouched.
"""
import json
import os
import sys
from datetime import date

REG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models", "registry.json")


def main(name, file, metric, value, notes=""):
    reg = json.load(open(REG, encoding="utf-8"))
    cur = next((m for m in reg["models"] if m["model_name"] == name), None)
    old = ((cur or {}).get("test_score") or {}).get(metric)
    entry = dict(model_name=name, file=file, version=date.today().isoformat(), training_date=date.today().isoformat(),
                 test_score={metric: value}, notes=notes)
    if old is not None and value < old:
        reg.setdefault("rejected", []).append(dict(entry, reason=f"{metric} {value} < production {old}"))
        print(f"REJECTED: {metric} {value} < production {old}; production model kept")
    else:
        reg["models"] = [m for m in reg["models"] if m["model_name"] != name] + [entry]
        print(f"registered {name}: {metric} {value} (previous {old})")
    json.dump(reg, open(REG, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), " ".join(sys.argv[5:]))
