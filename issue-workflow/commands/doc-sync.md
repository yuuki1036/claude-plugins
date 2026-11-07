---
description: "repo の文書（仕様書・規約・ADR）とコードコメント・実装・決めたことの整合を確かめ、食い違いと文書への未反映を文書の行を引いて一覧にし、承認した分だけ直す。 トリガー: 「文書整合」「仕様書とコードコメントの整合性を確認」「仕様書に反映されているか」「doc sync」「/doc-sync」"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
  - Agent
argument-hint: "[--base <ref>] [--issue <path>] [--report-only]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/doc-sync/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

doc-sync スキルを使って、diff・Issue ファイル・このセッションで決めたことと、repo の文書（仕様書・規約・ADR）・コードコメントの整合を確かめてください。
食い違いと文書への未反映を文書の行を引いて一覧にし、直し方の案を出してください。書き換えは承認された分だけにしてください。

このセッションの effort: `${CLAUDE_EFFORT}`（SKILL.md の Phase 1 で、Bash の `CLAUDE_EFFORT` が空のときだけ使う。SKILL.md は Read で読むのでこの変数が展開されない）

引数: $ARGUMENTS
