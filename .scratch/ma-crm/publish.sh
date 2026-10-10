#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
REPO=serge-merlin-innovation/testing-crm-creation
MAP=issues/numbers.txt
touch "$MAP"
n=$(jq length issues/manifest.json)
for i in $(seq 0 $((n-1))); do
  key=$(jq -r ".[$i].key" issues/manifest.json)
  if grep -q "^$key " "$MAP"; then continue; fi
  title=$(jq -r ".[$i].title" issues/manifest.json)
  file=$(jq -r ".[$i].file" issues/manifest.json)
  blockers=$(jq -r ".[$i].blocked[]" issues/manifest.json)
  bl=""
  for b in $blockers; do
    num=$(awk -v k="$b" '$1==k{print $2}' "$MAP")
    bl+="- #$num"$'\n'
  done
  [ -z "$bl" ] && bl="- None (can start immediately)"
  body=$(python3 -c 'import sys;print(open(sys.argv[1]).read().replace("{{BLOCKED_BY}}", sys.argv[2].rstrip()))' "$file" "$bl")
  url=$(gh issue create -R "$REPO" --title "$title" --label ready-for-agent --body "$body")
  num=${url##*/}
  echo "$key $num" >> "$MAP"
  echo "$key -> #$num"
  for b in $blockers; do
    bnum=$(awk -v k="$b" '$1==k{print $2}' "$MAP")
    bid=$(gh api repos/$REPO/issues/$bnum --jq .id)
    gh api --method POST repos/$REPO/issues/$num/dependencies/blocked_by -F issue_id=$bid >/dev/null 2>&1 || echo "  dependency API failed for #$num <- #$bnum (body has Blocked by)"
  done
done
