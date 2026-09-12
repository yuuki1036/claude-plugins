---
description: "diff で追加・変更したコード内コメントを精査して直す（2 観点の推敲 + git 外 ID の除去）。差分提示 → 承認 → 適用 トリガー: 「コメント精査」「コメント整理」「コメントを直して」「コメントの ID を消して」「/comment-polish」 引数: [base branch] [--staged] [--embed] [--from-findings <path>] [--github]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - AskUserQuestion
argument-hint: "[--staged | base branch] [--embed] [--from-findings <path>] [--github]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/comment-polish/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

comment-polish スキルを使用して、現在の diff で追加・変更したコード内コメントを精査してください（2 観点の推敲 + git 外の参照 ID の除去）。

引数が渡されていればそれも考慮してください（`--staged` / base ブランチ / `--embed` / `--from-findings <path>` / `--github`）。
