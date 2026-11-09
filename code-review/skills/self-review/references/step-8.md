### 8. worktree teardown 連携（非 embed のみ）

レビュー完了後に作業用 worktree が放置されるのを防ぐ後片付け。Step 7 の修正方針フロー（修正を選んだ場合はその実施）まで**すべて完了した後**の最終ステップとして実行する（teardown は cwd＝worktree 自体を削除するため、後続ステップを残した状態で起動してはならない）。

**`--embed` 指定時は skip**（呼び出し元の UX を阻害しない）。それ以外では `${CLAUDE_PLUGIN_ROOT}/references/worktree-teardown-flow.md` を Read し、発動条件（worktree 内か / worktree-setup 由来か / tree が clean か / dev-workflow が有効か）と AskUserQuestion の確認手順に従う。**条件が 1 つでも欠けたら silent skip**。削除の同意が取れたときだけ `Skill` tool で `dev-workflow:worktree-teardown` を起動する。

**ここで終わり**
