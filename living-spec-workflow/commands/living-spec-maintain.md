---
description: "living spec の整合と鮮度を 8 段のファネルで検証する。収束率や open OQ を見るだけなら living-spec の status（こちらは壊れていないかの検証） トリガー: 「living spec の整合チェック」「living spec を点検」「OQ と Decision の参照が合ってるか」 「確度ラベルの塩漬けを検出」「living spec の鮮度チェック」「living spec lint」「/living-spec-maintain」"
user_invocable: true
allowed-tools:
  - AskUserQuestion
  - Bash
  - Edit
  - Glob
  - Read
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/living-spec-maintain/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `living-spec-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

`living-spec-maintain` スキルを使って、living spec の整合と鮮度を検証してください。

## 引数

`$ARGUMENTS`:
- 省略 → 対象を自動特定（1 件なら自動 / 複数なら選択 / 0 件なら案内して終了）
- `--spec <slug>` → `.claude/living-specs/<slug>.md` を対象にする
- `--all` → `.claude/living-specs/*.md` の全件を対象にする

## 実行

`living-spec-maintain` スキルの処理フローに従ってください:

1. Phase 0: 対象特定 + doc-freshness の縮退判定 + `${CLAUDE_EFFORT}` 分岐
2. Phase 1: 前処理（HTML コメント区間の除去。失敗したら段 1 Critical で fail-closed）
3. Phase 2: 機械判定 段 1-7（段 1-3 に Critical が出たら段 8 に進まない）
4. Phase 3: 段 8 の LLM 判断（`high` 以上 かつ Critical 0 件のときのみ）
5. Phase 4: レポート → Critical 0 件なら `last-validated` の更新を確認

判定ルールの正本は `skills/living-spec-maintain/references/check-rules.md`、入力契約（表スキーマ・語彙・採番規約・パース正規表現）の正本は `skills/living-spec/references/format-spec.md` です。

**前処理を省かないでください**。HTML コメント区間を除去せずに判定すると、テンプレや説明コメント内の記入例を実在の行・ID として数え、段 2（採番）と段 3（相互参照）が偽陽性を出します。日付は必ず Bash の `date` で取得してください。
