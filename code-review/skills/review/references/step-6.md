<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/scoring-guide.md#報告閾値を割った指摘の記録 @b7079976 -->
<!-- SSOT: code-review/references/orchestration-measurement.md#16 @2a27f9ea -->
<!-- SSOT: code-review/references/orchestration-guide.md#2 @ac86f925 -->
<!-- SSOT: code-review/references/orchestration-guide.md#5 @88f608c4 -->
### 6. スコアリングとフィルタリング（2軸: confidence × severity）

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

1. **各指摘の base confidence と severity を取得**
   - reviewer 出力の `[confidence: XX]` と `[severity: BLOCKER|CRITICAL|MAJOR|MINOR]` をパース
   - severity が欠落している指摘は **CRITICAL とみなす**（後方互換 / 安全側デフォルト）
   - **この時点の severity 別件数を控える**（= `pre_adjust_counts`。統合・dedup 後、手順 2 以降の verdict 反映・加減算・降格・フィルタを**一切かける前**の生の分布）。締めフロー 4 の publish で使う。**手順 5 通過後の件数との差が「調整で消えた分」**であり、これが無いと「reviewer が検出しなかった」と「検出したが調整で消えた」を事後に区別できない（orchestration-measurement.md `## 16`）
   - **base 検算は `pre_adjust_counts` を控えた後に行う**（降格が「調整で消えた分」として会計されるため）。`退行` / 「変更前は X だった」を根拠にする指摘は `git show <base>:<path>` で base 側を検算する（orchestration-guide.md `## 5`「origin 主張の base 検算」。**冷や読み skeptic は reviewer 側の base 確認規約を継承しない**ため、この層の主張が主対象。反証レイヤーは effort ≥ high でしか走らないので、この検算だけが effort 非依存 / #124 (d)）
2. **反証 verdict の反映**（Phase 5.9 が動いた場合のみ。scoring-guide.md `## 反証レイヤーの verdict 反映` に従う）
   - **BLOCKER / CRITICAL の `refuted` は confidence / severity を据え置き**、指摘本文先頭に `⚠️ 反証メモ: <軸>（<根拠 file:line>、要確認）` を付与（**報告から消さない**）
   - **MAJOR / MINOR の `refuted`** は confidence −40（取り下げ理由を付録に記録）
   - `confirmed` は既存「複数エージェント +15」の発火源（二重計上しない）、`uncertain` は −10
   - verdict が無い指摘（対象外・反証失敗）は no-op
3. **confidence への加算・減算ルールを適用**
   - PR コンテキストタグ（`[re-flag: ...]` / `[resolved: ...]` / `[intent-conflict]` / `[scope:out]`）の加減算
   - 複数エージェント検出 / explorer 裏付け / セッションコンテキスト等の加減算
   - 最終 confidence を 0-100 にクランプ
4. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（反証 `severity-inflated` もこのルールに統合。二重降格しない）。**BLOCKER / CRITICAL の `severity-inflated` は降格後に報告マトリクスを割る場合のみ据え置き + 反証メモ**（scoring-guide の不変条件。高 severity を silent に消さない）。**MAJOR / MINOR が `severity-inflated` の降格で報告閾値を割って脱落する場合は、`refuted` の −40 脱落と同じく 🔁 付録に取り下げ理由を記録する**（scoring-guide.md `## 反証レイヤーの verdict 反映` / issue #109。降格で消える指摘が silent に落ちない）
4.5. **加減算で報告閾値を割った指摘を控える**（issue #128）: 手順 3〜4 の減算・クランプ・降格の結果、手順 5 の報告マトリクスを通過しなくなる指摘は、**severity を問わず** 🔁 付録に「調整前の (severity, confidence) / 適用した規則名 / 遷移後の値」を記録する。反証由来の脱落（手順 2）と同じ枠に、経路が分かる形で並べる。**加減算を受けずに reviewer の付けた値のまま閾値を割っている指摘（③）も同じ枠に記録する**。正本: scoring-guide.md `## 報告閾値を割った指摘の記録`
5. **報告マトリクスでフィルタ**:

   | severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
   |---|:---:|:---:|:---:|:---:|
   | BLOCKER | skip | 報告 | 報告 | 報告 |
   | CRITICAL | skip | skip | 報告 | 報告 |
   | MAJOR | skip | skip | skip | 報告 |
   | MINOR | skip | skip | skip | 報告 |

   **実効報告閾値が `MINOR` の回は MINOR 行を 80+ で通す**（手順 6 の実効値。scoring-guide.md `### 実効報告閾値が MINOR の回` / GitHub issue #295）。95+ のままだと、閾値を下げて reviewer に本文を書かせた MINOR が付録に落ちる

6. **userConfig 適用**: `review_severity_threshold` (default: `MAJOR`) の**実効値**より低い severity は除外（doc だけの diff = `## size` の `doc_only=1` では既定の `MAJOR` を `MINOR` に下げる / orchestration-guide.md `## 2` / #275）。**`pre_adjust_counts` には各 reviewer の `## below-threshold` の件数を同名 severity のバケツへ足し、`severity_threshold` を併せて記録する**（足し込む分は dedup されないため版で非可換。版マーカー `schema` は**スクリプトが注入する**ので書かない。orchestration-measurement.md `## 16`）。**足し込んだその件数を `below_threshold_counts` にも同じバケツで再掲し、`## below-threshold` の `demoted-across-threshold:` 行の型名を `below_threshold_counts.demoted_types` に型別で数える**（**親オブジェクトの中に置く** — トップレベルに書くと集計されない / GitHub issue #208）（どちらも 0 件でもキーを省かない / GitHub issue #146・#150）。合算しか残らないと **(a) 本文を書いてから捨てた**（出力トークンの純損失）と **(b) 件数だけ返した**（既に節約できている）が分離できず、閾値注入の効果を判定できない。**`pre_adjust_counts` を超える値は publish が fail-fast する**。**`below_threshold_counts` に入れるのは reviewer の `## below-threshold` 件数行の数字だけ**。`#### 指摘事項` に列挙された指摘は、反証・加減算・報告マトリクス（手順 2〜5）で閾値を割っても足さない — それらは 🔁 付録の側に載る指摘で、`pre_adjust − below` の「本文を書いた」に入る。足すと付録の上限が縮み、正規の付録行で `payload:appendix.exceeds-body` が偽陽性になる（実測 1 回 / GitHub issue #248）。**`## below-threshold` の件数行の後に reviewer が本文を書いていても、その指摘は below に数えるだけで本文にも 🔁 付録にも載せない**（付録の対象は閾値以上で列挙された指摘だけ ＝ 契約 (a)。載せると本文を書いた数の上限を超え、publish が `payload:appendix.exceeds-body` を立てる / GitHub issue #248）。**🔁 付録の件数は `appendix` に載せる**（`{listed, recommended}`。`listed` は付録に並べた行数、`recommended` はそのうち `※ 推奨:` を付けた行数。0 件でもキーを省かない / GitHub issue #168）— **付録に列挙しただけでは「報告 0 件の回」と「価値 0 の回」が payload 上で同じ形になる**（実測: severity 4 バケツすべて 0 なのに付録 18 件・うち 4 件を人間に推していた回がある）。`recommended` が `listed` を超えると publish が fail-fast する。マーカーの規約は scoring-guide.md `## 報告閾値を割った指摘の記録` の「推奨マーカー」。**`adversarial_verify.inflated_axes` は反証 agent の `axis` を同じ 4 型へ寄せて数える**（`pre-existing` / `intended` → `base_derived` / `misread` → `misread` / `overstated-impact` → `overstated_impact` / `miscategorized` → `miscategorized`。**`unknown` は「軸が返らなかった・語彙外だった」件だけ**で、`unreachable` / `pre-validated` / `none` は`severity-inflated` の軸ではないのでここに落ちる）。**語彙内の値を寄せ忘れても合計の突合は通る**ので、`unknown` が 1 件以上あると `measurement_gaps` に `axis-unknown` / `demoted-unknown` が立つ / GitHub issue #167
7. **出力**: タグ（`[re-flag: @user]` 等）と severity ラベルを指摘文冒頭にそのまま残す。`⚠️ 反証メモ:` が付いた係争指摘は本文にメモを残したまま出力する

**次は Step 7**（SKILL.md に戻り、その見出しを見る）
