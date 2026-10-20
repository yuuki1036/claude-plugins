---
description: "セッション開始。引数の Issue ID を優先し、無ければブランチ名から判定（main ならダッシュボード）。新規着手なら feature-dev 起動の確認を出す トリガー: 「作業開始」「セッション開始」「今日の作業」「/start」 引数: [Issue ID] [今回の意図]（省略可）"
allowed-tools:
  - Agent
  - Skill
  - AskUserQuestion
  - EnterWorktree
  - mcp__linear__get_issue
  - mcp__linear__list_issues
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - TodoWrite
argument-hint: "[Issue ID] [今回の意図（「新規タスク」or やること）]（すべて省略可）"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/start/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

start スキルを使って、セッション開始時の作業準備をしてください。

引数: $ARGUMENTS

引数は `{Issue ID} [今回の意図（自由記述）]` の形で解釈してください。

- 第 1 トークンが Issue ID（`[A-Z]+-\d+` 形式）なら、**ブランチ名より優先**してその Issue を対象にしてください（ブランチが main のままでも Feature ブランチモードで読み込む）。その Issue の作業が別の worktree やブランチに既にあるか、そこへ移るかは Phase F2.5 が決めます（session-context だけで結び付いた（Claude アプリが作る）detached HEAD の worktree には移らず案内だけする。判定の細部は SKILL.md の F2.5 に従い、ここから推測しない）。
- 残りの文字列は「今回の意図」です。**やることの中身が書かれていなければ新規着手**（例: `TEAM-123 新規タスク`）、**書かれていれば継続作業**（例: `TEAM-123 ログイン画面のバリデーション直す`）として Phase 1 の `TASK_INTENT` に分類してください。
- 新規着手の場合、Phase F7 で **進め方の確認（feature-dev / 軽量フロー / 自分で進める の AskUserQuestion）を必ず出す**こと。コミット数や `feature_dev_plan:` を理由にスキップしないでください（既存のコミットがあっても確認は出す。ただしブランチは新しく作らず既存のものを使う。確認を出さずに報告・案内だけする回 — Issue が completed / canceled、作業が session-context だけで結び付いた detached HEAD の worktree にしか無い、など — は SKILL.md の F7 に従う）。
- 引数が空なら従来どおりブランチ名から判定してください。
