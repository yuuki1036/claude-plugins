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
#   session-start  SessionStart。古い状態ファイルを消し、resume / compact / fork のときに知らせる。
#                  fork のときは状態ファイルを作って印を立て、transcript が既にあればその場で親の会話から版を拾う
#
# 状態: ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugin-manager/sessions/<session_id>.json
# UserPromptSubmit は毎回の発言で走るので、このセッションの状態ファイルが無ければ python を起動しない
# （transcript が親から写された fork 先だけは起動する）。状態ファイルの候補があれば、写されたかに関わらず
# python を起動するので、transcript の先頭も読まない。
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
    # subagent・in-process teammate の Read も agent_id 付き・main と同じ session_id で届き、main の状態ファイルに
    # 記録される。ここでは黙らせない（プロンプトに本文を貼らずパスだけ渡して agent に読ませる使い方では、agent_id で
    # 外すと agent が読んだ skill の記録が抜ける）。記録済みの版を上書きしないのは stale_skill.py の record が
    # payload の agent_id で決める（JSON として読むので、読んだファイルの中身の字面には当たらない / GitHub issue #542）。
    # 残る限界: 記録はセッション単位で、agent ごとには持たない。sub が先に読んだ版は main が読んでいなくても main の
    # 記録になり、記録済みの後に sub だけが新しい版を読んでも main の記録は古いまま
    if [[ "$INPUT" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"Skill\" ]]; then
      :
    elif [[ "$INPUT" == *'/plugins/cache/'* ]]; then
      :
    else
      safe_hook_error NotFound "not a plugin read"
    fi
    ;;
  prompt|compact|session-start)
    # fork 先は状態ファイルがまだ無いので、ここで止めずに python に作らせる（GitHub issue #487）。
    # 入れ子のオブジェクトの source に当たっても、python が payload の source で判定し直す
    FORK=0
    if [ "$MODE" = "session-start" ] && [[ "$INPUT" =~ \"source\"[[:space:]]*:[[:space:]]*\"fork\" ]]; then
      FORK=1
    fi
    # subagent が compaction したときも、この hook は agent_id 付きで走る（CC 2.1.323+ / GitHub issue #486）。
    # main 向けの通知を sub の文脈に入れないよう、agent_id があれば黙る（sub の payload の session_id は main と同じなので、main の状態ファイルにも触らない）。
    # payload の文字列値に出る "agent_id" は JSON で `\"` にエスケープされるので当たらない
    if [[ "$INPUT" =~ \"agent_id\"[[:space:]]*:[[:space:]]*\"[^\"]+\" ]]; then
      safe_hook_error NotFound "subagent compaction"
    fi
    # payload の入れ子のオブジェクトにも session_id のキーがありうるので、出現をすべて候補にする
    # （最初の 1 件だけだと、自分より先に置かれた入れ子の id と取り違える）。発言の本文の字面は
    # JSON で `\"` にエスケープされるので当たらない（GitHub issue #465）。
    # どれが自分のものかは python が payload の session_id で決める（mtime の更新もそちら）。
    # sessions dir が無ければ候補の状態ファイルも無いので、grep / sed を起動しない
    KEEP=()
    if [ -d "$DIR" ]; then
      while IFS= read -r sid; do
        if [ -n "$sid" ] && [ -f "${DIR}/${sid}.json" ]; then
          KEEP+=(! -name "${sid}.json")
        fi
      done < <(grep -oE '"session_id"[[:space:]]*:[[:space:]]*"[A-Za-z0-9_-]+"' <<<"$INPUT" | sed -E 's/.*"([A-Za-z0-9_-]+)"$/\1/' || true)
    fi
    # デスクトップアプリの fork は resume として届き、状態ファイルも無い。transcript の先頭の行の
    # sessionId がファイル名の id と違えば（親から写された transcript）、python に見分けさせる
    # （判定し直しは stale_skill.py の copied_transcript。先頭の数行しか読まない / GitHub issue #517）。
    # transcript のファイル名は session_id と同じ前提（python は payload の session_id で判定し直す）。
    # 行数は stale_skill.py の COPIED_HEAD_LINES と揃える。KEEP が空でなければ FORK に関わらず python を起動する
    # （下の 2 つの判定）ので、transcript を開くのは KEEP が空のときだけ（毎回の発言で head を起動しない / GitHub issue #542）。
    # 入れ子の id だけが KEEP に当たり自分の状態ファイルが無い回は、python が copied_transcript で見分ける。
    # ファイル名は 2 回目の =~ が BASH_REMATCH を上書きする前に取る（basename を起動しない）
    if [ "${#KEEP[@]}" -eq 0 ] && [ "$FORK" = 0 ] && [ "$MODE" != "compact" ] \
      && [[ "$INPUT" =~ \"transcript_path\"[[:space:]]*:[[:space:]]*\"([^\"]+\.jsonl)\" ]]; then
      TP="${BASH_REMATCH[1]}"
      if [ -f "$TP" ]; then
        NAME="${TP##*/}"
        HEAD=$(head -n 5 "$TP" 2>/dev/null || true)
        if [[ "$HEAD" =~ \"sessionId\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9_-]+)\" ]] \
          && [ "${BASH_REMATCH[1]}" != "${NAME%.jsonl}" ]; then
          FORK=1
        fi
      fi
    fi
    [ "$FORK" = 1 ] || [ -d "$DIR" ] || safe_hook_error NotFound "no sessions dir"
    if [ "$MODE" = "session-start" ]; then
      # -mtime は 24 時間単位で切り捨てるので +13 で「14 日以上前」。候補は消さない
      # （14 日ぶりに resume したセッションの記録を、通知する前に消さない）。書きかけの tmp も消す
      find "$DIR" -maxdepth 1 -type f \( -name '*.json' -o -name '.*.tmp' \) -mtime +13 ${KEEP[@]+"${KEEP[@]}"} -delete 2>/dev/null || true
    fi
    [ "$FORK" = 1 ] || [ "${#KEEP[@]}" -gt 0 ] || safe_hook_error NotFound "no record for this session"
    ;;
  *)
    safe_hook_error Validation "unknown mode: ${MODE}"
    ;;
esac

command -v python3 >/dev/null 2>&1 || safe_hook_error Dependency "python3 not installed"

printf '%s' "$INPUT" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/stale_skill.py" "$MODE"
