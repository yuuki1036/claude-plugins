### 4.9 反証レイヤー（adversarial verification / 動的・**meta-reviewer(4.6) と同一 wave**）

冷や読み skeptic の統合後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-dynamic-gates.md` `## 9 反証レイヤー`）。meta-reviewer (4.6) / skeptic (4.8) が見落とし（false negative）を足す係なのに対し、本フェーズは独立読み直しで **severity を較正し偽陽性を摘出する**鏡像（実測は較正が主機能: `severity_inflated` 60% / `refuted` 6%。#114）。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップし、同一 wave の 4.6 だけを発行する）。**発火は起動有無にかかわらず payload（`fired` + 括弧内の `skip_reason`。起動時は `null`）と Step 6 レポートに記録する。4 つ目を他と同じ値に潰さないこと** — 既定 high では BLOCKER / CRITICAL が 0 件なら対象が構造的に 0 件になるため、潰すと「ゲートが狭いのか対象が無かったのか」を事後に切り分けられない（→ triage-dynamic-gates.md `## 9` / issue #129）:
- userConfig `enable_adversarial_verify` が `false`（`"config"`）
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`（`"effort"`）
- `--focus` / `--exclude` でスコープを絞り込んでいる（既検証の再評価を避ける）（`"scope"`）。**`--since` だけでは当たらない** — delta の回も通常のゲートを範囲で絞らず全指摘に当てる（G-V ループが auto-fix に入れうる指摘を水増しのまま通さない / #313）
- 反証対象（triage-dynamic-gates.md `## 9` のゲート）に合致する指摘が 0 件（**`"no-eligible-findings"`**）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 10` の手順に従う（triage-dynamic-gates.md `## 9` の選定ルールで対象を選び、**5 件ずつのバッチ**に分けて反証エージェントを `model: opus`, `effort: high` で並列起動（上限 3 体）。**この一括発行に Step 4.6 の meta-reviewer を含める**（同一 wave）。**reviewer の理由文は渡さない**＝アンカリング防止 → verdict を finding_id で突合して Step 5 のスコアリングに渡す。失敗した指摘は verdict なしのまま続行の best-effort）。**回収した直後に `mark wave` を記録する**（Step 4 と同じ呼び出し。後勝ち。既定 effort ではこのフェーズが最後の agent wave になるため、ここを落とすと `duration_synthesis_min` が反証 wave を丸ごと含む）。レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 6 で出力）。 **meta 由来指摘の追加バッチ**（`[meta]` タグ付きが反証ゲートに該当する場合のみ 1 体・上限 5 件を直列起動。0 件なら wave は増えない。`## 10` 手順 3.5）を起動したときは、回収直後に再度 `mark wave` を記録する。

**次は Step 4.7**（SKILL.md に戻り、その見出しを見る）
