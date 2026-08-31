#!/usr/bin/env bash
# retro-aggregate.sh — retro Phase 2/3 の集計
#
# 窓内の tag 別件数に加えて、**最後の還流日以降の発生**を分子として出す
# （GitHub issue #193）。還流済みの発生を分子に残すと、対策を打った後も窓を
# 抜けるまで同じ tag が鳴り続け、次の retro が同じ手を再提案する。
#
# なぜ SKILL 本文の jq ではなくスクリプトなのか: 閾値判定が journal と
# remediations の join になり、境界（還流日ちょうどの発生・閾値ちょうどの件数）を
# 回帰テストで固定できない。判定自体は決定的なので機械層へ寄せる。
#
# **分母と除外件数は必ず出す。** 黙って分子を減らすと「収まった」と誤読される
# （`review-retro.sh` の抑止件数と同じ扱い）。
#
# 出力: JSON（stdout）。exit 0 集計成功 / 2 判定不能（jq 不在・引数不正）
set -euo pipefail

JOURNAL=".claude/failure-journal/journal.jsonl"
REMED=".claude/failure-journal/remediations.jsonl"
SPLITS=".claude/failure-journal/splits.jsonl"
DAYS=30
THRESHOLD=3
NOW=""

usage() {
  cat <<'USAGE'
usage: retro-aggregate.sh [options]

  --journal PATH        journal.jsonl のパス（既定: .claude/failure-journal/journal.jsonl）
  --remediations PATH   remediations.jsonl のパス（既定: .claude/failure-journal/remediations.jsonl）
  --splits PATH         splits.jsonl のパス（既定: .claude/failure-journal/splits.jsonl）
  --days N              集計窓の日数（既定: 30）
  --threshold N         閾値（既定: 3）
  --now ISO8601         現在時刻。省略時は date -u。テストで窓を固定するために使う

出力 JSON の各 tag 行:
  count_window            窓内の全発生（分母）
  count_effective         最後の還流日以降の発生（分子）
  excluded_by_remediation 還流日以前として分子から外した件数
  over_threshold          count_effective が閾値に達した
  quiet_since_remediation 還流実績があり、その後の発生が 0 件
  split_declared_at       分割を宣言した日時（同一 umbrella が複数行なら最も古いもの）
  sub_tags                宣言した寄せ先のサブ tag
  count_after_split       宣言日以降の窓内発生。**分子には影響しない**
  split_not_adopted       分割を宣言したのに宣言日以降も umbrella へ起票されている
USAGE
}

_need_value() {
  # $1=フラグ名 $2=残り引数の個数
  if [ "$2" -lt 2 ]; then
    printf '%s に値がありません\n' "$1" >&2
    exit 2
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --journal)      _need_value "$1" $#; JOURNAL="$2";   shift 2 ;;
    --remediations) _need_value "$1" $#; REMED="$2";     shift 2 ;;
    --splits)       _need_value "$1" $#; SPLITS="$2";    shift 2 ;;
    --days)         _need_value "$1" $#; DAYS="$2";      shift 2 ;;
    --threshold)    _need_value "$1" $#; THRESHOLD="$2"; shift 2 ;;
    --now)          _need_value "$1" $#; NOW="$2";       shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *) printf '不明な引数: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v jq >/dev/null 2>&1; then
  printf 'jq が見つかりません（集計不能）\n' >&2
  exit 2
fi

for _pair in "days:${DAYS}" "threshold:${THRESHOLD}"; do
  case "${_pair#*:}" in
    ''|*[!0-9]*)
      printf -- '--%s は 0 以上の整数で指定してください: %s\n' "${_pair%%:*}" "${_pair#*:}" >&2
      exit 2 ;;
  esac
done

[ -n "$NOW" ] || NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
case "$NOW" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z) ;;
  *) printf -- '--now は ISO8601 UTC（末尾 Z）で指定してください: %s\n' "$NOW" >&2; exit 2 ;;
esac

# 不正な行が混ざっても集計を落とさない（journal は手書き append される）
_stream() {
  if [ -f "$1" ]; then
    jq -R 'fromjson? // empty' -- "$1"
  fi
}

jq -n \
  --argjson days "$DAYS" \
  --argjson threshold "$THRESHOLD" \
  --arg now "$NOW" \
  --slurpfile occ_raw <(_stream "$JOURNAL") \
  --slurpfile rem_raw <(_stream "$REMED") \
  --slurpfile spl_raw <(_stream "$SPLITS") '
def ok: type == "object" and ((.tag? | type) == "string") and ((.timestamp? | type) == "string");
def ok_split: type == "object"
  and ((.umbrella? | type) == "string")
  and ((.declared_at? | type) == "string");
def iso: try fromdateiso8601 catch null;

($now | iso) as $now_epoch
| ((($now_epoch - ($days * 86400)) | todateiso8601)) as $since
| ($occ_raw | map(select(ok))) as $occ
| ($rem_raw | map(select(ok))) as $rem
| ($spl_raw | map(select(ok_split))) as $spl
| {
    window: {days: $days, since: $since, now: $now},
    threshold: $threshold,
    tags: (
      (($occ + $rem) | map(.tag) | unique)
      | map(
          . as $t
          | ($occ | map(select(.tag == $t))) as $o
          | ($rem | map(select(.tag == $t)) | sort_by(.timestamp)) as $r
          | ($o | map(select(.timestamp >= $since))) as $ow
          | (if ($r | length) == 0 then null else ($r | last | .timestamp) end) as $last
          # 有効境界は「窓境界と最後の還流日の遅い方」。比較演算子で書くと
          # 両者が同値のとき境界変異が等価になり、変異テストで必ず生き残る
          | ([$since] + (if $last == null then [] else [$last] end) | max) as $eff
          | ($ow | map(select(.timestamp >= $eff))) as $oe
          # 分割は語彙の宣言であって還流ではない。分子（$oe）も有効境界（$eff）も動かさない
          # — 動かすと対策を打っていないのにアラームが消える（GitHub issue #195）
          | ($spl | map(select(.umbrella == $t))) as $s
          | (if ($s | length) == 0 then null
             else ($s | map(.declared_at) | min) end) as $sdecl
          | (if $sdecl == null then null
             else ($ow | map(select(.timestamp >= $sdecl)) | length) end) as $after
          | {
              tag: $t,
              count_all_time: ($o | length),
              count_window: ($ow | length),
              count_effective: ($oe | length),
              excluded_by_remediation: (($ow | length) - ($oe | length)),
              window_since: $since,
              effective_since: $eff,
              last_remediated_at: $last,
              days_since_remediation: (
                if $last == null then null
                else (($last | iso) as $le
                      | if $le == null then null
                        else ((($now_epoch - $le) / 86400) | floor) end)
                end),
              remediations: ($r | map({
                timestamp: .timestamp,
                target: (.target // null),
                ref: (.ref // null),
                note: (.note // null)
              })),
              over_threshold: (($oe | length) >= $threshold),
              quiet_since_remediation: ($last != null and ($oe | length) == 0),
              split_declared_at: $sdecl,
              sub_tags: (if $sdecl == null then null
                         else ($s | sort_by(.declared_at) | last | (.sub_tags // [])
                               | map(.tag)) end),
              count_after_split: $after,
              split_not_adopted: ($sdecl != null and $after != 0)
            })
      | sort_by(-.count_effective, -.count_window, .tag)
    )
  }
'
