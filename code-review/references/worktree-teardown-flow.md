# worktree teardown 連携（self-review Step 8 / 非 embed のみ）

self-review の**最終ステップ**の正本。`--embed` では実行しないので、SKILL 本文ではなくここに置く（本文サイズは毎セッションの読み込み量に直結する）。

起動タイミングと skip 条件の判断は SKILL 側が持ち、**発動が確定してから**この doc を Read する。

## 手順

レビュー完了後に作業用 worktree（dev-workflow:worktree-setup で作成。識別マーカー: worktree 内の `envs/.backend.env.worktree`）が放置されるのを防ぐ後片付け。Step 7 の修正方針フロー（修正を選んだ場合はその実施）まで**すべて完了した後**の最終ステップとして実行する（teardown は cwd＝worktree 自体を削除するため、後続ステップを残した状態で起動してはならない）。

**発動条件（すべて満たす場合のみ。欠けたら silent skip）**:

1. `--embed` 指定なし（embed mode では呼び出し元の UX を阻害しないため skip）
2. worktree 内で実行中: `git rev-parse --git-dir` ≠ `git rev-parse --git-common-dir`
3. worktree-setup 由来である: `[ -f envs/.backend.env.worktree ]`（マーカーの無い無関係な worktree でレビューのたびに削除プロンプトを出さない）
4. 未コミット変更が無い: `git status --porcelain` が空（self-review はコミット前ゲートであり、指摘修正やコミット前の作業が残る状態で削除を提案するのは 1 手早い。dirty なら黙って skip する）
5. dev-workflow が**有効**である:
   ```bash
   DEV_WORKFLOW=0
   for f in "$HOME/.claude/settings.json" ".claude/settings.json" ".claude/settings.local.json"; do
     grep -Eq '"dev-workflow@[^"]*"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null && DEV_WORKFLOW=1
   done
   ```
   キー存在だけを見る grep は使わない（`": false"` の無効化済みを導入済みと誤判定し、project-scoped 有効化を取りこぼすため。enabled-only 判定）

発動時、**AskUserQuestion** で削除の意思を確認する（worktree・DB・env は git で復元できない不可逆操作のため、「止めない」原則の例外として確認する。teardown 自身は clean tree の `git worktree remove` を確認なしで実行するため、削除の同意は必ずここで取る）:

- question: "この worktree での作業は完了していますか？worktree を削除（teardown）できます"
- header: "worktree"
- multiSelect: false
- options:
  1. label: "残す" / description: "worktree を維持する（マージ・push 等が残っている場合はこちら）"
  2. label: "削除する" / description: "dev-workflow:worktree-teardown を起動して DB / port / worktree を片付ける"

「削除する」が選ばれたら `Skill` tool で `dev-workflow:worktree-teardown` を起動する。プロセス kill / DB drop / `--force` remove の個別確認は teardown 側の cleanup チェックリストに従う。
