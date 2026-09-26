#!/usr/bin/env bash
# adr-write-guard.sh — PreToolUse hook (Write|Edit)
#
# .claude/adr/ に ADR を新規作成するとき、adr スキルの手順を踏んだ形かを検査し、
# 外れていれば exit 2 で止めて理由を返す:
#   1. ファイル名が `<14 桁 timestamp>-<slug>.md` で、frontmatter の id と H1 の id がその timestamp と一致する
#   2. id が現在時刻の 300 秒前から 60 秒後までに入る（スキルは Write の直前に `date +%Y%m%d%H%M%S` を取る）
#   3. テンプレ（skills/adr/references/template.md）の見出しがすべてある
#
# なぜ hook か: スキルを通さず ADR を直接 Write する経路にはスキル本文が届かない。
# 実測（2026-09-24）で既存 9 件中 4 件の id が date を通さない丸め値（秒が 00）、
# 3 件でテンプレの節（適用方法など）が落ちていた。transcript で確認できた 3 件はどれもスキルを通していない。
#
# 検査しないもの（既知の穴）:
#   - 既存ファイルの上書き・Edit（supersede の旧 ADR 更新と、テンプレ以前の既存 ADR の手直しで止めない）
#   - Bash 経由の作成（heredoc・cp・git checkout）。過去の ADR を復元・移植するときの退路でもある
#   - 丸めた時刻から 5 分以内に書かれた id。秒が 00 の id を一律に止める案は、date が偶然 00 秒を
#     返した正規の Write も 60 回に 1 回止めるので採らなかった
#
# 時刻は壁時計どうしで比べる（両方ローカル時刻の文字列を jq の mktime に通す）。Bash ツールの
# シェルと hook のプロセスで TZ が違う・DST をまたぐと整時間ずれる。そのときに取り直しで抜け出せる
# よう、止めるメッセージに hook 側の現在時刻を出し、それを id に使ってよいとする。
#
# **本文をパイプで読まない**: safe-hook は pipefail を張るので、`printf "$CONTENT" | grep -q` の
# ように途中で読むのをやめる相手に流すと、64KB を超える本文で printf が SIGPIPE で死ぬ
# （見出しがあるのに無いと判定する / ERR trap で検査ごと素通りする。どちらも実測）。
# 本文の解析は jq が payload 全体を読んでまとめて行う。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "adr-keeper:adr-write-guard"

command -v jq >/dev/null 2>&1 || safe_hook_error Dependency "jq not installed"

INPUT=$(safe_hook_input)
TOOL_NAME=$(jq -r '.tool_name // empty' <<< "$INPUT" 2>/dev/null || true)
FILE_PATH=$(jq -r '.tool_input.file_path // empty' <<< "$INPUT" 2>/dev/null || true)

case "$TOOL_NAME" in
  Write|Edit) ;;
  *) safe_hook_error Validation "not a Write/Edit: $TOOL_NAME" ;;
esac
[ -n "$FILE_PATH" ] || safe_hook_error Validation "empty file_path"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
case "$FILE_PATH" in
  /*) ABS_PATH="$FILE_PATH" ;;
  *) ABS_PATH="${PROJECT_DIR}/${FILE_PATH}" ;;
esac
# `/./` と `//` を畳む（`.claude/adr/./x.md` で素通りさせない）。パターンと置換は変数で渡す —
# bash 3.2 は置換側の `\/` をバックスラッシュごと残す
SEG_DOT="/./"; SEG_DBL="//"; SEP="/"
while [[ "$ABS_PATH" == *"$SEG_DOT"* ]]; do ABS_PATH="${ABS_PATH//"$SEG_DOT"/$SEP}"; done  # mutation-ok: 反転すると `/./` を含まないパス（ほぼ全件）で置換が空回りして無限ループになる。hook のテストは全件 timeout で落ちるが、変異テスト全体の timeout を超えて TIMEOUT に分類される
while [[ "$ABS_PATH" == *"$SEG_DBL"* ]]; do ABS_PATH="${ABS_PATH//"$SEG_DBL"/$SEP}"; done  # mutation-ok: 上の行と同じ（`//` を含まないパスで無限ループ）

# 対象は `.claude/adr/` 直下の .md だけ（大文字小文字を区別しない FS があるので小文字で比べる）
DIR_LC=$(tr '[:upper:]' '[:lower:]' <<< "$(dirname "$ABS_PATH")")
BASE=$(basename "$ABS_PATH")
BASE_LC=$(tr '[:upper:]' '[:lower:]' <<< "$BASE")
case "$DIR_LC" in
  */.claude/adr) ;;
  *) safe_hook_error Validation "not an ADR path: $FILE_PATH" ;;
esac
case "$BASE_LC" in
  readme.md|index.md) safe_hook_error Validation "index file, not an ADR: $FILE_PATH" ;;
  *.md) ;;
  *) safe_hook_error Validation "not markdown: $FILE_PATH" ;;
esac
if [ -e "$ABS_PATH" ]; then
  safe_hook_error Validation "existing file (overwrite is not checked): $FILE_PATH"
fi

# Write は content、Edit は「無いファイルを old_string 空で作る」ときの new_string を見る
ANALYSIS=$(jq -c --arg tool "$TOOL_NAME" '
  def norm_lines: sub("^\ufeff"; "") | gsub("\r"; "") | split("\n") | map(sub("[ \t]+$"; ""));
  (if $tool == "Write" then (.tool_input.content // "")
   elif ((.tool_input.old_string // "") == "") then (.tool_input.new_string // "")
   else null end) as $c
  | if $c == null then {skip: true} else
      ($c | norm_lines) as $L
      | (if ($L | length) > 0 and $L[0] == "---"
         then ($L[1:] | (index(["---"])) as $e | if $e == null then [] else .[:$e] end)
         else [] end) as $fm
      | ($fm | map(select(test("^id:"))) | .[0] // ""
         | sub("^id:[ \t]*"; "") | sub("[ \t]+#.*$"; "") | gsub("[\"'"'"' \t]"; "")) as $id
      | ($L | map(select(test("^# ADR-[0-9]{14}: "))) | .[0] // ""
         | if . == "" then "" else .[6:20] end) as $h1
      | ["## ステータス", "## コンテキスト / 背景", "## 決定", "## 影響 (Consequences)",
         "## 適用方法 (Enforcement)", "## 検討した代替案", "## 関連"] as $req
      | {skip: false, id: $id, h1: $h1,
         missing: [$req[] as $h | select(($L | index([$h])) == null) | $h]}
    end
' <<< "$INPUT" 2>/dev/null || true)
[ -n "$ANALYSIS" ] || safe_hook_error Validation "payload could not be analyzed"
[ "$(jq -r '.skip' <<< "$ANALYSIS")" = "false" ] || safe_hook_error Validation "Edit on a new file with non-empty old_string"

FM_ID=$(jq -r '.id' <<< "$ANALYSIS")
H1_ID=$(jq -r '.h1' <<< "$ANALYSIS")
PROBLEMS=""
add_problem() { PROBLEMS="${PROBLEMS}  - $1"$'\n'; }

FILE_TS=""
if [[ "$BASE" =~ ^([0-9]{14})-[a-z0-9]+(-[a-z0-9]+)*\.md$ ]]; then
  FILE_TS="${BASH_REMATCH[1]}"
else
  add_problem "ファイル名が \`<YYYYMMDDhhmmss>-<kebab-slug>.md\` の形ではない: ${BASE}"
fi

if [ -z "$FM_ID" ]; then
  add_problem "frontmatter に id が無い"
elif [ -n "$FILE_TS" ] && [ "$FM_ID" != "$FILE_TS" ]; then
  add_problem "frontmatter の id（${FM_ID}）がファイル名の timestamp（${FILE_TS}）と違う"
fi
if [ -z "$H1_ID" ]; then
  add_problem "見出し \`# ADR-<id>: <title>\` が無い"
elif [ -n "$FILE_TS" ] && [ "$H1_ID" != "$FILE_TS" ]; then
  add_problem "見出しの id（${H1_ID}）がファイル名の timestamp（${FILE_TS}）と違う"
fi

NOW_TS=""
if [ -n "$FILE_TS" ]; then
  # ADR_WRITE_GUARD_NOW はテストが境界値を秒単位で測るための差し替え口
  NOW_TS="${ADR_WRITE_GUARD_NOW:-$(date +%Y%m%d%H%M%S)}"
  DIFF=$(jq -n --arg a "$NOW_TS" --arg b "$FILE_TS" \
    'try ((($a|strptime("%Y%m%d%H%M%S")|mktime) - ($b|strptime("%Y%m%d%H%M%S")|mktime))) catch "bad"' 2>/dev/null || echo bad)
  if ! [[ "$DIFF" =~ ^-?[0-9]+$ ]]; then
    add_problem "timestamp（${FILE_TS}）が日時として読めない"
  elif [ "$DIFF" -gt 300 ] || [ "$DIFF" -lt -60 ]; then
    add_problem "timestamp（${FILE_TS}）が現在時刻（${NOW_TS}）から ${DIFF} 秒ずれている。Write の直前に \`date +%Y%m%d%H%M%S\` で取った値を使う（手で書いた・丸めた時刻は不可）"
  fi
fi

while IFS= read -r h; do
  if [ -n "$h" ]; then
    add_problem "見出し \`${h}\` が無い"
  fi
done <<< "$(jq -r '.missing[]' <<< "$ANALYSIS")"

if [ -z "$PROBLEMS" ]; then
  exit 0
fi

{
  echo "[adr-keeper] ADR の新規作成が adr スキルの手順から外れている: ${BASE}"
  printf '%s' "$PROBLEMS"
  echo ""
  echo "ADR は adr スキル（/adr new <title>）の手順で書く: 本文は skills/adr/references/template.md の"
  echo "見出しをすべて残して埋め、id とファイル名は Write の直前に \`date +%Y%m%d%H%M%S\` で取る。"
  if [ -n "$NOW_TS" ]; then
    echo "date を取り直しても合わない（シェルと hook で TZ が違う・DST をまたいだ）ときは、この hook の"
    echo "現在時刻 ${NOW_TS} を id とファイル名に使ってよい。"
  fi
} >&2
exit 2
