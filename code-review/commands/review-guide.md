---
description: "PR（または base 指定のローカル diff）を人間が後から理解するための読み順ガイドを出す。精読に値するファイルだけを 1〜5 件選び、実装の流れ順に並べ、各ファイルに 何をした / 難点 / 見る行 / レビュー観点 を付ける。投稿・永続化はしない。--walkthrough では精読を 1 件ずつ解説し、見つけた修正をその場で入れる（読み合わせ） トリガー: 「PR の読み方」「読み順」「この PR を解説して」「このPR何やってる」「PR を理解したい」「読み合わせ」「/review-guide」 引数: [PR番号 | --base <ref>] [--top N] [--walkthrough]（省略時は現在ブランチの PR）"
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
  - Edit
argument-hint: "[PR番号 | --base <ref>] [--top N] [--walkthrough]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/review-guide/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

review-guide スキルを使用して、対象 PR（または `--base <ref>` のローカル diff）の読み順ガイドをセッションに出力してください。ファイル作成・コメント投稿・push・commit・Issue 起票は行いません。書き込みは base モードの読み順の記録 1 件（SKILL.md Step 5）と、読み合わせ（`--walkthrough` の回か、解説の途中で直すよう言われた回）で入れるコードの修正（SKILL.md Step 6・7。作業ツリーが diff の対象そのものの回だけ）だけです。

引数が渡されていればそれも考慮してください（PR 番号 / `--base <ref>` / `--top N` / `--walkthrough`）。
