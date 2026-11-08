#!/usr/bin/env bash
# stale-skill.sh — PostToolUse / UserPromptSubmit / PostCompact / SessionStart hook（GitHub issue #416）
#
# 長く動くセッションが、プラグインの更新後も最初に読んだ版の SKILL.md の手順で進み続けないように、
# 読んだ版を記録し、インストール済みの版と違えば読み直すよう注入する。判定と文面は stale_skill.py。
#
# モード（hooks.json の args で渡す）:
#   record         PostToolUse(Read|Skill)。読んだ版を記録する。何も出力しない
#   prompt         UserPromptSubmit。まだ知らせていない更新を知らせる
#   compact        PostCompact。compaction で消えた通知をもう一度出す
#   session-start  SessionStart。古い状態ファイルを消し、resume / compact のときだけ知らせる
#
# 状態: ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugin-manager/sessions/<session_id>.json
# UserPromptSubmit は毎回の発言で走るので、このセッションの状態ファイルが無ければ python を起動しない。
# SessionStart では 14 日以上触れられていない状態ファイルを消す

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "plugin-manager:stale-skill"

MODE="${1:-}"
INPUT=$(safe_hook_input)
# 置き場所と session_id の文字種は stale_skill.py（config_dir / SID_RE）と揃える
DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugin-manager/sessions"

# 前段の判定はパイプを使わない。PostToolUse(Read) の stdin は読んだファイルの中身を含んで大きく、
# `printf | grep -q` は grep が先に終わると printf が SIGPIPE で落ち、pipefail で偽になって記録を取りこぼす
case "$MODE" in
  record)
    if [[ "$INPUT" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"Skill\" ]]; then
      :
    elif [[ "$INPUT" == *'/plugins/cache/'* ]]; then
      :
    else
      safe_hook_error NotFound "not a plugin read"
    fi
    ;;
  prompt|compact|session-start)
    [ -d "$DIR" ] || safe_hook_error NotFound "no sessions dir"
    # 発言の本文に session_id の字面が入ることがあるので、出現をすべて候補にする。
    # どれが自分のものかは python が payload の session_id で決める（mtime の更新もそちら）
    KEEP=()
    while IFS= read -r sid; do
      if [ -n "$sid" ] && [ -f "${DIR}/${sid}.json" ]; then
        KEEP+=(! -name "${sid}.json")
      fi
    done < <(grep -oE '"session_id"[[:space:]]*:[[:space:]]*"[A-Za-z0-9_-]+"' <<<"$INPUT" | sed -E 's/.*"([A-Za-z0-9_-]+)"$/\1/' || true)
    if [ "$MODE" = "session-start" ]; then
      # -mtime は 24 時間単位で切り捨てるので +13 で「14 日以上前」。候補は消さない
      # （14 日ぶりに resume したセッションの記録を、通知する前に消さない）。書きかけの tmp も消す
      find "$DIR" -maxdepth 1 -type f \( -name '*.json' -o -name '.*.tmp' \) -mtime +13 ${KEEP[@]+"${KEEP[@]}"} -delete 2>/dev/null || true
    fi
    [ "${#KEEP[@]}" -gt 0 ] || safe_hook_error NotFound "no record for this session"
    ;;
  *)
    safe_hook_error Validation "unknown mode: ${MODE}"
    ;;
esac

command -v python3 >/dev/null 2>&1 || safe_hook_error Dependency "python3 not installed"

printf '%s' "$INPUT" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/stale_skill.py" "$MODE"
