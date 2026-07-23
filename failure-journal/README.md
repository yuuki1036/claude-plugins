# failure-journal

再発する失敗パターンを検出し、規約（AGENTS.md/CLAUDE.md）・hook・skill へ還流するための Claude Code プラグイン。

## 責務

このプラグインの責務は **「セッション振り返り」ではなく「再発する失敗パターンの検出と規約還流」** です。

1. **セッション中**: SessionStart hook が注入する自己申告ルールにより、Claude が自己訂正した瞬間に `candidates.jsonl` へ候補を 1 行 append する（人間の操作不要）。人間が気づいた失敗は従来どおり `/log-failure` で journal に直接 append する
2. 一定期間後に `/retro` で candidates を**承認レビューして journal に昇格**し、閾値超え（直近 30 日 × 3 回以上）のパターンを抽出する
3. 抽出したパターンごとに「AGENTS.md/CLAUDE.md・hook・skill のどれに反映すべきか」と「既存ガードレールでカバーできていない理由」を提案する

candidates 方式を採る理由: 失敗の大半は Claude の自己訂正で人間の目に触れず、手動起票では拾えないためです（実測の起票率 ≒2.5%）。「retro 時に過去の transcript を掘る」のではなく、**検知できる唯一の主体（Claude 自身）に検知した瞬間書かせる**ことで、transcript の 30 日消滅・grep precision 35%・却下候補の再浮上という旧サルベージ設計の制約を回避します。transcript サルベージは候補が無い期間のフォールバック（Phase 0.6）として残ります。

> 開発環境での実測では、記録に値する失敗が約 40 件発生した期間に journal 起票は 1 件でした。ただしこれは単一環境（1 ユーザー・日本語セッション主体）の値で、対象 9 プロジェクトのうち 8 は log-failure を未運用だったため、「導線の弱さ」と「未運用」が合算されています。測定条件は `skills/retro/references/transcript-salvage.md` を参照してください。

判断軸を **「同じ状況で再発しうるか」の単一基準** に絞ることで、「これは記録すべきか」で迷わない設計にしています。

## `issue-workflow:retrospective` との違い

| | failure-journal | issue-workflow:retrospective |
|---|---|---|
| 責務 | 再発する失敗の **機械集計と規約還流** | **主観的なセッション振り返り**・見積もり精度分析 |
| データ | fingerprint (tag) ベースの JSON Lines | セッション単位の定性的な振り返り |
| 強制力 | 30 日 × 3 回で必ず還流提案が出る | 人の内省に依存 |

両者は責務が異なるため **並行 install 可能** です。個人開発者は retrospective のみ、チーム開発は両方、と install スコープを選べます。本プラグインは他プラグインに依存せず独立して動作します。

## コマンド

| コマンド | 説明 |
|---|---|
| `/log-failure [現象]` | 再発しうる失敗を journal に append。tag を規約検証し、`failure:logged` event を publish |
| `/retro [日数] [--salvage] [--no-salvage]` | candidates を承認レビューして journal に昇格し、集計・閾値超え抽出・還流提案を出力。候補 0 件なら transcript サルベージにフォールバック（`--salvage` で強制実行、`--no-salvage` で禁止） |

## journal の保存と運用

- 保存先: `.claude/failure-journal/journal.jsonl`（SessionStart hook で自動初期化）
- 形式: JSON Lines、**append-only**（既存行の編集・削除は禁止）
- スキーマ:
  ```json
  {"timestamp":"2026-05-29T12:00:00Z","tag":"spec-skipped-without-rationale","phenomenon":"...","context":{}}
  ```

### gitignore 推奨

`.claude/failure-journal/` は **ディレクトリごと `.gitignore` への追加を推奨** します。journal / candidates の中身を毎セッションで AI に読ませると fingerprint が AI の出力に汚染され、集計が不安定になるためです。commit せずローカルに留めてください。

`.gitignore` 例:

```
.claude/failure-journal/
```

### journal / candidates は retro 実行中のみ Read

journal ディレクトリの中身を **参照してよいのは `/retro` 実行中のみ** という運用ルールを設けています。`/log-failure` は append が主目的で、journal 全体を読む必要はありません（表記揺れ防止のための既存 tag 参照は最小限）。candidates.jsonl も同様に **append はいつでも・Read は retro 中のみ** です。常時 Read すると fingerprint が AI の出力に汚染されるため避けてください。

### 既知の制約

- **sidechain 盲点**: subagent は SessionStart ルールを受けないため候補を書きません。多段 agent スキル内の失敗は、オーケストレーターが訂正した時点での候補化に期待する設計です
- **マルチマシン**: candidates / journal はマシンローカルです。プロジェクトを複数マシンで開発する場合、retro は実行マシンの分しか見えません（transcript 依存だった旧設計よりは、ファイルを commit する選択肢が生まれた分だけ改善）

## tag 規約

`tag` は集計の fingerprint です。以下をすべて満たすこと:

- **kebab-case**（小文字 + ハイフン）
- **30 文字以内**
- **固有名詞禁止**（ファイル名・関数名・Issue ID・人名を含めない）
- **現象主体**（「何をしくじったか」を抽象化。例: `spec-skipped-without-rationale`）

規約違反を検出した場合、AI が修正案を提示して rewrite を要求します。

## Event Bus 連携

`/log-failure` は append 成功後、Event Bus 規約に従って `failure:logged` event を publish します（payload は tag のみ）。

```jsonl
{"ts":"2026-05-29T12:00:00Z","plugin":"failure-journal","event":"failure:logged","payload":{"tag":"spec-skipped-without-rationale"}}
```

これにより、plugin-feedback / issue-workflow などが subscribe して Issue 自動起票するエコシステムを組めます（subscriber は `event_bus_tail "failure:logged"` で読み出し、自前で dedup する）。

## 還流先の判断

`/retro` は CLAUDE.md の「ルール配置の意思決定（決定的 hook > LLM 判定）」に準拠して還流先を提案します:

- 決定的検証で判定可能（文字列・ファイル存在・diff・exit code） → **hook**（遵守率 100%）
- 文脈判断・自然言語理解が必要 → **skill / agent**
- 恒常的に参照したい規約・背景 → **AGENTS.md / CLAUDE.md**

実際の編集は本プラグインの責務外で、提案までを担います。

## 依存

- `jq`（event bus / 集計で使用。safe-hook.sh が前提とする ambient 依存）
- `bash` / `date`（macOS BSD / Linux GNU 両対応）
