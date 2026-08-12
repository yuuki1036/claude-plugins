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

## 反証 verdict の実測分布と、上流ガードを入れた根拠（v2.55.0 / GitHub issue #114）

全期間の集計（`adversarial_verify.severity_inflated` を持つ **19 サンプル / 計 67 verdict**）:

| verdict | 件数 | 比率 |
|---|---:|---:|
| confirmed | 23 | 34% |
| **severity_inflated** | **40** | **60%** |
| refuted | 4 | 6% |
| uncertain | 0 | 0% |

**反証レイヤーの実際の主機能は severity の較正であって偽陽性の除去ではない**（`refuted` は 6%）。層の価値を否定するデータではない — 実測 1 件では 9 件中 6 件を降格して報告を 1 件に絞れている。**記述と実挙動がずれていた**ので `triage-dynamic-gates.md ## 9` / `prompts/adversarial-verify.md` / 両 SKILL の位置づけを書き換えた。

**上流ガード（`prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」）を入れた根拠は n=1 のデータである。** review 1 件の `severity_inflated` 6 件の軸別内訳（pre-existing 1 / intended 2 / misread 1 / 影響が過大 2）から「半分は base を先に見れば避けられた」と読んだ。

- **軸別の内訳は payload に無く、レポート本文から手で数えた値**。集計値（n=19）と内訳（n=1）の信頼度は別物として扱うこと
- そのため**入れたのは prompt の手順追加という可逆な変更だけ**にした。`severity-inflated` の降格規則そのもの（不可逆側）は触っていない。この非対称は意図的で、上の「判断待ちの観測」と同じ流儀
- **効果の確認は `pre_adjust_counts` と `adversarial_verify.severity_inflated` の比率で行う**。ガードが効けば reviewer 側で降格済みの指摘が増え、反証の `severity_inflated` 比率が下がるはず。下がらなければ「reviewer は base を見ていない」か「過大評価の主因が base 以外（misread / 影響の見積もり）」のどちらかで、打ち手が変わる
