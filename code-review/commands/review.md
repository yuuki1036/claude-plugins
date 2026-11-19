---
description: "PRのコードレビューを実行する（2フェーズ構成・専門エージェント動的起動） トリガー: 「レビューして」「/review」「コードレビュー」 引数: [PR番号] [--emergency] (省略時は現在ブランチのPRを自動取得。--emergency は本番ホットフィックス向けの最小構成レビュー)"
allowed-tools:
  - Bash
  - Read
  - Write
  - Agent
  - EnterWorktree
  - ExitWorktree
  - AskUserQuestion
  - Skill
argument-hint: "[PR番号] [--emergency] (省略時は現在のブランチのPRを自動取得。--emergency は本番ホットフィックス向けの最小構成レビュー)"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。**SKILL.md が持つのは、全 Step に効く節（前提・パイプライン設計など）と、Step の並び・Read の行だけで、各 Step の手順は `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-<番号>.md` にある。Step に入るたびに、その見出しの下の Read の行が指すファイルを読んでから進む** — Step 7 のレポートテンプレートを読まないまま締めた回は 3/3 で定型を出さなかった（GitHub issue #250 / #447）。

review スキルを使用して、指定されたPR（または現在のブランチに紐づくPR）のコードレビューを実行してください。

引数が指定されている場合はそれをPR番号として使用してください。
