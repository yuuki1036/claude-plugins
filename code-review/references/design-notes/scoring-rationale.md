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

### v2.41.0 の縮小（バッチ化 + effort 引き下げ）は維持で確定した（GitHub issue #119）

同じ 19 サンプルが `triage-dynamic-gates.md ## 9` のロールバック条件の判定材料でもあった。**`uncertain` 0% / `refuted` 6%** で、どちらの戻し条件（uncertain 増 → effort を `max` に戻す / refuted 増 → バッチ 5 → 3）にも該当しない。**`effort: high` とバッチサイズ 5 を維持**する判定を `## 9` に記録し、「サンプルが貯まるまでは判断しない」の保留状態を解消した。

- `uncertain` が 0 なのは判定を避けているのではなく**判定できている**と読む（`adversarial-verify.md` は根拠を出せない場合に `uncertain` を選ぶよう指示しており、実測 1 件では 9 件すべてに `file:line` 付き根拠が返っていた。1 件は実ブラウザでの再現まで実施）
- **`orchestration-guide.md ## 5` の注記は閉じていない** — 「不変条件（高 severity 非削除）を緩めるときは反証 effort を `max` に戻すか同時に判断する」は verdict 分布とは独立の条件なので、本判定に巻き込まない

**上流ガード（`prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」）を入れた根拠は n=1 のデータである。** review 1 件の `severity_inflated` 6 件の軸別内訳（pre-existing 1 / intended 2 / misread 1 / 影響が過大 2）から「半分は base を先に見れば避けられた」と読んだ。

- **軸別の内訳は payload に無く、レポート本文から手で数えた値**。集計値（n=19）と内訳（n=1）の信頼度は別物として扱うこと
- そのため**入れたのは prompt の手順追加という可逆な変更だけ**にした。`severity-inflated` の降格規則そのもの（不可逆側）は触っていない。この非対称は意図的で、上の「判断待ちの観測」と同じ流儀
- **効果の確認は `pre_adjust_counts` と `adversarial_verify.severity_inflated` の比率で行う**。ガードが効けば reviewer 側で降格済みの指摘が増え、反証の `severity_inflated` 比率が下がるはず。下がらなければ「reviewer は base を見ていない」か「過大評価の主因が base 以外（misread / 影響の見積もり）」のどちらかで、打ち手が変わる

## `## below-threshold` は CLAUDE.md「Opus 5 足場③」に反する方向である（v2.58.0 / #117 のセルフレビュー指摘）

ルート CLAUDE.md は「**重要な指摘だけ報告せよ**（recall 低下。全報告→下流フィルタに）」を Opus 5 世代で逆効果になる足場として禁じている。#117 の実装は**下流にあったフィルタを reviewer 側の「書くか書かないか」へ上流移動**させるもので、この規約と逆を向く。**認識した上で、実測（MINOR が調整前 60 → 報告 9 の 85% 破棄・うち confidence 95+ が 7 件）を理由に採った。**

規約が想定する劣化を抑えるため、上流移動を**列挙だけ**に限定してある（判定は従来どおり / 繰り上げ禁止 / 0 件でも申告 / 未注入時は抑制しない）。ただし**散文の但し書きで抑えきれないという前提でこの規約は書かれている**ので、以下は既知のリスクとして残る。

**効果測定の盲点（重要）**: `pre_adjust_counts` に `## below-threshold` を足しても回収できるのは「**判定された** MINOR の件数」だけで、閾値を知った reviewer が**そもそも探索・形成しなくなった** MINOR は数に現れない。**この施策で最も起きやすい劣化が、施策の効果測定の盲点に入っている。** `pre_adjust_counts.minor` が減っても「PR の質が上がった」と読んではならない。

**切り分ける唯一の方法**: `review_severity_threshold = "MINOR"`（抑制なし）の対照サンプルを同規模 PR で数件取り、`pre_adjust_counts.minor`（schema 2 同士）を比較する。抑制ありの群で有意に少なければ、形成段階の recall が落ちている。

**撤去条件**: 上の対照比較で形成段階の劣化が確認されたら、#117 は撤去して下流フィルタに戻す（削減効果より recall を優先する。CLAUDE.md の規約が本則）。
