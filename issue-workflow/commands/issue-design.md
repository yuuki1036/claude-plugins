---
description: "Issue 本文を 9 セクションテンプレと設計判断ルールに沿って設計・構造化・リライトする トリガー: 「Issue 設計」「Issueの書き方」「Issueを設計し直す」「Issueリライト」「設計判断どう書く」「決定とopenの仕分け」「9セクション設計」「/issue-design」"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Skill
  - AskUserQuestion
argument-hint: "[ISSUE-ID | リライト対象]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/issue-design/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

issue-design スキルを使って、Issue 本文を 9 セクション構造で設計・リライトしてください。
新規起票が目的の場合は issue-create に切り替えてください。
