---
description: "PR に付いたレビューコメント（bot / 人間）への対応を仕分ける。指摘ごとにコードで妥当性を確かめ、帰属と対応（fix now / follow-up / 返信のみ / 要確認）を決めて返信の下書きまで出す。投稿・修正はしない トリガー: 「レビューコメントを精査」「レビュー対応を仕分けて」「review comment 精査」「/review-triage」 引数: [PR番号]（省略時は現在ブランチの PR）"
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
  - Skill
argument-hint: "[PR番号]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/review-triage/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

review-triage スキルを使用して、PR に付いているレビューコメントを精査し、対応を仕分けて返信の下書きを出してください。投稿・push・コード修正は行いません。

引数が渡されていればそれも考慮してください（PR 番号）。
