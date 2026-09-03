#!/usr/bin/env python3
"""מגלה מה אפשר להריץ על המכונה הזאת — ולא מניח כלום.

**למה זה קיים.** נדב עובד לפעמים ממחשב אחר, ולפעמים ממשתמש אחר על
מחשב של העבודה. השאלה "האם אפשר להריץ כאן סוכן" אינה נכונה או לא
נכונה באופן קבוע — היא תלויה במכונה. תשובה שנכתבה ביד מתיישנת
בשקט: הסקתי פעם מקובץ ישן שיש GPU, ונדב ענה "אין לי היום, כבר אין".

**כיצד הוא נכשל.** סגור. כל דבר שלא הצליח להיבדק מדווח כ-`unknown`
ולא כ-`no`. "לא הצלחנו לבדוק" ו"בדקנו ואין" הם שני מצבים שונים,
וכאן ההבדל ביניהם הוא בין "אל תשתמש" לבין "אולי כן".

**מה הוא לא עושה.** לא מדפיס ולא מעתיק אף מפתח. קיום מפתח נבדק
כבוליאני בלבד.

    python tools/agents/probe-machine.py           # קריא לאדם
    python tools/agents/probe-machine.py --json    # לכלים
"""
import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys

UNKNOWN = "unknown"

AGENTS = {
    "codex":  {"bin": "codex",  "home": ".codex"},
    "grok":   {"bin": "grok",   "home": ".grok"},
    "claude": {"bin": "claude", "home": ".claude"},
    "gemini": {"bin": "gemini", "home": ".gemini"},
    "ollama": {"bin": "ollama", "home": ".ollama"},
}
KEY_ENV = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_KEY_1", "GEMINI_KEY_2"),
    "codex":  ("OPENAI_API_KEY",),
    "grok":   ("XAI_API_KEY", "GROK_API_KEY"),
    "claude": ("ANTHROPIC_API_KEY",),
}
REACH = {
    "gemini": ("generativelanguage.googleapis.com", 443),
    "github": ("api.github.com", 443),
    "openai": ("api.openai.com", 443),
    "xai":    ("api.x.ai", 443),
}


def dir_size(path, cap_seconds=8.0):
    """גודל תיקייה. חוזר UNKNOWN אם לא הספיק — לא 0."""
    import time
    t0, total = time.time(), 0
    try:
        for base, _d, names in os.walk(path):
            for n in names:
                try:
                    total += os.path.getsize(os.path.join(base, n))
                except OSError:
                    pass
            if time.time() - t0 > cap_seconds:
                return UNKNOWN
    except OSError:
        return UNKNOWN
    return total


def probe_agents(home):
    out = {}
    for name, spec in AGENTS.items():
        d = os.path.join(home, spec["home"])
        exists = os.path.isdir(d)
        out[name] = {
            "on_path": shutil.which(spec["bin"]) is not None,
            "home_exists": exists,
            "home_bytes": dir_size(d) if exists else 0,
            "key_in_env": any(bool(os.environ.get(k))
                              for k in KEY_ENV.get(name, ())),
        }
    return out


def probe_reach():
    out = {}
    for name, (host, port) in REACH.items():
        try:
            with socket.create_connection((host, port), timeout=6):
                out[name] = True
        except OSError:
            out[name] = False
        except Exception:                              # noqa: BLE001
            out[name] = UNKNOWN
    return out


def probe_local_models():
    try:
        import urllib.request
        # ‏bandit B310 מושתק כאן: כתובת קבועה ל-loopback (‏Ollama
        # המקומי). הבקשה לא יוצאת מהמכונה, ואין בה סוד.
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags",  # nosec B310
                                    timeout=6) as r:
            names = [m["name"] for m in json.loads(r.read())["models"]]
        return {"running": True, "models": sorted(names)}
    except Exception:                                  # noqa: BLE001
        return {"running": False, "models": []}


def probe_install(home):
    """האם בכלל אפשר להתקין כאן. שדה שלא נבדק נשאר unknown."""
    try:
        usage = shutil.disk_usage(home)
        free_gb = round(usage.free / 1e9, 1)
    except OSError:
        free_gb = UNKNOWN
    writable = os.access(home, os.W_OK)
    admin = UNKNOWN
    if platform.system() == "Windows":
        try:
            import ctypes
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:                              # noqa: BLE001
            admin = UNKNOWN
    else:
        try:
            admin = os.geteuid() == 0
        except AttributeError:
            admin = UNKNOWN
    return {"home_writable": writable, "free_gb": free_gb,
            "admin": admin,
            "npm": shutil.which("npm") is not None,
            "pip": shutil.which("pip") is not None
                   or shutil.which("pip3") is not None,
            "git": shutil.which("git") is not None}


def probe_hardware():
    gpu = UNKNOWN
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL)
        gpu = r.stdout.strip().splitlines()[0].strip() if (
            r.returncode == 0 and r.stdout.strip()) else None
    except FileNotFoundError:
        gpu = None            # אין nvidia-smi — כלומר אין GPU של nvidia
    except (OSError, subprocess.SubprocessError):
        gpu = UNKNOWN         # ניסינו ולא הצלחנו — לא "אין"
    return {"os": platform.system(), "release": platform.release(),
            "cpus": os.cpu_count(), "gpu": gpu}


def verdict(a, reach, local, inst):
    """איזו שכבה בשרשרת הניתוב באמת שמישה כאן.

    השרשרת: ollama → gemini → codex/grok → claude. שכבה נכללת רק
    אם **נבדקה ונמצאה זמינה**; `unknown` אינו נחשב זמין.
    """
    usable, why = [], {}
    if local["running"] and local["models"]:
        usable.append("ollama")
    else:
        why["ollama"] = ("‏ollama אינו עונה על 11434"
                         if not local["running"] else "אין מודלים מותקנים")
    if a["gemini"]["key_in_env"] and reach.get("gemini") is True:
        usable.append("gemini")
    else:
        why["gemini"] = ("אין מפתח בסביבה" if not a["gemini"]["key_in_env"]
                         else "אין גישה ל-API")
    for n, host in (("codex", "openai"), ("grok", "xai")):
        if a[n]["on_path"] and reach.get(host) is True:
            usable.append(n)
        else:
            why[n] = ("אינו מותקן" if not a[n]["on_path"]
                      else "אין גישה ל-API")
    if a["claude"]["on_path"]:
        usable.append("claude")
    else:
        why["claude"] = "אינו מותקן"
    can_install = (inst["home_writable"] and inst["npm"] and
                   isinstance(inst["free_gb"], float) and inst["free_gb"] > 3)
    return {"usable_layers": usable, "unusable": why,
            "can_install_more": can_install,
            "note_he": ("שכבה נכללת רק אם נבדקה ונמצאה זמינה. "
                        "‏unknown אינו נחשב זמין.")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    home = os.path.expanduser("~")
    data = {"hardware": probe_hardware(), "install": probe_install(home),
            "agents": probe_agents(home), "reachable": probe_reach(),
            "local_models": probe_local_models()}
    data["verdict"] = verdict(data["agents"], data["reachable"],
                              data["local_models"], data["install"])
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    h, i, v = data["hardware"], data["install"], data["verdict"]
    print("מכונה: %s %s · %s ליבות · GPU: %s"
          % (h["os"], h["release"], h["cpus"],
             h["gpu"] if h["gpu"] else "אין"))
    print("התקנה: כתיבה=%s · פנוי=%s GB · admin=%s · npm=%s · git=%s"
          % (i["home_writable"], i["free_gb"], i["admin"], i["npm"], i["git"]))
    print("\nסוכנים:")
    for n, s in data["agents"].items():
        size = s["home_bytes"]
        size = ("%.0f MB" % (size / 1e6)) if isinstance(size, int) else size
        print("  %-8s ב-PATH=%-5s תיקייה=%-5s גודל=%-9s מפתח=%s"
              % (n, s["on_path"], s["home_exists"], size, s["key_in_env"]))
    print("\nרשת: " + " · ".join("%s=%s" % (k, x)
                                 for k, x in data["reachable"].items()))
    lm = data["local_models"]
    print("מקומי: רץ=%s · %d מודלים" % (lm["running"], len(lm["models"])))
    print("\nשמיש כאן: %s" % (" → ".join(v["usable_layers"]) or "כלום"))
    for k, r in v["unusable"].items():
        print("  ✗ %-8s %s" % (k, r))
    print("אפשר להתקין עוד: %s" % v["can_install_more"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
