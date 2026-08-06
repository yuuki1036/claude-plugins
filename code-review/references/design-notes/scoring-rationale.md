# スコアリング設計の根拠（実行時には読まない）

`scoring-guide.md` から切り出した「なぜそうなっているか」と将来拡張。**Step 6 のスコアリング実行中に読む必要はない** — 規範はガイド本体にあり、ここにあるのは規範を変えるときに必要な背景。


## なぜ 2 軸か（単一軸のジレンマ）

この 2 軸を混同すると次のジレンマが起きる:

| ケース | 単一軸 (confidence のみ) の問題 |
|---|---|
| **重大だが不確実** (race condition の疑い) | confidence 中程度 → 80 未満で**落ちる**。致命的見落とし |
| **軽微だが確実** (typo) | confidence 高い → 報告される。ノイズ |

2 軸化により **「BLOCKER は不確実でも報告」「MINOR はほぼ確実な時だけ報告」** という非対称な報告ルールを表現できる。


## `severity-inflated` の穴（v2.41.0 で塞いだ）

- **`severity-inflated` の穴（v2.41.0 で塞いだ）**: 旧規約は `severity-inflated` を「全 severity で 1 段階下げる」としていたため、**BLOCKER 60-79 → CRITICAL 60-79（要 80）/ CRITICAL 80-94 → MAJOR 80-94（要 95）** が報告マトリクスを割って silent に消えていた。`refuted` 経路しか塞いでいない不変条件は、反証レイヤーの effort を下げる根拠には使えない（orchestration-guide.md `## 5` の「扱い側で保険が効いている」はこの修正込みで成立する）


## パネル運用時の集計（将来拡張）

### パネル運用時の集計（max effort で 1 指摘を複数体反証する場合・将来拡張）

- `refuted` 成立は **過半数かつ全員が file:line 反証根拠を提示** した時のみ。票割れ・棄権（uncertain 混在）は uncertain 扱いとし delta を合算しない
- 現行は全 effort で **1 指摘 1 verdict**（v2.41.0 以降、反証エージェント 1 体が最大 5 件を担当するバッチ運用。1 件を複数体で見るパネルではない）。パネルは event bus 計測後に拡張判断
- **バッチはパネルではない**: 同じ指摘に複数 verdict が付くことは無いので、上の過半数ルールは現行では発火しない。バッチ内の verdict 同士を合算・相殺してはならない（triage-dynamic-gates.md `## 9`）


## 判断待ちの観測: review 経路の MAJOR がゼロに張り付いている

**scoring 規約を変える前に `design-notes/triage-rationale.md` の「未解決の観測」を読むこと。** 特に「MAJOR/MINOR の `severity-inflated` を無条件降格から保護する」（高 severity の不変条件を MAJOR へ拡張する）は precision を直接下げる不可逆な変更であり、**降格由来だと確認できていない段階で入れてはならない**。
