#!/usr/bin/env bash
# notify-pending.sh — UserPromptSubmit hook
# このセッションが project-hub の hub（stdin の session_id が hub.json と一致）で、inbox に未取り込みの
# report があるときだけ、取り込むよう促す（GitHub issue #314）。作業側の通知（cross-session message）でも
# lead の発言でも発火するので、通知が届かなかった回も次の発言で拾う。それ以外のセッションでは黙る

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "project-hub:notify-pending"

INPUT=$(safe_hook_input)
ROOT="${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}"
[ -d "$ROOT" ] || safe_hook_error NotFound "no project-hub root"

# 毎回の発言で走るので、このセッションの id を含む hub.json があるときだけ python を起動する。
# 一致の判定（session_id の欄そのものか）は hub.py がする
SID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([A-Za-z0-9_-]*\)".*/\1/p' | head -n 1)
[ -n "$SID" ] || safe_hook_error Validation "no session_id in stdin"
if ! grep -qsF -- "\"${SID}\"" "$ROOT"/*/hub.json; then
  safe_hook_error NotFound "this session is not a hub"
fi
command -v python3 >/dev/null 2>&1 || safe_hook_error Dependency "python3 not installed"

printf '%s' "$INPUT" | PROJECT_HUB_DIR="$ROOT" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hub.py" pending-hint
