# failure-journal

再発する失敗パターンを検出し、規約（AGENTS.md/CLAUDE.md）・hook・skill へ還流するための Claude Code プラグイン。

## 責務

このプラグインの責務は **「セッション振り返り」ではなく「再発する失敗パターンの検出と規約還流」** です。

1. AI が失敗するたびに `/log-failure` で JSON Lines (`journal.jsonl`) に append する
2. 一定期間後に `/retro` で集計し、閾値超え（直近 30 日 × 3 回以上）のパターンを抽出する
3. 抽出したパターンごとに「AGENTS.md/CLAUDE.md・hook・skill のどれに反映すべきか」と「既存ガードレールでカバーできていない理由」を提案する

判断軸を **「同じ状況で再発しうるか」の単一基準** に絞ることで、「これは記録すべきか」で迷わない設計にしています。

## `indie-workflow:retrospective` との違い

| | failure-journal | indie-workflow:retrospective |
|---|---|---|
| 責務 | 再発する失敗の **機械集計と規約還流** | **主観的なセッション振り返り**・見積もり精度分析 |
| データ | fingerprint (tag) ベースの JSON Lines | セッション単位の定性的な振り返り |
| 強制力 | 30 日 × 3 回で必ず還流提案が出る | 人の内省に依存 |

両者は責務が異なるため **並行 install 可能** です。個人開発者は retrospective のみ、チーム開発は両方、と install スコープを選べます。混ぜると壊れるため、本プラグインは独立して動作します。

## コマンド

| コマンド | 説明 |
|---|---|
| `/log-failure [現象]` | 再発しうる失敗を journal に append。tag を規約検証し、`failure:logged` event を publish |
| `/retro [日数]` | journal を集計し、閾値超えの再発パターンを抽出して還流提案を出力 |

## journal の保存と運用

- 保存先: `.claude/failure-journal/journal.jsonl`（SessionStart hook で自動初期化）
- 形式: JSON Lines、**append-only**（既存行の編集・削除は禁止）
- スキーマ:
  ```json
  {"timestamp":"2026-05-29T12:00:00Z","tag":"spec-skipped-without-rationale","phenomenon":"...","context":{}}
  ```

### gitignore 推奨

`.claude/failure-journal/journal.jsonl` は **`.gitignore` への追加を推奨** します。journal の中身を毎セッションで AI に読ませると fingerprint が AI の出力に汚染され、集計が不安定になるためです。commit せずローカルに留めてください。

`.gitignore` 例:

```
.claude/failure-journal/journal.jsonl
```

### journal は retro 実行中のみ Read

journal ディレクトリの中身を **参照してよいのは `/retro` 実行中のみ** という運用ルールを設けています。`/log-failure` は append が主目的で、journal 全体を読む必要はありません（表記揺れ防止のための既存 tag 参照は最小限）。常時 Read すると fingerprint が AI の出力に汚染されるため避けてください。

## tag 規約

`tag` は集計の fingerprint です。以下をすべて満たすこと:

- **kebab-case**（小文字 + ハイフン）
- **20 文字以内**
- **固有名詞禁止**（ファイル名・関数名・Issue ID・人名を含めない）
- **現象主体**（「何をしくじったか」を抽象化。例: `spec-skipped-without-rationale`）

規約違反を検出した場合、AI が修正案を提示して rewrite を要求します。

## Event Bus 連携

`/log-failure` は append 成功後、Event Bus 規約に従って `failure:logged` event を publish します（payload は tag のみ）。

```jsonl
{"ts":"2026-05-29T12:00:00Z","plugin":"failure-journal","event":"failure:logged","payload":{"tag":"spec-skipped-without-rationale"}}
```

これにより、plugin-feedback / linear-workflow などが subscribe して Issue 自動起票するエコシステムを組めます（subscriber は `event_bus_tail "failure:logged"` で読み出し、自前で dedup する）。

## 還流先の判断

`/retro` は CLAUDE.md の「ルール配置の意思決定（決定的 hook > LLM 判定）」に準拠して還流先を提案します:

- 決定的検証で判定可能（文字列・ファイル存在・diff・exit code） → **hook**（遵守率 100%）
- 文脈判断・自然言語理解が必要 → **skill / agent**
- 恒常的に参照したい規約・背景 → **AGENTS.md / CLAUDE.md**

実際の編集は本プラグインの責務外で、提案までを担います。

## 依存

- `jq`（event bus / 集計で使用。safe-hook.sh が前提とする ambient 依存）
- `bash` / `date`（macOS BSD / Linux GNU 両対応）
