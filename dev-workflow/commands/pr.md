---
description: "差分とコミット履歴からPRを自動作成する"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - Skill
  - mcp__linear__get_issue
  - mcp__linear__list_comments
  - mcp__github__create_pull_request
  - mcp__github__update_pull_request
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/pr` でも `Skill` tool の `dev-workflow:pr` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `dev-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。**SKILL.md が持つのは、全 Step に効く厳守ルールと、Step の並び・Read の行だけで、各 Step の手順は `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/steps/step-<番号>.md` にある。Step に入るたびに、その見出しの下の Read の行が指すファイルを読んでから進む**（GitHub issue #447）。

pr-creator スキルを使用して、現在のブランチの差分とコミット履歴から PR を作成してください（既定はドラフト。リポジトリ規約が draft 以外を指定する場合はそちらに従う）。PR 本文はユーザーの承認を得てから作成してください。

Linear Issue連携が可能であればIssue情報も活用してください。
