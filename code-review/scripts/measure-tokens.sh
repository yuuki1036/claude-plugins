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
#   measure-tokens.sh --json               # 機械可読（publish-review-event.sh が payload に載せる）
set -uo pipefail

SESSION=""; SINCE=""; LIST=0; AS_JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    # `$2` を素で読むと `set -u` の生エラー（`$2: unbound variable`）だけが出て、
    # **どの引数の指定漏れか**が残らない。他の同梱スクリプトと同じ形で弾く
    --session) [ $# -ge 2 ] || { echo "FATAL: --session に値が必要" >&2; exit 2; }; SESSION="$2"; shift 2 ;;
    --since)   [ $# -ge 2 ] || { echo "FATAL: --since に値が必要" >&2; exit 2; }; SINCE="$2"; shift 2 ;;
    --list)    LIST=1; shift ;;
    --json)    AS_JSON=1; shift ;;
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

SESSION="$SESSION" SINCE="$SINCE" SUBDIR="$SUBGLOB" AS_JSON="$AS_JSON" python3 <<'PY'
import glob, json, os, sys

path, since = os.environ["SESSION"], os.environ.get("SINCE") or None
subdir = os.environ.get("SUBDIR") or ""
buckets = {False: dict(n=0, out=0, cw=0, cr=0, inp=0), True: dict(n=0, out=0, cw=0, cr=0, inp=0)}
first_ts = last_ts = None
# **窓内に usage を持つ subagent transcript のファイル集合**。`--since` はメッセージ行に効くので、
# glob したファイル数をそのまま体数にすると窓の外で起動した agent まで数えてしまう（実測:
# `--since 2099-01-01` で `sub.n=0` なのに `sub_agents=8`）。窓と体数の意味を揃える
sub_seen = set()
tool_of = {}      # tool_use_id -> ツール名（main のみ）
intake = {}       # ツール名 -> tool_result の総文字数
intake_n = {}     # ツール名 -> tool_result の件数

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
            # `--since` は取り込み内訳にも効かせる（usage 表だけ絞ると区間比較で桁が合わない）
            ts = e.get("timestamp") or ""
            if since and ts and ts < since:
                continue
            # **main への取り込みを「何経由で入ったか」に分解する**（GitHub issue #118）。
            # cache_write は「新規に読んだ量」だが、参照 doc の読み込みと agent 出力の
            # 取り込みが同じバケツに入るため、cache_write 単独では分冊・遅延読み込みの
            # 効果を判定できない（fleet が大きいほど agent 側が支配的になる）。
            #
            # **経路は tool_result だけではない**。`type: "attachment"` のエントリ
            # （hook stdout の注入・skill/agent listing・編集ファイルのスニペット等）も
            # 同じくコンテキストへ入る。実測では attachment が tool_result 合計を
            # 上回るセッションがあり、これを分母から落とすと Agent 経由の占有が
            # 系統的に過大に出る（実測で 2.4〜3.3 倍）。両方を同じ表に積む。
            if not side:
                if e.get("type") == "attachment":
                    att = e.get("attachment") or {}
                    if isinstance(att, dict):
                        # 注入本文を持つフィールドは type ごとに違う。allowlist で拾い、
                        # どれも無いときだけ全体長にフォールバックする（黙って 0 にしない）
                        chars = 0
                        for key in ("content", "stdout", "stderr", "snippet",
                                    "addedLines", "addedBlocks"):
                            val = att.get(key)
                            if isinstance(val, str):
                                chars += len(val)
                            elif isinstance(val, (list, dict)):
                                chars += len(json.dumps(val, ensure_ascii=False))
                        if chars == 0:
                            chars = len(json.dumps(att, ensure_ascii=False))
                        name = "attachment:%s" % (att.get("type") or "?")
                        intake[name] = intake.get(name, 0) + chars
                        intake_n[name] = intake_n.get(name, 0) + 1
                msg = e.get("message") or {}
                blocks = msg.get("content")
                if isinstance(blocks, list):
                    for blk in blocks:
                        if not isinstance(blk, dict):
                            continue
                        if blk.get("type") == "tool_use":
                            tool_of[blk.get("id")] = blk.get("name") or "?"
                        elif blk.get("type") == "tool_result":
                            body = blk.get("content")
                            if not isinstance(body, str):
                                body = json.dumps(body, ensure_ascii=False)
                            # `--since` 指定時、tool_use が窓外・tool_result が窓内だと
                            # 名前が引けず `?` に落ちる（境界の数件。欠測として出す）
                            name = tool_of.get(blk.get("tool_use_id"), "?")
                            intake[name] = intake.get(name, 0) + len(body)
                            intake_n[name] = intake_n.get(name, 0) + 1
            u = (e.get("message") or {}).get("usage")
            if not u:
                continue
            if ts:
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
            b = buckets[side]
            if side:
                sub_seen.add(fpath)
            b["n"] += 1
            b["out"] += u.get("output_tokens") or 0
            b["cw"] += u.get("cache_creation_input_tokens") or 0
            b["cr"] += u.get("cache_read_input_tokens") or 0
            b["inp"] += u.get("input_tokens") or 0
agents = sub_files

def k(v): return f"{v/1000:,.1f}k"

# **機械可読モード**（GitHub issue #126）: publish-review-event.sh が review の publish 時に
# 呼んで `tokens` フィールドへ載せる。取り込み内訳は payload に載せない（文字数であって
# トークンではなく、集計側で混ぜると桁が合わない — 上の `## 17` の注記と同じ理由）
if os.environ.get("AS_JSON") == "1":
    print(json.dumps({
        "session": os.path.basename(path),
        "since": since, "first_ts": first_ts, "last_ts": last_ts,
        "main": {"n": buckets[False]["n"], "output": buckets[False]["out"],
                 "cache_write": buckets[False]["cw"], "cache_read": buckets[False]["cr"],
                 "input": buckets[False]["inp"]},
        "sub": {"n": buckets[True]["n"], "output": buckets[True]["out"],
                "cache_write": buckets[True]["cw"], "cache_read": buckets[True]["cr"],
                "input": buckets[True]["inp"]},
        # **2 つは別物**。`sub_agents` は窓内に usage を持つ本数（他フィールドと同じ窓）、
        # `sub_files` は glob した総数（**窓非適用**）。後者は「transcript は在るのに窓内が
        # 空」＝引き当て失敗の検出に要る（呼び出し側が縮退判定に使う）
        "sub_agents": len(sub_seen),
        "sub_files": len(agents),
    }, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0)

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
if intake:
    total_chars = sum(intake.values())
    print("\nmain への取り込み内訳（tool_result + attachment の文字数 / GitHub issue #118）")
    print(f"{'':<24}{'件数':>6}{'chars':>12}{'占有':>8}")
    for name, chars in sorted(intake.items(), key=lambda kv: -kv[1])[:8]:
        share = chars / total_chars * 100 if total_chars else 0
        print(f"{name[:24]:<24}{intake_n[name]:>6}{chars:>12,}{share:>7.1f}%")
    agent_share = intake.get("Agent", 0) / total_chars * 100 if total_chars else 0
    print(f"→ Agent 経由は**取り込み全体の** {agent_share:.1f}%（`main.cache_write` に占める比率ではない）")

print("""
読み方: main.output = オーケストレーターが書いた量（プロンプト複製はここ・単価最大）
        main.cache_write = 新規に読み込んだ量。取り込み（参照 doc も agent 出力も）はここへ
                           合流するが、**大半はターンごとに再キャッシュされるプロンプト前半**で、
                           取り込みぶんは実測で 1 割前後にとどまる（#118）。分冊・遅延読み込みの
                           効果を cache_write 単独で判定しない
        cache_read = 再利用ぶん。**単価は低いが総量は最大**になりやすい（往復回数 × その時点の
                     文脈量）。往復削減の効果はここに出るので output / cache_write と併せて見る

取り込み内訳は**文字数**（トークンではない）。換算係数が内容種別で変わるため絶対値ではなく
**経由別の比率**として読む。上の表は cache_write の分解ではない（桁が合わないのが正常）。
分冊の効果を単独で見たいなら agent を起動しない経路（Phase 0 までで中断・skip-mode）で測る。""")
PY
