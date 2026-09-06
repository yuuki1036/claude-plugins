---
description: "candidates（自己訂正の自己申告）をレビューして journal に昇格し、30日×3回閾値超えのパターンを規約還流提案に変換する。候補が無い期間は transcript サルベージにフォールバック トリガー: 「retro」「振り返り集計」「再発パターン抽出」「failure 集計」 「同じ失敗を何回踏んだ」「規約還流」「未起票の失敗を拾って」「/retro」"
user_invocable: true
allowed-tools:
  - Read
  - Bash
  - Agent
  - AskUserQuestion
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/retro/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `failure-journal@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

retro スキルを使って、再発する失敗パターンを集計し還流提案を生成してください。

## 引数

`$ARGUMENTS`:
- 未指定 → デフォルト窓（直近 30 日）・デフォルト閾値（同一 tag 3 回以上）で集計
- 数値指定（例: `60`） → 集計窓の日数を上書き
- `--salvage` → candidates の有無に関わらず transcript 走査（Phase 0.6）も実行する
- `--no-salvage` → transcript 走査を禁止する（candidates レビューは実行する）

## 実行

`retro` スキルの処理フローに従ってください:

1. Phase 0: journal 読み込み（retro 実行中のみ参照可）
2. Phase 0.5: 候補レビュー（candidates.jsonl の verdict:null 行 → REAL/NOISE 分類 → 承認 → journal 昇格 → verdict 書き戻し）
3. Phase 0.6: transcript サルベージ（フォールバック: --salvage 明示 or 候補 0 件のみ）
4. Phase 1: 窓・閾値の決定（30 日 / 3 回）
5. Phase 2: tag 別集計（Bash + jq、30 日境界フィルタ → group → count）
6. Phase 3: 閾値超え tag の抽出
7. Phase 4: 還流先提案（分割宣言の確認 → AGENTS.md/CLAUDE.md・hook・skill のどれに反映するか + 既存ガードレール未カバー理由）
8. Phase 5: レポート出力
9. Phase 6: 還流アクション確認（任意、AskUserQuestion）

> Phase 0.5 / 0.6 の journal append は **必ず承認制**。サルベージ grep の precision は約 35% で、自動 append は journal を汚す。
