---
description: "code-review の計測結果（review:completed の蓄積）を更新し、前回からの差分・比較表・`## 15` の更新条件・語彙落ちを集計して、関連 issue へのコメントと改善案の起票までを固定の手順で回す。投稿・起票は承認を取ってから行う トリガー: 「計測を更新」「計測結果を更新して」「metrics update」「/metrics-update」 引数: [--split-version <版>]（省略可）"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
argument-hint: "[--split-version <版>]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/metrics-update/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

metrics-update スキルを使用して、code-review の計測結果を更新し、関連 issue へのコメントと改善案の起票を手順どおりに進めてください。コメントと起票は、本文のプレビューに承認を得てから投稿します。

引数が渡されていればそれも考慮してください（`--split-version <版>`）。
