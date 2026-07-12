---
description: 文章を語句レベルで推敲・添削する（冗長削り・曖昧語の具体化・トーン統一・AI っぽさ除去）。差分提示 → 採否フロー
user_invocable: true
argument-hint: "[text | ファイルパス | 省略時は直近の生成テキスト] [--embed] [--tone <種別>] [--aggressive]"
allowed-tools:
  - Read
  - Edit
  - AskUserQuestion
  - Bash
---

`writing-polish` スキルを実行して、文章を推敲・添削する。

対象: $ARGUMENTS

校正手順とルールは `writing-polish` skill に従う（`skills/writing-polish/SKILL.md`、校正ルールの正本は `references/tone-guide.md`、提示・採否 UX の正本は `references/presentation-guide.md`）。

- 引数がテキストならそれを、ファイルパスなら読み込んだ内容を、省略なら直近の自分の生成テキストを対象にする。
- `--embed` 指定時は採否確認を出さず推敲結果のみ返す（他プラグインからの呼び出し用）。
- `--tone <種別>` で文書種別（commit / pr / issue / rfc / review / code-comment 等）を明示できる。`code-comment` はコードコメント校正（別正本 `code-comment-guide.md`。what 削除・subtype 別保全）に分岐する。
- `--aggressive` で任意の言い換え提案まで広く出す。

中核原則（最小差分・過剰修正の抑制・原文の声の保持・構造の不変更）を必ず守る。
