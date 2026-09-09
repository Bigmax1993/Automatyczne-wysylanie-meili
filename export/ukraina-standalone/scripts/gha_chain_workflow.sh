#!/usr/bin/env bash
set -euo pipefail
# Uruchamia kolejny workflow w łańcuchu pipeline GU.
# Użycie: gha_chain_workflow.sh "Nazwa workflow" [pole=wartość ...]
WF="${1:?workflow name required}"
shift
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}"
args=()
for kv in "$@"; do
  args+=(-f "$kv")
done
echo "Chain: uruchamiam workflow '$WF' w $REPO"
gh workflow run "$WF" -R "$REPO" "${args[@]}"
