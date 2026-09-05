---
description: "Issue 化前の設計収束ドキュメント (living spec) を作成・運用する トリガー: 「living spec」「リビングスペック」「living spec 作る」「OQ 台帳」「Open Questions 台帳」 「OQ 追加」「Decision log」「決定を記録して OQ を閉じる」「確度ラベル」「収束率」 「Issue 化前に未確定を詰めたい」「設計を収束させたい」「/living-spec」"
user_invocable: true
allowed-tools:
  - AskUserQuestion
  - Bash
  - Edit
  - Glob
  - Read
  - Write
---

`living-spec` スキルを使って、Issue 化前の設計収束ドキュメント (living spec) を管理してください。

## 引数

`$ARGUMENTS` の第 1 引数は**常にサブコマンド**として解釈します（slug は `init` の後ろにしか置けません）:

- `init [slug]` → `.claude/living-specs/<slug>.md` を scaffold（既存なら中止）
- `oq <text>` → OQ 台帳に append（`OQ<max+1>` を機械採番 / `status: open` / `since` を機械付与）
- `oq list [--all]` → OQ 一覧（既定は open のみ。`--all` で closed 込み）
- `decision <text>` → Decision log に append（`D<max+1>` を機械採番）し、関連 OQ を close して双方向参照を成立させる
- `spec <項目> <確度>` → 仕様表の確度ラベル（`確定` / `方向性(仮)` / `未定`）を更新し `since` を機械付与
- `status` → 進捗ビュー（収束率 + open OQ 残数 + セッション再開導線）

`init` 以外は `--spec <slug>` で対象ファイルを明示指定できます（省略時: 1 件なら自動 / 複数なら選択 / 0 件なら init を案内）。

引数なしは usage を報告して終了します（**既定のサブコマンドを持ちません**）。未知の第 1 引数も slug とみなさず、不明なサブコマンドとして報告して終了します。整合・鮮度チェックは `/living-spec-maintain` の領分です（`maintain` を渡すとそちらへ案内します）。

## 実行

`living-spec` スキルの処理フローに従ってください:

1. Phase 0: 保存先確認（`.claude/living-specs/`、無ければ作成）+ サブコマンド判定 + 対象ファイル特定
2. Phase 1-3: init（slug の命名規則検証 / 既存なら中止 → `date` 取得 → 衝突確認 → template 置換 → Write）
3. Phase 4: oq（採番 → append）/ oq list（読むだけ）
4. Phase 5: decision（採番 → 関連 OQ を選ばせる → append → OQ を close → 双方向参照を Read で検証）
5. Phase 6: spec（確度の 3 値検証 → 項目で引き当て → 確度と since を更新）
6. Phase 7: status（収束率と open OQ 残数を集計）

書式の正本は `skills/living-spec/references/format-spec.md` です（表スキーマ・確度ラベル 3 値・採番規約・パース正規表現）。日付は必ず Bash の `date` で取得し、擬似日付を作らないでください。**採番の前に HTML コメント区間を除去する**こと（コメント内の記入例を実在 ID として数えないため）。
