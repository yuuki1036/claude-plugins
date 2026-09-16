---
description: "PR（または base 指定のローカル diff）を人間が後から理解するための読み順ガイドを出す。重要ファイルを精読 N 件に絞り、実装の流れ順に並べ、各ファイルに 何をした / 難点 / 見る行 / レビュー観点 を付ける。読み取り専用で投稿・修正・永続化はしない トリガー: 「PR の読み方」「読み順」「この PR を解説して」「このPR何やってる」「PR を理解したい」「/review-guide」 引数: [PR番号 | --base <ref>] [--top N]（省略時は現在ブランチの PR）"
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
argument-hint: "[PR番号 | --base <ref>] [--top N]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

review-guide スキルを使用して、対象 PR（または `--base <ref>` のローカル diff）の読み順ガイドをセッションに出力してください。ファイル作成・コメント投稿・コード修正は行いません。

引数が渡されていればそれも考慮してください（PR 番号 / `--base <ref>` / `--top N`）。
