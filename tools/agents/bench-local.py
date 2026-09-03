#!/usr/bin/env python3
"""מודד את המודלים המקומיים וכותב את התוצאה ל-providers.json.

**למה זה כלי ולא טבלה.** המספרים תלויים במכונה. הבעלים אמר את זה בצורה
הכי חדה שאפשר: הסקתי מקובץ ישן שיש לו GTX 1650, והוא ענה "אין לי
היום, כבר אין". מספר שנכתב ביד מתיישן **בשקט** — הוא ממשיך להיראות
כמו עובדה.

לכן: הריצו את זה, אל תערכו את הערכים. כל רשומה נושאת `measured_on`
ואת פרופיל המכונה שנמדד עליה, כדי שיהיה אפשר לדעת שהיא כבר לא תקפה.

    python tools/agents/bench-local.py            # מדפיס בלבד
    python tools/agents/bench-local.py --write    # כותב ל-providers.json

**נכשל סגור:** שרת שאינו עונה, מודל שנכשל, או תשובה ריקה — כולם
נרשמים ככישלון מפורש ולא כאפס. "לא הצלחנו למדוד" אינו "איטי".
"""
import argparse
import datetime as dt
import json
import platform
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:11434"
HERE = Path(__file__).resolve().parent
PROVIDERS = HERE / "providers.json"

# משימת הסיווג היא המשימה שהשכבה המקומית נועדה לה, ולכן היא המדד.
PROMPT = (
    "You classify GitHub issues for a PXE imaging server project.\n"
    "Answer with ONE word only: docs, code, or infra.\n\n"
    "Issue title: docs/grub-generator.md contradicts itself - the table "
    "still lists a boot timeout that was removed from the code.\n\nAnswer:")
EXPECTED = "docs"


def machine_profile():
    """מה שאפשר לזהות בלי להניח. שדה שלא זוהה נשאר null, לא מנוחש."""
    gpu = None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL)
        if out.returncode == 0 and out.stdout.strip():
            gpu = out.stdout.strip().splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError):
        gpu = None
    return {"os": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "processor": platform.processor()
            or None, "gpu": gpu}


def installed():
    try:
        with urllib.request.urlopen(HOST + "/api/tags", timeout=15) as r:
            return [m["name"] for m in json.loads(r.read())["models"]]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        raise SystemExit("‏ollama אינו עונה על %s (%s). לא ממשיכים — "
                         "'לא הצלחנו למדוד' אינו 'אין מודלים'."
                         % (HOST, type(exc).__name__))


def bench(model):
    body = json.dumps({"model": model, "prompt": PROMPT, "stream": False,
                       "options": {"num_predict": 40, "temperature": 0.2}}
                      ).encode("utf-8")
    req = urllib.request.Request(HOST + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode("utf-8"))
    wall = round(time.time() - t0, 1)
    ev, ed = d.get("eval_count") or 0, (d.get("eval_duration") or 0) / 1e9
    ans = (d.get("response") or "").strip().lower()
    if not ans:
        raise ValueError("תשובה ריקה")
    return {"tokens_per_second": round(ev / ed, 1) if ed else None,
            "seconds_to_answer": wall,
            "load_seconds": round((d.get("load_duration") or 0) / 1e9, 1),
            "classified_correctly": EXPECTED in ans}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="לכתוב ל-providers.json במקום להדפיס בלבד")
    ap.add_argument("models", nargs="*", help="ברירת מחדל: כל המותקנים")
    args = ap.parse_args()

    models = args.models or installed()
    stamp = dt.date.today().isoformat()
    profile = machine_profile()
    print("מכונה: %s" % json.dumps(profile, ensure_ascii=False))
    results, failed = {}, []
    for m in models:
        try:
            r = bench(m)
        except Exception as exc:                      # noqa: BLE001
            failed.append((m, type(exc).__name__))
            print("  %-24s נכשל: %s" % (m, type(exc).__name__))
            continue
        r["measured_on"] = stamp
        r["measured_gpu"] = profile["gpu"]
        results[m] = r
        print("  %-24s %6s tok/s  %5ss  טעינה %ss  סיווג %s"
              % (m, r["tokens_per_second"], r["seconds_to_answer"],
                 r["load_seconds"], "✓" if r["classified_correctly"] else "✗"))

    if failed:
        print("\n%d מודלים נכשלו ואינם נרשמים כאיטיים — הם נרשמים "
              "כלא-נמדדו." % len(failed))
    if not args.write:
        return 0
    if not results:
        raise SystemExit("אף מדידה לא הצליחה — לא כותבים.")

    data = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    oll = data["providers"]["ollama"]
    oll["machine_profile"] = profile
    oll["benchmark_tool"] = "tools/agents/bench-local.py"
    for name, r in results.items():
        cur = oll["models"].get(name, {})
        cur.update({"rpm": None, "rpd": None, "source": "n/a"})
        cur.update(r)
        oll["models"][name] = cur
    data["updated"] = stamp
    PROVIDERS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print("\nנכתב %s — %d מודלים" % (PROVIDERS.name, len(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
