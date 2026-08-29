#!/usr/bin/env bash
# セッションの**トークン消費と agent の発行パターン**を transcript から集計する
# （改修の前後比較用）。
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
#   - dispatch         … agent を**どのメッセージから発行したか**で一括発行が守られたかを
#                        判定する（GitHub issue #142 / 判定単位の是正が #149）。
#                        `duration_fleet_min` は「9 体を逐次で回した 89 分」と
#                        「1 体が 89 分かかった」を区別できない
#
# 使い方:
#   measure-tokens.sh                      # 現在のリポジトリの最新セッション
#   measure-tokens.sh --session <path>     # 特定の transcript
#   measure-tokens.sh --list               # セッション候補を新しい順に表示
#   measure-tokens.sh --since 2026-08-06T10:00Z # その時刻以降だけ集計（**UTC**。transcript が UTC のため）
#   measure-tokens.sh --json               # 機械可読（publish-review-event.sh が payload に載せる）
#   measure-tokens.sh --per-agent          # 体ごとの cache_read と往復数（回内分散 / GitHub issue #156）
set -uo pipefail

SESSION=""; SINCE=""; LIST=0; AS_JSON=0; PER_AGENT=0
while [ $# -gt 0 ]; do
  case "$1" in
    # `$2` を素で読むと `set -u` の生エラー（`$2: unbound variable`）だけが出て、
    # **どの引数の指定漏れか**が残らない。他の同梱スクリプトと同じ形で弾く
    --session) [ $# -ge 2 ] || { echo "FATAL: --session に値が必要" >&2; exit 2; }; SESSION="$2"; shift 2 ;;
    --since)   [ $# -ge 2 ] || { echo "FATAL: --since に値が必要" >&2; exit 2; }; SINCE="$2"; shift 2 ;;
    --list)    LIST=1; shift ;;
    --json)    AS_JSON=1; shift ;;
    --per-agent) PER_AGENT=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要" >&2; exit 2; }

# transcript ディレクトリの slug 導出は `lib/review-paths.sh` の `review_project_dirs`
# が正本（cwd 側とメイン側の 2 候補を返す理由・片方に決め打ちできない理由はそちら）。
# ここでは候補ディレクトリを受け取って「最も新しい .jsonl」を採るだけ
# （実行中のセッションが最新であることを使う）。
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_project_dirs
DIRS=(${REVIEW_PROJECT_DIRS[@]+"${REVIEW_PROJECT_DIRS[@]}"})

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

SESSION="$SESSION" SINCE="$SINCE" SUBDIR="$SUBGLOB" AS_JSON="$AS_JSON" PER_AGENT="$PER_AGENT" python3 <<'PY'
import glob, json, os, sys

path, since = os.environ["SESSION"], os.environ.get("SINCE") or None
subdir = os.environ.get("SUBDIR") or ""
buckets = {False: dict(n=0, out=0, cw=0, cr=0, inp=0), True: dict(n=0, out=0, cw=0, cr=0, inp=0)}
# **モデル世代**（GitHub issue #169）。`effort` / `size_tier` で層別する設計だが、
# Opus 5 と 4.8 が混ざった瞬間にその層別が成立しなくなる（実測: 2026-08-24 の 1 日で
# 3 サンプル中 2 件が 4.8）。世代はユーザーが実行時に選ぶもの（エイリアスは親世代を継ぐ
# — `docs/pipeline-design.md` モデルルーティング規約）なので、**事故ではなく層別キー**として扱う
models = {False: set(), True: set()}
first_ts = last_ts = None
# **窓内に usage を持つ subagent transcript のファイル集合**。`--since` はメッセージ行に効くので、
# glob したファイル数をそのまま体数にすると窓の外で起動した agent まで数えてしまう（実測:
# `--since 2099-01-01` で `sub.n=0` なのに `sub_agents=8`）。窓と体数の意味を揃える
sub_seen = set()
per_agent = {}   # subagent transcript -> 窓内の内訳（`--per-agent` 用）
sub_first = {}    # サブエージェント transcript -> 窓内で最初の timestamp（= 起動時刻）
# 同 -> 窓内で**最も新しい** timestamp（= 終了時刻 / GitHub issue #153）。wave 間ギャップを「wave N の agent が回っていた時間」と
# 「オーケストレーターが次の wave を出すまでの時間」に割るのに要る
sub_last = {}
# 同 -> 窓内の timestamp 付き行数。**終了時刻が「取れた」と言えるのは 2 行以上あるときだけ**。
# transcript が 1 行しか無い（窓が起動直後で切れた / 途中で壊れた）回は `sub_last` が
# `sub_first` と同一になり、**「起動と同時に終わった」と区別がつかない**。そのまま使うと
# agent 実行時間が 0 に出て idle 側が総取りし、「オーケストレーターが遅い」という誤った
# 打ち手を選ばせる（#153）
sub_rows = {}
tool_of = {}      # tool_use_id -> ツール名（main のみ）
# **Agent の tool_use id -> (発行したアシスタントメッセージのキー, 時刻)**。
# 同一メッセージから出た agent は同一 wave（GitHub issue #149）。main だけでなく
# sub 側も見る（agent がさらに agent を起動した回を親メッセージに寄せないため）。
#
# **キーは `message.id`（無ければ `requestId`）であって行の `uuid` ではない**。transcript は
# 1 メッセージを **tool_use ブロックごとに別行へ分解**して書く（実測: 同一メッセージから出た
# 5 体が `uuid` 別・`message.id` 共通で、各行の content は 1 ブロックだけ）。`uuid` で束ねると
# **一括発行した回まで「1 体ずつの wave」に見え、全件が serial に落ちる**
agent_dispatch = {}
# toolUseId -> 結果が返り、かつ `is_error` でないか（GitHub issue #154）。
# **`description` は読まない** — 自由文で書式が安定しないうえ、Round 2 は仕様上
# 同じ reviewer を再起動して出力を置換するので、字面では再試行と区別できない
result_ok = {}
sub_depth = {}      # subagent transcript -> meta.json の spawnDepth


def _wave_key(entry):
    msg = entry.get("message") or {}
    return msg.get("id") or entry.get("requestId") or entry.get("uuid")
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
                            if blk.get("name") == "Agent":
                                agent_dispatch[blk.get("id")] = (_wave_key(e), ts)
                        elif blk.get("type") == "tool_result":
                            body = blk.get("content")
                            if not isinstance(body, str):
                                body = json.dumps(body, ensure_ascii=False)
                            # `--since` 指定時、tool_use が窓外・tool_result が窓内だと
                            # 名前が引けず `?` に落ちる（境界の数件。欠測として出す）
                            name = tool_of.get(blk.get("tool_use_id"), "?")
                            intake[name] = intake.get(name, 0) + len(body)
                            intake_n[name] = intake_n.get(name, 0) + 1
                            # **結果が返ったか**を記録する（GitHub issue #154）。
                            # 返っていない体＝割り込み等で捨てられた試行で、
                            # オーケストレーターの申告には現れない
                            _rid = blk.get("tool_use_id")
                            if _rid:
                                result_ok[_rid] = not blk.get("is_error")
            elif e.get("type") == "assistant":
                # sub 側は取り込み内訳を採らない（main の負荷が論点）が、**Agent の発行だけは
                # 拾う**。入れ子起動（`spawnDepth >= 2`）を親メッセージに寄せると wave の
                # 大きさが実態とずれる
                blocks = (e.get("message") or {}).get("content")
                if isinstance(blocks, list):
                    for blk in blocks:
                        if not isinstance(blk, dict):
                            continue
                        if blk.get("type") == "tool_use" and blk.get("name") == "Agent":
                            agent_dispatch[blk.get("id")] = (_wave_key(e), ts)
            elif side and e.get("type") == "user":  # mutation-ok: main 側の tool_result は上のブロックで記録済みなので or でも結果は同じ
                # **孫 agent の結果は親の sub transcript 側にある**ので、そこからも
                # 到達を拾う（main 限定だと孫が全部「捨てられた」に落ちる）。
                # `tool_result` は **`user` メッセージ**に載る（`assistant` ではない）
                blocks = (e.get("message") or {}).get("content")
                if isinstance(blocks, list):
                    for blk in blocks:
                        if isinstance(blk, dict) and blk.get("type") == "tool_result":
                            _rid = blk.get("tool_use_id")
                            if _rid:
                                result_ok[_rid] = not blk.get("is_error")
            # **usage を持つ行に限らない**（起動直後のメタ行が先に来る）。窓の適用は
            # 上の `since` フィルタで済んでいるので、ここに来た時点で窓内
            if side and ts:
                if fpath not in sub_first:
                    sub_first[fpath] = ts
                # **`max` で採る**（行が時系列に並んでいる前提を置かない。append ログなので
                # 通常は並ぶが、並びを仮定すると壊れたときに「終了が起動より前」という
                # 負のギャップになり、静かに 0 へクランプされて欠測と区別できなくなる）
                prev = sub_last.get(fpath)
                sub_last[fpath] = ts if prev is None else max(prev, ts)
                sub_rows[fpath] = sub_rows.get(fpath, 0) + 1
            # `message.model` は assistant 行にだけ載る素の文字列。**`<synthetic>` のような
            # プレースホルダが混ざる**ので（実測: 160 transcript を走査して 11 件）、
            # `<` 始まりは実モデルではないとして数えない。ここを素通しすると
            # `main_distinct` が 2 件になり、単一世代の回まで「混在」に落ちる
            mdl = (e.get("message") or {}).get("model")
            if isinstance(mdl, str):
                mdl = mdl.strip()
                if mdl and not mdl.startswith("<"):
                    models[side].add(mdl)
            u = (e.get("message") or {}).get("usage")
            if not u:
                continue
            if ts:
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
            b = buckets[side]
            if side:
                sub_seen.add(fpath)
                # 体ごとの内訳（回内分散 / GitHub issue #156）。**層別サンプルを待たずに
                # 1 run 内で対照が取れる**のがこの粒度の値打ちで、tier / effort / 世代が
                # 定義上そろうため交絡しない
                pa = per_agent.setdefault(fpath, {"cr": 0, "cw": 0, "out": 0, "n": 0})
                pa["n"] += 1
                pa["cr"] += u.get("cache_read_input_tokens") or 0
                pa["cw"] += u.get("cache_creation_input_tokens") or 0
                pa["out"] += u.get("output_tokens") or 0
            b["n"] += 1
            b["out"] += u.get("output_tokens") or 0
            b["cw"] += u.get("cache_creation_input_tokens") or 0
            b["cr"] += u.get("cache_read_input_tokens") or 0
            b["inp"] += u.get("input_tokens") or 0
agents = sub_files

# **発行パターンの判定**（GitHub issue #142 / 判定単位の是正が #149）。
# `duration_fleet_min` は「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を区別できない。
#
# **判定単位は wave（同一メッセージから出た agent の束）であってレビュー全体ではない**
# （orchestration-guide.md `## 0`）。explorer → reviewer → 反証 は設計上逐次で、1 メッセージに
# まとめられない。旧版は起動時刻のフラットな時系列に 120 秒閾値を当てていたため、**wave 間の
# ギャップ（実測ベースライン 6〜9 分）を違反として数え、2 層以上のレビューは規約を完全に
# 守っていても `batched` に到達できなかった**（#149）。
#
# wave は推定しない。`subagents/agent-*.meta.json` の `toolUseId` を transcript の `tool_use`
# ブロックへ引き当てれば、**どのアシスタントメッセージから出たか**が確定する。時間閾値も
# LLM の自己申告も要らない（`agents.explorer_waves` = 打点の行数 は自己申告なので、打ち忘れた
# 瞬間に違反の証拠も消えていた / design-notes/pending-optimizations.md `## 8`）。
# schema 3: wave 間ギャップの内訳（`inter_wave_agent_sec` / `inter_wave_idle_sec`）を追加
# （GitHub issue #153）。`max_inter_wave_sec` は「wave N 起動 → wave N+1 起動」なので、
# **agent が回っていた時間**と**オーケストレーターの統合・dedup・scoring 時間**が
# 合算されている。どちらが支配的かで打ち手が正反対（前者なら wave を減らす / 後者なら
# 往復を減らす）なので、分離しないまま是正すると「wave を消したのに fleet が縮まない」を踏む
DISPATCH_SCHEMA = 4
# **連続する単独 wave が何本続いたら違反と呼ぶか**。1 体だけの wave 自体は正当（設計上 1 体
# しか起動しないフェーズがある）。2 連続も skeptic → meta のような別ゲートの並びで説明が
# つく。**3 連続以上はこのパイプラインの層構造では説明できない**ので、そこを閾値にする。
# 上げ下げの判断材料として `waves` / `wave_sizes` を payload に残す
DISPATCH_SOLO_RUN = 3


def _epoch(ts):
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# 窓内に起動した agent を「発行元メッセージ」へ寄せる。**引き当てられない agent が 1 体でも
# あれば判定しない** — 一部だけで wave を組むと wave 数が実態より小さく出て、`batched` 寄りの
# 誤判定になる。#142 が持っていた原則（「一括だった」に倒さない）を**両側**に効かせる
waves_by_msg = {}
waves_completed = {}
unresolved = 0
for fpath, ts in sub_first.items():
    started = _epoch(ts)
    meta_path = fpath[:-len(".jsonl")] + ".meta.json" if fpath.endswith(".jsonl") else ""
    tool_use_id = None
    # 印は**変異させる行と同じ行**に置かないと効かない（直前行に書いていて #152 で生存した）
    if meta_path and os.path.exists(meta_path):  # mutation-ok: `or` は等価（存在しない meta_path は open が OSError を投げ同じ「引き当て失敗」に落ちる）
        try:
            with open(meta_path) as mfh:
                meta = json.load(mfh)
            if isinstance(meta, dict):
                tool_use_id = meta.get("toolUseId")
                _sd = meta.get("spawnDepth")
                if isinstance(_sd, int) and not isinstance(_sd, bool):
                    sub_depth[fpath] = _sd
        except (OSError, ValueError):
            tool_use_id = None
    owner = agent_dispatch.get(tool_use_id) if tool_use_id else None
    if started is None or not owner or not owner[0]:
        unresolved += 1
        continue
    # 終了時刻は**取れないことがある**（末尾行に timestamp が無い / 窓の切り方）ので、
    # 起動時刻と違って引き当て失敗を `unresolved` に数えない。wave 構成そのものは
    # 起動時刻だけで決まるため、終了が欠けても `verdict` は判定できる（欠測にするのは
    # 内訳 2 本だけ / #153）
    ended = _epoch(sub_last.get(fpath) or "") if sub_rows.get(fpath, 0) >= 2 else None
    waves_by_msg.setdefault(owner[0], []).append((started, ended))
    # **捨てられた試行・孫を除いた wave も同時に組む**（GitHub issue #154 / #192）。
    # 再試行は wave 本数・`wave_sizes`・`span_sec` も膨らませるので、`agents` だけを
    # 直すと一括発行の判定が汚れた本数のまま走る（実測: 8 本のうち 3 本が同一 6 体の再発行）
    if result_ok.get(tool_use_id) and sub_depth.get(fpath, 1) <= 1:
        waves_completed.setdefault(owner[0], []).append(started)

# ---- agents の分解（GitHub issue #154）--------------------------------------
# **`agents` は据え置く。** これは sub 側のトークン集計と同じファイル集合で、
# 「1 体あたり cache_read」の分母として正しい唯一の値（捨てられた試行も孫も実コストを
# 食っている）。実測でユニーク数を分母にすると 4,941k が 11,364k ＝ 2.30 倍に化け、
# 起きていない退行として読める。**減らすのではなく内訳を足し、突合の相手だけ差し替える**。
#
# 分解の軸は `description` ではない。自由文で書式が安定しないうえ、**Round 2 は仕様上
# 同じ reviewer を再起動して出力を置換する**ので、字面では正当な再起動と再試行を
# 区別できない（実測: 重複 38 件中 26 件が正当な別起動）。代わりに
# **結果が返ったか**（`tool_result` の到達）と `spawnDepth` で切る。
#
#   agents_completed … depth==1 かつ結果が返った（`is_error` でない）体
#   agents_abandoned … 結果が返っていない / `is_error` の体（深さ不問）
#   agents_nested    … depth>=2 かつ結果が返った体（オーケストレーターは申告しようがない）
#
# 不変条件: completed + abandoned + nested == agents
# **`tool_result` を 1 件も引けなかったら分解しない。** 引けない理由は「全部捨てられた」
# ではなく「結果の所在が変わった / 窓の外にある」の可能性があり、0 と欠測を潰すと
# **毎回 `agents_completed = 0` になって突合が常時ずれる**（＝ agents-mismatch が
# 恒常的に立ち、信号として死ぬ）。判定できないときは分解ごと出さず、突合は
# 従来どおり `agents` で行う（publish 側がフォールバックする）
agents_completed = agents_abandoned = agents_nested = None
if result_ok:
    agents_completed = agents_abandoned = agents_nested = 0
for _f in (sub_first if result_ok else ()):
    # `_f` は `agent-*.jsonl` の glob 由来なので拡張子の分岐は要らない
    _mp = _f[: -len(".jsonl")] + ".meta.json"
    _tid = None
    if os.path.exists(_mp):
        try:
            _m = json.load(open(_mp))
            if isinstance(_m, dict):
                _tid = _m.get("toolUseId")
        except (OSError, ValueError):
            _tid = None
    # **結果の有無が不明なら `abandoned` に倒す**（引き当てられなかった体を
    # 「完了した」と数えると、突合が黙って通る方向に倒れる）
    if not _tid or not result_ok.get(_tid):
        agents_abandoned += 1
    elif sub_depth.get(_f, 1) > 1:
        agents_nested += 1
    else:
        agents_completed += 1

dispatch = {"schema": DISPATCH_SCHEMA, "agents": len(sub_first),
            "agents_completed": agents_completed,
            "agents_abandoned": agents_abandoned,
            "agents_nested": agents_nested,
            # **捨てられた試行・孫を除いた wave 本数**。一括発行の判定はこちらを使う。
            # `waves` / `wave_sizes` は据え置き（実際に走った本数として意味がある）
            # 分解が成立した回だけ出す（同上）
            # `waves_completed` は `result_ok` を引けた体しか入らないので、
            # `result_ok` の空判定は要らない（分岐を残すと死んだ条件になる）
            "waves_effective": (len(waves_completed) if waves_completed else None),
            "waves": None,
            "wave_sizes": None, "max_solo_run": None, "max_inter_wave_sec": None,
            "inter_wave_agent_sec": None, "inter_wave_idle_sec": None,
            "span_sec": None, "verdict": "unknown"}

# ---- 区間打点の補完材料（GitHub issue #161） --------------------------------
# #142 / #153 が既に読んでいる**起動時刻と終了時刻**をそのまま渡し、publish 側で「落ちた
# 区間だけ」を実測値で埋める。渡すのは agent transcript の実測時刻そのものなので
# `## 14` の禁止（*publish 時刻からの推定*）には当たらない。
# **打点漏れの実測値と射程の論拠は `publish-review-event.sh` の同節が正本**（数字を 2 箇所に
# 書くと更新漏れで食い違う）。**どのマーカーを埋めるかの判断も publish 側**（`agents` を
# 持つのがあちらのため）。
#
# **payload には載せない** — 絶対時刻は集計に使わず、載せると窓外の情報が payload に混ざる。
# `unresolved` がある回は出さない（wave 構成そのものが信用できない / #142 と同じ原則）。
wave_clock = None
if not unresolved and waves_by_msg:
    wave_clock = [
        {"n": len(w), "start": round(min(s for s, _ in w)),
         # 終了は **1 体でも取れなければ `None`**。取れた体だけで max を採ると「まだ回って
         # いた時間」が実態より短く出て、補完値が前倒しになる（#153 の縮退方向と揃える）
         "end": round(max(e for _, e in w)) if all(e is not None for _, e in w) else None}
        for w in sorted(waves_by_msg.values(), key=lambda w: min(s for s, _ in w))
    ]

if unresolved:
    # 旧い transcript（meta.json が無い）・窓の外で発行された agent・入れ子起動の親を
    # 引けない回。**「一括だった」にも「逐次だった」にも倒さない**（#149）
    dispatch["unresolved"] = unresolved
elif len(sub_first) == 1:
    # 1 体では wave の概念が立たない
    dispatch.update(waves=1, wave_sizes=[1], max_solo_run=1,
                    max_inter_wave_sec=0, inter_wave_agent_sec=0,
                    inter_wave_idle_sec=0, span_sec=0, verdict="single")
elif waves_by_msg:
    ordered = sorted(waves_by_msg.values(), key=lambda w: min(s for s, _ in w))
    sizes = [len(w) for w in ordered]
    heads = [min(s for s, _ in w) for w in ordered]
    solo_run = best_solo_run = 0
    for n in sizes:
        solo_run = solo_run + 1 if n == 1 else 0
        best_solo_run = max(best_solo_run, solo_run)
    inter = [b - a for a, b in zip(heads, heads[1:])]
    starts = sorted(s for w in ordered for s, _ in w)

    # **最大ギャップの内訳だけを割る**（GitHub issue #153）。`max_inter_wave_sec` が
    # 報告している当のギャップと同じ区間でないと、内訳と総和が対応しない。
    #
    # 縮退の向き: **終了時刻が 1 体でも取れなければ両方 -1（欠測）**。取れた体だけで
    # max を採ると「まだ回っていた時間」が実態より短く出て、**idle 側が過大**になる
    # ＝「オーケストレーターが遅い」という誤った打ち手を選ばせる（#153 の期待する動作）
    agent_sec = idle_sec = -1
    if inter:
        i = max(range(len(inter)), key=lambda j: inter[j])
        ends = [e for _, e in ordered[i]]
        if all(e is not None for e in ends):
            # wave i の agent が回り終えた時刻。次の wave 起動より後なら（前の層が
            # まだ走っているうちに次を出した回）ギャップ全体が agent 実行に埋まる
            last_end = max(ends)
            agent_sec = round(max(0.0, min(last_end, heads[i + 1]) - heads[i]))
            # **idle は引き算で出す**（`round(gap - agent)` ではなく `round(gap) - agent`）。
            # 両方を独立に丸めると和が `max_inter_wave_sec` と 1 秒ずれ、読む側に
            # 「3 つ目のバケツがある」と誤読させる。**内訳の和 == 総和**を成立させる
            idle_sec = max(0, round(inter[i]) - agent_sec)
    else:
        agent_sec = idle_sec = 0   # 1 wave = ギャップ無し。欠測ではない
    if len(ordered) == 1:
        verdict = "batched"          # 全体が同一メッセージ内の一括発行
    elif best_solo_run >= DISPATCH_SOLO_RUN:
        verdict = "serial"           # 1 体ずつ別メッセージで発行している
    else:
        # **多層だが違反の証拠が無い**。explorer → reviewer → 反証 のような層ごとの wave は
        # 設計上正当で、1 メッセージにまとめられない（`batched` に到達できないのが正常）
        verdict = "layered"
    dispatch.update(waves=len(ordered), wave_sizes=sizes, max_solo_run=best_solo_run,
                    max_inter_wave_sec=round(max(inter)) if inter else 0,
                    inter_wave_agent_sec=agent_sec, inter_wave_idle_sec=idle_sec,
                    span_sec=round(starts[-1] - starts[0]), verdict=verdict)


def k(v): return f"{v/1000:,.1f}k"

# **モデル世代の確定**（GitHub issue #169）。`main` は**単一世代の回にだけ**値を入れる。
# 実行中にモデルを切り替えた回（実測: self-review のセッションで opus-5 → opus-4-8 → opus-5）と
# 引き当て失敗はどちらも `None` に倒し、集計側で「mixed」の別バケツへ落とさせる。
# **どちらか片方を代表値として選ばない** — 選ぶと交絡したサンプルが単一世代の分布に混ざり、
# 「深さのコストが下がった」と「世代が違うから軽い」が永久に分離できなくなる（#156 / #150）。
#
# `sub_distinct` は集合で持つ。同一レビューで opus と sonnet が混在するのは**設計どおり**
# （ロール別ルーティング）なので、sub 側の複数値は混在の証拠ではない。層別キーは `main` で、
# `sub_distinct` は「エイリアスが親世代を継ぐ」前提が崩れた回を事後に検出するための証拠
# （`CLAUDE_CODE_SUBAGENT_MODEL` が立っていた回など / `docs/pipeline-design.md`）
MODELS_SCHEMA = 1
_main_models = sorted(models[False])
_sub_models = sorted(models[True])
models_out = {
    "schema": MODELS_SCHEMA,
    "main": _main_models[0] if len(_main_models) == 1 else None,
    "main_distinct": _main_models,
    "sub_distinct": _sub_models,
}

# **機械可読モード**（GitHub issue #126）: publish-review-event.sh が review の publish 時に
# 呼んで `tokens` フィールドへ載せる。取り込み内訳は payload に載せない（文字数であって
# トークンではなく、集計側で混ぜると桁が合わない — 上の `## 17` の注記と同じ理由）
# ---- `--per-agent`: 体ごとの cache_read と往復数（GitHub issue #156）--------
#
# **1 体あたりの読む量を決めているのは往復回数**（実測 r = 0.978 / n=22・1 run 内）。
# 1 往復あたりの cache_read は 63k〜124k とほぼ一定で、focus や担当ファイル量では
# 変わらない。したがって「担当ファイルを絞る」は往復数を減らさない限り効かず、
# 効くのは**探索予算（Read/Grep の回数上限）**の側。
#
# **`sub_agents` は再試行で膨らむ**。同一 focus が別 `toolUseId` で複数回起動された回は、
# 捨てられた試行ぶんも glob に載る（実測: 6 focus が 3 回ずつ起動し、総 cache_read の
# 48% が破棄された試行だった）。`--per-agent` は description を出すので重複が目視できる。
if os.environ.get("PER_AGENT") == "1":
    import statistics as _st
    rows = []
    for fpath, pa in per_agent.items():
        # `fpath` は `agent-*.jsonl` の glob 由来なので拡張子の分岐は要らない
        meta_p = fpath[: -len(".jsonl")] + ".meta.json"
        desc = depth = None
        try:
            mj = json.load(open(meta_p))
            desc, depth = mj.get("description"), mj.get("spawnDepth")
        except (ValueError, OSError):
            pass          # meta が無い / 壊れている回は focus 名なしで出す
        rows.append((desc or os.path.basename(fpath), depth, pa))
    if not rows:
        print("体ごとの内訳: 窓内に subagent が無い")
    else:
        rows.sort(key=lambda r: -r[2]["cr"])
        # `cache_write` / `output` も出す。重み付けは output x5 / cache_write x1.25 /
        # cache_read x0.1 なので、read だけ見ると単価の高い項を取りこぼす
        # （`design-notes/pending-optimizations.md` の計測の基準値）
        print(f"{'focus':<32}{'depth':>6}{'往復':>6}{'cache_read':>12}"
              f"{'/往復':>9}{'cache_write':>13}{'output':>10}")
        print("-" * 88)
        for desc, depth, pa in rows:
            per = pa["cr"] / pa["n"] if pa["n"] else 0
            print(f"{str(desc)[:31]:<32}{str(depth if depth is not None else '?'):>6}"
                  f"{pa['n']:>6}{k(pa['cr']):>12}{k(per):>9}"
                  f"{k(pa['cw']):>13}{k(pa['out']):>10}")
        crs = [r[2]["cr"] for r in rows]
        if len(crs) > 1:
            lo, hi = min(crs), max(crs)
            cv = _st.pstdev(crs) / _st.mean(crs) if _st.mean(crs) else 0
            print()
            print(f"回内分散: 中央値 {k(_st.median(crs))} / 最小 {k(lo)} / 最大 {k(hi)}"
                  f" / 最大最小 {hi / lo:.1f} 倍 / 変動係数 {cv:.2f}")
        dup = {}
        for desc, depth, _ in rows:
            dup[desc] = dup.get(desc, 0) + 1
        repeated = {d: c for d, c in dup.items() if c > 1}
        if repeated:
            print(f"⚠️ 同一 focus の重複起動: {len(repeated)} 種"
                  f"（再試行ぶんが体数と総量を膨らませている / #156）")
    raise SystemExit(0)

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
        # **窓内に起動した agent の発行パターン**（`sub_agents` と同じ窓）。publish が payload の
        # `dispatch` に載せ、`verdict == "serial"` のとき警告する（`layered` は層ごとの wave
        # ＝設計上正当なので警告しない / #149）
        "dispatch": dispatch,
        # **区間打点の補完材料**（issue #161）。wave ごとの `{n, start, end}`（epoch 秒）。
        # `end` は wave 内の全体の終了時刻が取れたときだけ入る
        "wave_clock": wave_clock,
        # **モデル世代**（issue #169）。層別キーは `main`（単一世代の回だけ非 null）
        "models": models_out,
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
# **`if agents:` の elif 連鎖の外に置く**（間に挟むと「1 体だけ起動した回」で
# 『transcript が見つからない』が誤発火する）
if dispatch["verdict"] in ("serial", "layered", "batched"):
    label = {"serial": "逐次発行", "layered": "層ごとの発行", "batched": "一括発行"}[dispatch["verdict"]]
    print("発行パターン    : %s（%d 体 / %d wave %s / wave 間の最大 %ds）"
          % (label, dispatch["agents"], dispatch["waves"],
             "+".join(str(n) for n in dispatch["wave_sizes"]), dispatch["max_inter_wave_sec"]))
    if dispatch["verdict"] == "serial":
        print("   → 同一フェーズは 1 メッセージで一括発行する。fleet は**wave 内最長の 1 体**で"
              "決まる（orchestration-guide.md `## 0`「並列発行の明示」）")
elif dispatch.get("unresolved"):
    # 判定を諦めた回を黙って落とさない（`batched` にも `serial` にも倒さない / #149）
    print("発行パターン    : 判定不能（%d 体中 %d 体の発行元メッセージを引けない）"
          % (dispatch["agents"], dispatch["unresolved"]))
# **モデル世代**（issue #169）。`main` が空＝混在か引き当て失敗で、集計側では層別に使えない回
if models_out["main_distinct"] or models_out["sub_distinct"]:
    if models_out["main"]:
        _m = models_out["main"]
    elif models_out["main_distinct"]:
        _m = "混在（%s）" % "/".join(models_out["main_distinct"])
    else:
        _m = "不明"
    print("モデル世代      : main=%s / sub=%s"
          % (_m, "+".join(models_out["sub_distinct"]) or "-"))

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
