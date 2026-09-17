---
name: worktree-gc
description: |
  散らばった git worktree を横断検出・分類・安全確認して一括削除する棚卸し (GC)。
  scan（副作用なし・機械可読出力）→ 承認 → reap（承認済み行のみ削除）の 2 段で、表に出したものだけが消える。
  `--all` で PC 横断、review 残骸（detached）は HEAD の PR 状態で、PR 無しブランチは Linear Issue の状態で判定を補う。
  トリガー: 「worktree 棚卸し」「worktree 一括削除」「worktree GC」「残骸 worktree を掃除」「worktree gc」「/worktree-gc」
effort: medium
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - mcp__linear__get_issue
---

# worktree-gc

現リポ（`--all` なら root 配下の全リポ）に溜まった git worktree を検出・分類し、損失リスクのないものだけを承認の上で一括削除する。`scan.sh`（副作用なしの列挙）と `reap.sh`（承認済み行のみを消す実行）の 2 段に分かれ、**承認の表に出したものだけが消える**ことを入力契約で担保する（ADR-20260912142858）。

## teardown / setup との使い分け

| 状況 | スキル |
|---|---|
| **散らばった多数の worktree を棚卸しして GC する** | **worktree-gc**（本スキル） |
| 1 worktree を丁寧に破棄する（DB drop / port 解放 / env クリーンアップ） | `worktree-teardown` |
| 並列開発環境を作る（DB 名 / port を導出） | `worktree-setup` |

`worktree-teardown` は「worktree の**中から**実行・main clone では exit 1・現 worktree の env に書かれた port のみ対象」を厳守ルールに持つ。worktree-gc は逆に **main clone / 任意の worktree から複数を横断して**扱うため、teardown の phase 追加ではなく別スキルにした（前提が反転する）。単数の「worktree 削除 / 破棄」は teardown の担当で、本スキルのトリガーには入れない。

## 適用範囲

- 現リポに複数の worktree（開発用・レビュー残骸・agent worktree）が溜まっている
- `git worktree list` に prunable な残骸（dir を消したが git 管理に残っている）がある
- PC 全体を横断したい（`--all [root]`。root の既定は環境変数 `DEV_WORKFLOW_WORKTREE_GC_ROOT` → `.claude/dev-workflow.json` の `worktree_gc_root` → `$HOME`）
- review 残骸（`.claude/worktrees/` 配下・detached）が溜まっている。HEAD に紐づく PR が merged / closed なら reap 候補に載る
- 調査だけで完結し PR を作らなかった Issue の worktree が残っている。ブランチ名の Issue ID（`PRE-1` 型）を Linear で引き、Done / Canceled なら reap 候補に載る（Step 1.5）

## 実行手順

### Step 0: 起動位置の確認

main clone / worktree 内どちらから起動してもよい。scan は起動時の cwd を含む worktree を `self` として必ず保持する。

### Step 1: scan（列挙）

`scan.sh` を実行し、現リポの全 worktree を 1 行 1 JSON で取得する（副作用なし）。

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-gc/scan.sh"
```

- 各行のフィールドと分類規則（安全ゲート・verdict）の正本は [references/classification.md](references/classification.md)
- `verdict: "keep"` の行はそのまま保持。`verdict: "reap"` の行が削除候補
- `lsof` が無い環境では `--no-lsof` を付ける（`live_pids` を unknown 扱いにし保守的に keep）。`${CLAUDE_EFFORT}` が `low` / `medium` のときは省略してよい（対象が少数なら lsof は軽いので既定では回す）
- ユーザーが横断を求めたら `--all [root]` を付ける（root 省略時の既定は上の「適用範囲」）。`${CLAUDE_EFFORT}` が `xhigh` / `max` なら `--depth 6` で走査を広げる（分類ロジックは effort で変えない）。リポごとに `gh pr list` を 1 回叩くので、リポ数 × 1〜2 秒かかる
- detached な worktree（review 残骸）は HEAD の sha から PR を引く（`gh api commits/<sha>/pulls`）。gh が無い / 引けないときは従来どおり keep に倒れる

### Step 1.5: Issue 状態の取り込み（Linear MCP が使えるときのみ）

scan の出力に `issue.id` を持ち、かつ reasons に `no-pr-not-merged` / `no-pr-ahead` がある行が 1 つでもあれば、Linear MCP で状態を引いて scan をやり直す。**Linear MCP が未接続 / 未認証なら本ステップを飛ばす**（従来どおりの分類で続行。機能低下は許容）。

1. 対象の `issue.id` を重複なく集める（例: `jq -r 'select(.issue != null and (.reasons | index("no-pr-not-merged") or index("no-pr-ahead"))) | .issue.id' /tmp/wtgc-scan.jsonl | sort -u`）
2. 各 ID を `mcp__linear__get_issue` で引き、状態の **名前と type** を取る（type は Linear の workflow state type: `completed` / `canceled` / `started` / `unstarted` / `backlog` / `triage`。判定は type が正で、名前は表示用）
3. 状態ファイルを書く。**値は jq に `--arg` で渡す**（Issue 名・状態名は外部入力）:

```bash
jq -n --arg id "PRE-1" --arg state "Done" --arg type "completed" \
  '{($id): {state: $state, type: $type}}' > /tmp/wtgc-issues.json
# 複数件は `jq -s 'add'` でまとめる
```

4. `scan.sh --issue-status /tmp/wtgc-issues.json` で再 scan する（`--all` 等の他オプションは 1 回目と同じにする）。閉じている Issue の行は `no-pr-*` が外れて `issue-closed:<ID>:<状態>` が付き、open の行は keep のまま `issue-open:<ID>:<状態>` が付く

### Step 2: 分類表の提示

scan の出力を読み、**削除候補（reap）と保持（keep）を理由つきの表**に整形してユーザーに提示する。

- keep の行は `reasons`（self / primary-worktree / dirty / live-or-unknown-process / pr-open / no-pr-not-merged / no-pr-ahead。Issue 状態を引いた行は `issue-open:<ID>:<状態>` も）をそのまま添える
- reap の行は path / branch（detached なら `head` の短縮 sha）/ kind / PR 状態 / Issue 状態（`issue-closed:<ID>:<状態>`）を並べる
- `--all` のときはリポ（`repo`）ごとに表を分ける
- session 一覧が使える環境（ccd_session_mgmt 等）では、実行中 session に紐づく worktree を keep 側へ倒す（optional 信号。keep 方向にしか使わない）

### Step 3: 承認（AskUserQuestion）

削除は不可逆なので**必ず承認を取る**（「起動＝実行確定」の例外にあたらない）。`AskUserQuestion` で:

- question: 「以下の N 件を削除します。よいですか？」（表を本文に併記）
- options:
  1. 「削除する」— reap 候補すべてを削除
  2. 「一部だけ削除」— 残す行を選ばせる（選ばれた行は reap 入力から外す）
  3. 「中止」— 何も削除しない

### Step 4: reap（実行）

承認された reap 行だけを `reap.sh` に stdin で渡す。**scan が出した行をそのまま渡す**（行を選ぶことはあっても書き換えない）。

```bash
# 承認された行だけを reap に渡す（例: scan 出力を保存し、承認で絞ってから流す）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-gc/scan.sh" > /tmp/wtgc-scan.jsonl
# reap は verdict=reap 以外の行を exit 2 で拒否するので、承認で絞った reap 行だけを渡す
jq -c 'select(.verdict=="reap")' /tmp/wtgc-scan.jsonl \
  | bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-gc/reap.sh" --dry-run
```

- **まず `--dry-run` で would remove を確認してから**、承認済みなら `--dry-run` を外して実行する
- reap は nested（agent）→ 親（review）の順で `git worktree remove` し、最後にリポごとに `git worktree prune`（行の `repo` を見るので `--all` の出力もそのまま渡せる）
- marker（`envs/.backend.env.worktree` の `DB_NAME`）のある行だけ DB drop 候補になる。**marker 無し行は DB に触れない**（名前一致は所有権を証明しないため / F1）
- 削除直前に `live_pids` を再取得し、scan 後に使い始めた worktree は SKIP する

### Step 5: 完了レポート

reap の出力（removed / SKIP / 失敗 / DB drop / 手動案内の件数）をそのままユーザーに提示する。失敗行には手動コマンドが併記されている。

## 絶対厳守ルール

- **承認なしで reap しない**。削除は不可逆で、AskUserQuestion 例外（起動＝実行確定）の対象外
- **reap には scan が出した行をそのまま渡す**。verdict を書き換えて渡すのは入力契約違反（reap が exit 2 で拒否する）
- **marker 無し行の DB は drop しない**。sanitize は非単射で、名前一致は別 worktree / 本番 DB を掴む経路になる
- **プロセスを kill しない**。生存プロセスのある worktree は keep して PID を表示するだけ（誤 kill の被害が worktree 誤削除より大きい）
- `--dry-run` で内容を確認してから本実行する

## Additional Resources

### Reference Files

- **`references/classification.md`** - scan の出力フィールド・安全ゲート・reap 入力契約の正本
- 設計の全体像・却下した代替案: `.claude/designs/20260912-worktree-gc-skill.md`
- 「列挙と実行を別プロセスに分ける」設計判断: `.claude/adr/20260912142858-enumerate-then-reap-split.md`
