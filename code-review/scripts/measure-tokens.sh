#!/usr/bin/env bash
# セッションのトークン消費を transcript から集計する（改修の前後比較用）。
#
# `review:completed` payload は所要時間しか持たないため、「トークンが減ったか」は
# 従来まったく測れていなかった。Claude Code の transcript (jsonl) は各アシスタント
# メッセージに `usage` を持つので、そこから集計する。
#
# **main / sub の分離はファイルの所在で行う**（`isSidechain` フィールドでは分離できない）。
# 実測: top-level の `<slug>/*.jsonl` は全行 `isSidechain:false` で、サブエージェントは
# `<slug>/<session-id>/subagents/agent-*.jsonl` という別階層に置かれる。
# `isSidechain` で分けようとすると sub が常に 0 になり、**プロンプト複製の削減で
# main → sub へ移動しただけのコストまで「削減」に見えてしまう**（削減幅の過大評価）。
#
# 見るべき数字:
#   - main.output      … オーケストレーターが**書いた**量。プロンプト複製はここに出る（単価最大）
#   - main.cache_write … オーケストレーターが**新規に読んだ**量。参照 doc の読み込みはここ
#   - sub.*            … サブエージェント側。体数を変えた効果はここに出る
#
# 使い方:
#   measure-tokens.sh                      # 現在のリポジトリの最新セッション
#   measure-tokens.sh --session <path>     # 特定の transcript
#   measure-tokens.sh --list               # セッション候補を新しい順に表示
#   measure-tokens.sh --since 2026-08-06T10:00Z # その時刻以降だけ集計（**UTC**。transcript が UTC のため）
set -uo pipefail

SESSION=""; SINCE=""; LIST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --session) SESSION="$2"; shift 2 ;;
    --since)   SINCE="$2"; shift 2 ;;
    --list)    LIST=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要" >&2; exit 2; }

# transcript ディレクトリの slug はセッションを開始したディレクトリを正規化したもの
# （Claude Code は英数字以外をすべて `-` に置換する）。
#
# **cwd 由来の slug だけを見ると review 経路では必ず落ちる**（GitHub issue #112）。
# review skill は Step 0 で必ず EnterWorktree するため、本スクリプトを実行する時点の
# cwd は worktree 側だが、セッションはメインリポジトリで始まっているのでメインループの
# transcript はメイン slug の下にある。逆に dev-workflow の作業用 worktree 内で開始した
# セッションでは cwd 側にある。**どちらかに決め打ちすると片方で必ず欠測する**ので、
# 両方を候補にして「最も新しい .jsonl」を採る（実行中のセッションが最新であることを使う）。
#
# メインルートの導出は `--git-common-dir`（linked worktree からもメインの .git を返す）。
# publish-review-event.sh / lib/review-paths.sh と同じ手法。
ROOT=$(pwd)
CAND_ROOTS=("$ROOT")
GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
# GCD が空のときに無条件で cd "$GCD/.." すると `/` に降りるので必ず分岐する
if [ -n "$GCD" ] && MAIN_ROOT=$(cd "$GCD/.." && pwd 2>/dev/null); then
  [ "$MAIN_ROOT" != "$ROOT" ] && CAND_ROOTS+=("$MAIN_ROOT")
fi

DIRS=()
for _r in "${CAND_ROOTS[@]}"; do
  DIRS+=("$HOME/.claude/projects/$(printf %s "$_r" | sed 's#[^a-zA-Z0-9]#-#g')")
done

# 候補ディレクトリ横断で .jsonl を集める（`ls -t` に全件渡して大域的な新しい順にする。
# ディレクトリごとに `ls -t | head -1` すると候補間の順序が失われる）
FILES=()
for _d in "${DIRS[@]}"; do
  for _f in "$_d"/*.jsonl; do [ -f "$_f" ] && FILES+=("$_f"); done
done

if [ "$LIST" = "1" ]; then
  if [ ${#FILES[@]} -gt 0 ]; then
    ls -lt "${FILES[@]}" | head -20
  else
    printf 'セッションが見つからない:\n' >&2
    printf '  %s\n' "${DIRS[@]}" >&2
  fi
  exit 0
fi
if [ -z "$SESSION" ] && [ ${#FILES[@]} -gt 0 ]; then
  SESSION=$(ls -t "${FILES[@]}" | head -1)
fi
[ -n "$SESSION" ] && [ -f "$SESSION" ] || {
  echo "FATAL: transcript が見つからない（--session で指定するか --list で確認）。探索したディレクトリ:" >&2
  printf '  %s\n' "${DIRS[@]}" >&2
  exit 1; }

# **サブエージェントの transcript は別の project slug にあることがある**（GitHub issue #104）。
# review skill は Step 0 で EnterWorktree するため、セッションが 2 つの slug に割れる:
#   <repo-slug>/<session-id>.jsonl                        ← メインループ
#   <repo-slug>--claude-worktrees-<name>/<session-id>/subagents/  ← サブエージェント
# メイン slug 配下だけを見ると review では必ず sub=0 になる。
# **session-id は全 slug を通じて一意**なので、slug をまたいで session-id で引き当てる
# （`--claude-worktrees-*` という命名規則に依存しないので EnterWorktree の実装が変わっても効く）。
SESSION_ID=$(basename "$SESSION" .jsonl)
SUBGLOB="$HOME/.claude/projects/*/${SESSION_ID}/subagents"

SESSION="$SESSION" SINCE="$SINCE" SUBDIR="$SUBGLOB" python3 <<'PY'
import glob, json, os, sys

path, since = os.environ["SESSION"], os.environ.get("SINCE") or None
subdir = os.environ.get("SUBDIR") or ""
buckets = {False: dict(n=0, out=0, cw=0, cr=0, inp=0), True: dict(n=0, out=0, cw=0, cr=0, inp=0)}
first_ts = last_ts = None

# main = 親 transcript / sub = <session-id>/subagents/agent-*.jsonl
# subdir は `~/.claude/projects/*/<session-id>/subagents` のようなワイルドカード付き
sub_files = sorted(glob.glob(os.path.join(subdir, "*.jsonl"))) if subdir else []
targets = [(path, False)] + [(f, True) for f in sub_files]

for fpath, side in targets:
    try:
        fh = open(fpath)
    except OSError:
        continue
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            u = (e.get("message") or {}).get("usage")
            if not u:
                continue
            ts = e.get("timestamp") or ""
            if since and ts and ts < since:
                continue
            if ts:
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
            b = buckets[side]
            b["n"] += 1
            b["out"] += u.get("output_tokens") or 0
            b["cw"] += u.get("cache_creation_input_tokens") or 0
            b["cr"] += u.get("cache_read_input_tokens") or 0
            b["inp"] += u.get("input_tokens") or 0
agents = sub_files

def k(v): return f"{v/1000:,.1f}k"

print(f"transcript : {os.path.basename(path)}")
if first_ts:
    print(f"期間       : {first_ts} 〜 {last_ts}")
print()
print(f"{'':<10}{'msgs':>7}{'output':>12}{'cache_write':>14}{'cache_read':>13}{'input':>10}")
for side, label in ((False, "main"), (True, "sub")):
    b = buckets[side]
    print(f"{label:<10}{b['n']:>7}{k(b['out']):>12}{k(b['cw']):>14}{k(b['cr']):>13}{k(b['inp']):>10}")
tot_out = buckets[False]["out"] + buckets[True]["out"]
tot_cw = buckets[False]["cw"] + buckets[True]["cw"]
print(f"{'合計':<9}{buckets[False]['n']+buckets[True]['n']:>7}{k(tot_out):>12}{k(tot_cw):>14}")
if agents:
    print(f"\nサブエージェント: {len(agents)} 体（{os.path.basename(subdir)}/ から集計）")
elif buckets[False]["n"]:
    # 前提が壊れたときに黙って 0 を返さない（sub が常に 0 だと削減幅を過大評価する）
    print("\n⚠️  サブエージェントの transcript が見つからない: " + (subdir or "(未指定)"))
    print("   fleet を起動したのに 0 体なら、session-id での引き当てが効いていない。")
    print("   `ls ~/.claude/projects/*/" + os.path.basename(os.path.dirname(subdir or "")) + "/subagents` で実在を確認する")
print("""
読み方: main.output = オーケストレーターが書いた量（プロンプト複製はここ・単価最大）
        main.cache_write = 新規に読み込んだ量（参照 doc の読み込みはここ）
        cache_read は再利用ぶんなので単価が低い。前後比較は output と cache_write で見る""")
PY
