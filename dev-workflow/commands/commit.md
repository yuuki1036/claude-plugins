---
description: "変更を分析して原子性重視の高品質コミットを作成する"
allowed-tools:
  - Bash
  - Read
  - Skill
  - AskUserQuestion
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/git-commit-helper/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/commit` でも `Skill` tool の `dev-workflow:commit` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `dev-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない。`git commit` を直接打たない / GitHub issue #219）。

git-commit-helper スキルを使用して、現在の変更を分析し、適切な単位に分割してコミットを作成してください。

引数が渡されていればそれも考慮してください（例: --no-protect, --with-push）。
