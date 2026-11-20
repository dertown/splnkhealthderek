#!/usr/bin/env bash
# Build a Splunk Cloud .spl (bin/derekaiping.py only, no local/, search-head only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ID="splunk_exec_health"
DIST="$ROOT/dist"
VERSION="$(awk -F= '
  /^\[launcher\]/ { in_launcher=1; next }
  /^\[/ { in_launcher=0 }
  in_launcher && /^version[[:space:]]*=/ {
    gsub(/[[:space:]]/, "", $2)
    print $2
    exit
  }
' "$ROOT/default/app.conf")"

if [[ -z "$VERSION" ]]; then
  echo "Could not read version from default/app.conf" >&2
  exit 1
fi

python3 "$ROOT/tools/validate_keys.py"

python3 - <<PY
import json
from pathlib import Path
root = Path("$ROOT")
manifest = json.loads((root / "app.manifest").read_text())
app_conf = (root / "default" / "app.conf").read_text()
assert manifest["info"]["id"]["name"] == "$APP_ID"
assert manifest["info"]["id"]["version"] == "$VERSION"
assert "targetWorkloads" in manifest and "_search_heads" in manifest["targetWorkloads"]
assert "supportedDeployments" in manifest
assert "[package]" in app_conf and "id = $APP_ID" in app_conf
assert "sc_admin" in (root / "metadata" / "default.meta").read_text()
print("manifest and app.conf versions match $VERSION")
PY

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
mkdir -p "$DIST" "$STAGING/$APP_ID"

rsync -a \
  --exclude '.git' --exclude '.gitignore' --exclude 'dist' --exclude 'local' \
  --exclude 'metadata/local.meta' --exclude '.DS_Store' --exclude '__pycache__' \
  --exclude '*.pyc' --exclude '*.tgz' --exclude '*.spl' --exclude 'tools' \
  --exclude '.idea' --exclude '.vscode' --exclude '.venv' \
  --exclude 'lookups/dq_agent_ai_config.csv' --exclude 'lookups/dq_agent_approvals.csv' \
  "$ROOT/" "$STAGING/$APP_ID/"

find "$STAGING/$APP_ID" \( -name '.DS_Store' -o -name '._*' -o -name '*.pyc' \) -delete
find "$STAGING/$APP_ID" -type f -exec chmod 644 {} \;
find "$STAGING/$APP_ID" -type d -exec chmod 755 {} \;

bad=$(find "$STAGING/$APP_ID" -type f \( -name '*.py' -o -name '*.pyc' \) ! -path "$STAGING/$APP_ID/bin/derekaiping.py" ! -path "$STAGING/$APP_ID/bin/healthdash.py")
if [[ -n "$bad" ]]; then
  echo "Package may contain only bin/derekaiping.py and bin/healthdash.py as Python" >&2
  echo "$bad" >&2
  exit 1
fi
if [[ ! -f "$STAGING/$APP_ID/bin/derekaiping.py" || ! -f "$STAGING/$APP_ID/bin/healthdash.py" ]]; then
  echo "bin/derekaiping.py is missing from the package" >&2
  exit 1
fi
if [[ -d "$STAGING/$APP_ID/local" || -d "$STAGING/$APP_ID/tools" ]]; then
  echo "Cloud package must not contain local/ or tools/" >&2
  exit 1
fi

export COPYFILE_DISABLE=1
export COPY_EXTENDED_ATTRIBUTES_DISABLE=1
OUT_TGZ="$DIST/${APP_ID}-${VERSION}.tgz"
OUT_SPL="$DIST/${APP_ID}-${VERSION}.spl"
tar -czf "$OUT_TGZ" -C "$STAGING" "$APP_ID"
cp "$OUT_TGZ" "$OUT_SPL"
cp "$OUT_SPL" "$DIST/latest.spl"

python3 - <<PY
import tarfile
from pathlib import Path
path = Path("$OUT_SPL")
disallowed = []
with tarfile.open(path, "r:gz") as tar:
    names = tar.getnames()
    for member in tar.getmembers():
        name = member.name
        if (name.endswith(".py") and name not in ("splunk_exec_health/bin/derekaiping.py", "splunk_exec_health/bin/healthdash.py")) or "/tools/" in name + "/" or "/local/" in name + "/" or "/._" in name or name.endswith(".git"):
            disallowed.append(name)
        if member.isfile() and (member.mode & 0o111):
            disallowed.append(f"{name} (executable)")
        if member.isfile() and (member.mode & 0o002):
            disallowed.append(f"{name} (world-writable)")
if disallowed:
    raise SystemExit("Disallowed Cloud package entries:\\n" + "\\n".join(disallowed))
required = [
    "splunk_exec_health/app.manifest",
    "splunk_exec_health/LICENSE",
    "splunk_exec_health/README.md",
    "splunk_exec_health/default/app.conf",
    "splunk_exec_health/metadata/default.meta",
    "splunk_exec_health/bin/derekaiping.py",
]
missing = [item for item in required if item not in names]
if missing:
    raise SystemExit("Missing required Cloud files: " + ", ".join(missing))
for runtime_csv in ("dq_agent_ai_config.csv", "dq_agent_approvals.csv"):
    if "splunk_exec_health/lookups/" + runtime_csv in names:
        raise SystemExit(runtime_csv + " must not ship in the package; runtime data lives in KV Store and an upgrade would wipe it")
print(f"packaged {path} ({path.stat().st_size} bytes, {len(names)} entries)")
PY

# GitHub dist/ keeps latest.spl plus the two newest versioned packages. Older
# .spl files stay on this machine and stay gitignored.
python3 - <<PY
import re
from pathlib import Path
root = Path("$ROOT")
dist = root / "dist"
app_id = "$APP_ID"
packs = []
for path in dist.glob(app_id + "-*.spl"):
    match = re.fullmatch(re.escape(app_id) + r"-(\d+(?:\.\d+)*)\.spl", path.name)
    if match:
        packs.append((tuple(int(part) for part in match.group(1).split(".")), path))
packs.sort()
keep = [path for _, path in packs[-2:]]
keep_names = [path.name for path in keep]
gitignore = root / ".gitignore"
lines = [line for line in gitignore.read_text(encoding="utf-8").splitlines()
         if not line.startswith("!dist/splunk_exec_health-")]
if "!dist/latest.spl" not in lines:
    try:
        at = next(i for i, line in enumerate(lines) if line == "*.spl") + 1
    except StopIteration:
        at = len(lines)
    lines.insert(at, "!dist/latest.spl")
at = next(i for i, line in enumerate(lines) if line == "!dist/latest.spl")
for name in keep_names:
    at += 1
    lines.insert(at, "!dist/" + name)
gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
rows = ["| [latest.spl](latest.spl) | Current Splunk Health Derek+ Cloud package |"]
rows += [f"| [{name}]({name}) | Version {name[len(app_id)+1:-4]} |" for name in keep_names]
(dist / "README.md").write_text(
    "# Dist\\n\\n"
    "Download the packaged app from this folder. \`latest.spl\` is always the current build. "
    "GitHub keeps that file plus the **last two versions**. Older local builds stay on the machine that ran \`bash tools/package.sh\`.\\n\\n"
    "| File | What it is |\\n| --- | --- |\\n" + "\\n".join(rows) + "\\n\\n"
    "Install: **Apps → Manage apps → Install app from file**, then upload the \`.spl\`.\\n",
    encoding="utf-8",
)
print("git dist keeps: latest.spl " + " ".join(keep_names))
PY
