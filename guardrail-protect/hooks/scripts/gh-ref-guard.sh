#!/usr/bin/env bash
# gh-ref-guard.sh
#
# `gh` で issue / PR に本文を書き込むとき、本文中の
# ``` `<file>.md ## <見出し>` ``` 参照のうち**見出しが実在しないもの**を検出して
# exit 2 でブロックする。
#
# **ファイルパスの実在は検証しない。** 実測でパス実在検証は真の検出 0 件・偽陽性 41 件
# だった。測定の一次記録・母集団の限界・既知の偽陽性は
# `docs/session-reports/2026-08-28-gh-ref-guard-measurement.md` を読むこと。
# 検出ロジックは `detect-stale-refs.py` の docstring。
#
# 本文の取り出しはコマンド文字列をそのまま検査する方式（参照はバッククォート付きで
# 現れるため `--body` / `-b` / heredoc を覆う）。`--body-file` / `-F` は内容を読み足す。
# **コマンド置換・変数展開・`-F -`（stdin）で渡された本文は検査されない。**
#
# fail-loud: jq / python3 が無い場合は silent skip せず Unexpected として stderr に
# 通知する（ガードが黙って無効化されるのを防ぐ / `pre-commit-guard.sh` と同じ方針）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:gh-ref-guard"

command -v jq      >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; guard cannot inspect command"
command -v python3 >/dev/null 2>&1 || safe_hook_error Unexpected "python3 not installed; guard cannot inspect references"

input=$(safe_hook_input)
# jq の失敗を暗黙の fail-open にしない（`pre-commit-guard.sh` と同じ理由 / issue #178）
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)

# **matcher 単独に依存しない**（CLAUDE.md Gotchas の二重ゲート規約）。ただし
# tool_name が無いときは弾かない（payload に載せない CC 版でガードごと無効化しない）
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi

[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

# 安価な事前フィルタ: `gh` の文字列を含まなければ即 exit 0（トークン判定より先に安く弾く）
case "$cmd" in
  *gh*) ;;
  *) exit 0 ;;
esac

# **トークン境界で判定する。** 部分文字列 glob（`*gh*issue*create*`）は
# `hi(gh)light ... issue ... create` のような **gh を呼んでいないコマンドを block** する
is_write=$(printf '%s' "$cmd" | python3 -c '
import shlex, sys
WRITE = {"create", "comment", "edit", "close", "review", "reopen"}
try:
    tokens = shlex.split(sys.stdin.read())
except ValueError:
    # クォートが閉じていない。トークン化できないので検査側に倒す（黙って外さない）
    print("1"); raise SystemExit
for i, tok in enumerate(tokens):
    if tok != "gh":
        continue
    rest = [t for t in tokens[i + 1:] if not t.startswith("-")]
    if len(rest) >= 2 and rest[0] in ("issue", "pr") and rest[1] in WRITE:
        print("1"); raise SystemExit
print("0")
' 2>/dev/null || printf '1')

[ "$is_write" = "1" ] || exit 0

# repo root が取れないなら判定しない（git 管理下でなければ参照も解決できない）
repo_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
[ -z "$repo_root" ] && safe_hook_error NotFound "not inside a git repository"

# 検査対象 = コマンド文字列 + `--body-file` / `-F` が指すファイルの中身
body_file_contents=$(printf '%s' "$cmd" | python3 -c '
import shlex, sys
cmd = sys.stdin.read()
try:
    tokens = shlex.split(cmd)
except ValueError:      # クォートが閉じていない等。読み足しは諦めてコマンド本体だけ見る
    tokens = []
out = []
for i, tok in enumerate(tokens):
    path = None
    if tok in ("--body-file", "-F") and i + 1 < len(tokens):
        path = tokens[i + 1]
    elif tok.startswith("--body-file="):      # `=` 形式も gh は受け付ける
        path = tok.split("=", 1)[1]
    if path is None or path == "-":           # `-` は stdin。読めないので検査対象外
        continue
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            out.append(fh.read())
    except OSError:
        # 読めない（相対パスが hook の cwd から解決できない等）。読み足しは諦めるが、
        # コマンド文字列本体は引き続き検査される
        pass
print("\n".join(out))
' 2>/dev/null || true)

# **`2>/dev/null || true` を付けないこと。** 検出器は「常に exit 0」を契約にしているので、
# 非ゼロは契約違反＝異常であり、そこを握り潰すと**ガードが黙って無効化される**
# （実測: 検出器を消すと rc=0 / 出力 0 バイトで、既存 `pre-commit-guard.sh` が同条件で
# 出す `Unexpected` 通知が消えていた）。代入は `&& rc=0 || rc=$?` の形にする
# （`VAR="$(...)"; RC=$?` は `set -e` 下で ERR trap を踏む / CLAUDE.md Gotchas）
detection=$(printf '%s\n%s' "$cmd" "$body_file_contents" \
  | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-stale-refs.py" "$repo_root") && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
  safe_hook_error Unexpected "stale-ref detector failed (rc=${rc})"
fi

if [ -n "$detection" ]; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to publish a reference to a heading that does not exist

以下の参照は、ファイルは実在するのに**その見出しが無い**:
${detection}

公開後の訂正コストが高いため、書き込む前に引用元を開いて見出しを確認すること。
節番号のずれ（分冊で番号が引き継がれている / 節が増減した）が典型。

判定は見出しの実在のみで、パスの実在は見ていない。
誤検出だと判断する場合は参照の書き方を変えるか（複数節をまとめて指す形・
バッククォートの外に出す形は判定対象外）、guardrail-protect を一時的に
無効化する（プラグイン単位。commit 迂回ガードも同時に外れる点に注意）。
誤検出は GitHub issue に報告してほしい — 既知の偽陽性は README の制限事項にある。

Tool: ${tool_name}
EOF
  exit 2
fi

exit 0
