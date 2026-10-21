#!/usr/bin/env bash
# inject-state.sh — SessionStart / PostCompact hook
# このセッションが project-hub の hub（stdin の session_id が hub.json と一致）のときだけ、
# state.md と、その生成後に増えた journal の件数を注入する。それ以外のセッションでは黙る

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "project-hub:inject-state"

INPUT=$(safe_hook_input)
ROOT="${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}"
[ -d "$ROOT" ] || safe_hook_error NotFound "no project-hub root"

# hub を 1 つも持たないマシン（大半のセッション）では python を起動しない
HAS_HUB=0
for f in "$ROOT"/*/hub.json; do
  if [ -f "$f" ]; then
    HAS_HUB=1
    break  # mutation-ok: continue でも HAS_HUB=1 のまま残り結果は同じ（break は走査を打ち切るだけ）
  fi
done
[ "$HAS_HUB" = 1 ] || safe_hook_error NotFound "no hub.json under ${ROOT}"
command -v python3 >/dev/null 2>&1 || safe_hook_error Dependency "python3 not installed"

printf '%s' "$INPUT" | PROJECT_HUB_DIR="$ROOT" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hub.py" inject
