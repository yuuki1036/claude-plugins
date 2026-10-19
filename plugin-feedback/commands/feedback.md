---
description: プラグインの改善要望・バグ報告を GitHub Issue として作成する
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/feedback-issue/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/feedback` でも `Skill` tool の `plugin-feedback:feedback` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `plugin-feedback@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。SKILL.md と `references/` の中の `${CLAUDE_PLUGIN_ROOT}` も、SKILL.md を読んだのと同じ root に読み替える。

起票先は公開リポジトリなので、**SKILL.md を読めなければ起票せずに中止して報告する**。どの経路でも、Step 3.7（匿名化）と Step 4（承認）を通さずに投稿しない。

この command から入った回は、次の 2 点が skill の手順と違う:

- 利用者が `/feedback`（`/plugin-feedback:feedback` を含む）を入力した回は、起票を明示的に求めた回として Step 1（提案）を飛ばす。会話の流れでモデルがこの command を選んだ回は Step 1 から通す
- `$ARGUMENTS` にプラグイン名や要望内容が含まれていれば、Step 2 でそれを材料にする（重複して聞かない）
