#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Create a semver tag for release automation.

Usage:
  scripts/release.sh [--version X.Y.Z] [--push]

Workflow (recommended):
  1. Prep on release/x.y.z, merge into main when ready
  2. Run this script from main to bump versions and create a release commit
  3. With --push, push main and then create/push vX.Y.Z
  4. The release workflow runs from the pushed tag

Behavior:
  - Must run on main branch
  - Requires clean working tree
  - Updates version fields in workspace/core/worker/worker-llm/UI manifests
  - Creates release commit `🚀 Release vX.Y.Z`
  - If --version is omitted in a terminal session, prompts for a version with the next patch as default
  - If --version is omitted non-interactively: first release is 0.0.1; otherwise patch-bump from latest vX.Y.Z
  - Creates annotated tag vX.Y.Z
  - With --push: pushes main before pushing the tag
  - Pushes tag when --push is provided
EOF
}

version=""
push_tag=false
release_files=(
  "pyproject.toml"
  "core/pyproject.toml"
  "worker/pyproject.toml"
  "worker-llm/pyproject.toml"
  "ui/package.json"
)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      version="${2:-}"
      shift 2
      ;;
    --push)
      push_tag=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

branch="$(git branch --show-current)"
if [[ "$branch" != "main" ]]; then
  echo "Release tagging is only allowed on main (current: $branch)." >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is not clean. Commit or stash changes before tagging." >&2
  exit 1
fi

git fetch origin main --tags --quiet

local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/main)"
merge_base="$(git merge-base HEAD origin/main)"

if [[ "$local_head" != "$remote_head" ]]; then
  if [[ "$merge_base" == "$remote_head" ]]; then
    echo "Local main is ahead of origin/main; release commit will be pushed with current changes."
  elif [[ "$merge_base" == "$local_head" ]]; then
    echo "Local main is behind origin/main. Pull first." >&2
    exit 1
  else
    echo "Local main has diverged from origin/main. Reconcile history first." >&2
    exit 1
  fi
fi

latest_tag="$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n1)"

suggested_version=""
if [[ -z "$version" ]]; then
  if [[ -z "$latest_tag" ]]; then
    suggested_version="0.0.1"
  else
    base="${latest_tag#v}"
    IFS='.' read -r major minor patch <<<"$base"
    patch="$((patch + 1))"
    suggested_version="${major}.${minor}.${patch}"
  fi

  if [[ -t 0 ]]; then
    read -r -p "Release version [${suggested_version}]: " prompted_version
    version="${prompted_version:-$suggested_version}"
  else
    version="$suggested_version"
  fi
fi

version="${version#v}"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version '$version'. Use semantic version format X.Y.Z." >&2
  exit 1
fi

tag="v${version}"

if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  echo "Tag ${tag} already exists." >&2
  exit 1
fi

update_version_file() {
  local file="$1"
  python3 - "$file" "$version" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
text = path.read_text()

if path.suffix == ".json":
    data = json.loads(text)
    data["version"] = version
    path.write_text(json.dumps(data, indent=2) + "\n")
else:
    updated, count = re.subn(
        r'(?m)^version = "[^"]+"$',
        f'version = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Could not update version in {path}")
    path.write_text(updated)
PY
}

for file in "${release_files[@]}"; do
  update_version_file "$file"
done

git add "${release_files[@]}"
git commit -m "🚀 Release ${tag}"
echo "Created release commit for ${tag}"

if [[ "$push_tag" == "true" ]]; then
  git push origin main
  echo "Pushed main to origin"
fi

git tag -a "$tag" -m "Release $tag"
echo "Created tag $tag"

if [[ "$push_tag" == "true" ]]; then
  git push origin "$tag"
  echo "Pushed tag $tag"
else
  echo "Tag not pushed. Run: git push origin $tag"
fi
