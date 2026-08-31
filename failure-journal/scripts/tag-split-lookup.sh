#!/usr/bin/env bash
# tag-split-lookup.sh — 分割宣言（splits.jsonl）の照会
#
# 起票側（log-failure Phase 2）が寄せ先を決めるときに読む、唯一の機械可読な宣言。
#
# なぜ要るか（GitHub issue #195）: umbrella tag の分割を doc の表に書いても起票側に降りない。
# Phase 2 が寄せ先候補として見るのは「journal に実在する tag」だけで、宣言直後のサブ tag は
# 0 件だから構造的に候補に上がらない。実測でも、分割宣言から窓が一巡するまでサブ tag の
# 使用は 0 件のままだった。**候補プールに宣言を足す**のがこのスクリプトの役目。
#
# **壊れた行は捨てずに止める（fail-loud）。** 1 行落とすと「分割されていない」に化け、
# 起票側が黙って umbrella へ寄せて issue #195 の状態へ戻る。集計側（retro-aggregate.sh）が
# 壊れた行を飛ばすのとは非対称だが意図的で、あちらは落ちてもレポートの 1 フィールドが
# 欠けるだけで済む。
#
# 出力: JSON（stdout）。exit 0 回答（宣言 0 件を含む） / 2 判定不能（jq 不在・壊れた行・引数不正）
set -euo pipefail

SPLITS=".claude/failure-journal/splits.jsonl"

usage() {
  cat <<'USAGE'
usage: tag-split-lookup.sh [options]

  --splits PATH   splits.jsonl のパス（既定: .claude/failure-journal/splits.jsonl）
  -h, --help      この使い方

出力 JSON:
  splits[]        宣言済みの umbrella tag（umbrella 名でソート）
    umbrella      分割元 tag
    declared_at   その umbrella の宣言のうち最も古いもの（採用計測の起点）
    sub_tags[]    寄せ先のサブ tag（最新の宣言行の内容）
    redirects[]   umbrella に見えるが別ファミリへ送る型

exit code:
  0  回答した（宣言 0 件を含む）
  2  判定不能（jq 不在 / 壊れた行 / 引数不正）。「分割なし」と読まないこと
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --splits)
      if [ $# -lt 2 ]; then
        printf -- '--splits に値がありません\n' >&2
        exit 2
      fi
      SPLITS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf '不明な引数: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v jq >/dev/null 2>&1; then
  printf 'jq が見つかりません（分割宣言を照会できません）\n' >&2
  exit 2
fi

if [ ! -f "$SPLITS" ]; then
  printf '{"splits":[]}\n'
  exit 0
fi

# 1 行ずつ検証してから畳む。行番号を出すために -R -s（ファイル全体を 1 文字列）で読む
OUT="$(jq -R -s '
def rows:
  split("\n")
  | to_entries
  | map(select((.value | test("^[[:space:]]*$")) | not))
  | map({line: (.key + 1), parsed: (try (.value | fromjson) catch null)});

def invalid:
  map(select(
    (.parsed | type) != "object"
    or ((.parsed.umbrella? | type) != "string")
    or ((.parsed.declared_at? | type) != "string")))
  | first;

rows as $r
| ($r | invalid) as $bad
| if $bad != null then {error: $bad.line}
  else
    {splits: (
      $r | map(.parsed)
      | group_by(.umbrella)
      | map(sort_by(.declared_at) as $g
            | {umbrella: ($g | last | .umbrella),
               declared_at: ($g | map(.declared_at) | min),
               sub_tags: ($g | last | (.sub_tags // [])),
               redirects: ($g | last | (.redirects // []))})
      | sort_by(.umbrella))}
  end
' -- "$SPLITS")" || exit 2

BAD_LINE="$(printf '%s' "$OUT" | jq -r '.error // empty')" || exit 2
if [ -n "$BAD_LINE" ]; then
  printf '%s: %s 行目が分割宣言として読めません（umbrella / declared_at の文字列が要ります）\n' \
    "$SPLITS" "$BAD_LINE" >&2
  printf '宣言を 1 行でも落とすと「分割なし」に化けるので中断します\n' >&2
  exit 2
fi

printf '%s\n' "$OUT"
