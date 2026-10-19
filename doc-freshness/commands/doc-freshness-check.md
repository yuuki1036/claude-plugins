---
description: ドキュメント鮮度を機械的に検証する（frontmatter / phase stale / 行数 / link / superseded）
user_invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - Write
  - AskUserQuestion
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/doc-freshness/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/doc-freshness-check` でも `Skill` tool の `doc-freshness:doc-freshness-check` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `doc-freshness@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

doc-freshness スキルを使って、ドキュメント鮮度を検証してください。

## 引数

`$ARGUMENTS`:
- 未指定 → プロジェクト全体走査
- ファイルパス指定（例: `CLAUDE.md`） → 単一ファイル走査
