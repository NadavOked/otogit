# tools/agents/watch/actions_used.py
import re

USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(.*)$")


def parse_uses(line):
    """Return the parsed form of one `uses:` line, or None if it is not one."""
    match = USES_RE.match(line)
    if not match:
        return None

    val = match.group(1).rstrip("\r\n")

    # Strip comment and surrounding quotes
    raw_val = None
    if val.startswith('"'):
        # Double-quoted string
        end_idx = val.find('"', 1)
        if end_idx != -1:
            raw_val = val[1:end_idx]
    elif val.startswith("'"):
        # Single-quoted string
        end_idx = val.find("'", 1)
        if end_idx != -1:
            raw_val = val[1:end_idx]

    if raw_val is None:
        # Not quoted, strip comment starting with #
        if "#" in val:
            val = val.split("#", 1)[0]
        raw_val = val.strip()

    if not raw_val:
        return {
            "kind": "unknown",
            "owner": None,
            "repo": None,
            "path": None,
            "ref": None,
            "raw": raw_val,
        }

    if raw_val.startswith("./"):
        return {
            "kind": "local",
            "owner": None,
            "repo": None,
            "path": None,
            "ref": None,
            "raw": raw_val,
        }

    if raw_val.startswith("docker://"):
        return {
            "kind": "docker",
            "owner": None,
            "repo": None,
            "path": None,
            "ref": None,
            "raw": raw_val,
        }

    if "@" in raw_val:
        action_part, ref = raw_val.split("@", 1)
        parts = action_part.split("/")
        if len(parts) >= 2 and parts[0] and parts[1]:
            owner = parts[0]
            repo = parts[1]
            path = "/".join(parts[2:]) if len(parts) > 2 else None
            return {
                "kind": "remote",
                "owner": owner,
                "repo": repo,
                "path": path,
                "ref": ref,
                "raw": raw_val,
            }

    return {
        "kind": "unknown",
        "owner": None,
        "repo": None,
        "path": None,
        "ref": None,
        "raw": raw_val,
    }


def actions_used(files):
    """Return (inventory, unparsed) for a set of workflow files."""
    if not files:
        return ([], [])

    unparsed = []
    # Key: (owner, repo, path) -> {"refs": set(), "files": set()}
    remote_map = {}

    for f in files:
        if (
            not isinstance(f, dict)
            or "name" not in f
            or not isinstance(f.get("text"), str)
        ):
            file_name = f.get("name", "unknown") if isinstance(f, dict) else "unknown"
            unparsed.append(
                {"file": file_name, "line": 0, "text": "", "kind": "bad-file"}
            )
            continue

        file_name = f["name"]
        lines = f["text"].splitlines()

        for idx, line_text in enumerate(lines, 1):
            parsed = parse_uses(line_text)
            if parsed is None:
                continue

            kind = parsed["kind"]
            if kind == "remote":
                key = (parsed["owner"], parsed["repo"], parsed["path"])
                if key not in remote_map:
                    remote_map[key] = {"refs": set(), "files": set()}
                remote_map[key]["refs"].add(parsed["ref"])
                remote_map[key]["files"].add(file_name)
            else:
                unparsed.append(
                    {
                        "file": file_name,
                        "line": idx,
                        "text": line_text.strip(),
                        "kind": kind,
                    }
                )

    inventory = []
    for (owner, repo, path), data in remote_map.items():
        inventory.append(
            {
                "owner": owner,
                "repo": repo,
                "path": path,
                "refs": tuple(sorted(data["refs"])),
                "files": tuple(sorted(data["files"])),
            }
        )

    inventory.sort(
        key=lambda x: (x["owner"], x["repo"], x["path"] or "", x["refs"], x["files"])
    )

    return (inventory, unparsed)
