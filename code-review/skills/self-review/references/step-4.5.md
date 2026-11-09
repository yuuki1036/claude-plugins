### 4.5 Adaptive deepening: Round 2（unmet_information 起点 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 4.8 の skeptic 統合へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない
- **unmet の target が全件「到達不能」**（DB / 本番の実データ、このリポジトリに存在しないコード、意図的にスキップした lint / テスト実走など）で、追加探索が構造的に空振りする場合。分類表と「1 件でも到達可能なら起動する」根拠は triage-dynamic-gates.md `## 8`（GitHub issue #100 C）。スキップ時は `missing_coverage` に識別子 `round2` を記録し（**理由はレポート本文へ**）、レポートの「動的ラウンド」行にも出す。**⚠️ 「repo 外」≠「到達不能」（v2.60.0）** — 外部サービスの実挙動でも**その MCP / CLI がセッションで使えるなら到達可能**で、Round 2 の前に**メインで直接照会して解決してよい**（read-only）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 6` の手順に従う（unmet_information 集約 → **high は 1 段圧縮**: 追加 explorer なしで該当 reviewer 最大 3 体を再起動し unmet ターゲットを自力探索させる / **xhigh・max は 2 段**: 追加 explorer 最大 3 体 → 該当 reviewer 再起動 → 初回出力を置換。失敗時は初回結果のまま続行の best-effort）。**回収した直後に `mark wave` を記録する**（Step 4 と同じ呼び出し。後勝ち。**追加 explorer を起動した場合も `--explorer` は付けない** — `agents.explorer_waves` は「初回 explorer の一括発行が守られたか」の指標で、Round 2 の追加 explorer を混ぜると規約どおりの起動が「一括発行違反」として誤検知される）。レポートに「Round 2 trigger: <reason>」を記録（Step 6 で出力）。

**次は Step 4.8**（SKILL.md に戻り、その見出しを見る）
