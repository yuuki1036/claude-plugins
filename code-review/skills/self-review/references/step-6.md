<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/scoring-guide.md#報告閾値を割った指摘の記録 @ebcc7da2 -->
### 6. レポート出力

**他 skill からオーケストレーションされても定型と publish は省かない**（GitHub issue #232）: feature-dev 等の親 skill が self-review を呼び、手順を親のコンテキストで回す場合でも、**下のテンプレートどおりのレポート → `mark t2` → 6.4 の publish** は self-review の手順として踏む（`--embed` の有無を問わない）。親の集約・要約はこの定型レポートを**出した後に**足すもので、置き換えない。publish を踏まずに Edit / Write / Skill / Agent を呼ぶと publish-guard hook（PreToolUse）が鳴る。

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。**理由・補足はこのセクション本文に書き、payload の `missing_coverage` 配列には識別子のみを入れる**（語彙は orchestration-measurement.md `## 16`。自由文を入れると綴りが割れて集計不能になる）。

**冷や読み skeptic の観測可能性（issue #85）**: high-risk surface を含む変更では、冷や読み skeptic（Phase 4.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 4.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと **Step 6.4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-dynamic-rounds.md `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## セルフレビュー結果

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従う。コミット前ゲートとして「このままコミットしてよいか」の指針）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**範囲**: {`--since` を渡した回だけ: `delta（N ファイル・M 行 / 起点 <tree の先頭 8 桁>）` | `diff 全体（<縮退の理由>）`。渡していない回はこの行を省く}（GitHub issue #313。理由は `fallback=` の値を `--staged と併用` / `起点が tree の ID でない` / `起点の tree を引けない` / `--prior-findings を読めない` / `delta を取れない` / `PR のレビュー` と書く。呼び出し元はこの行の有無で code-review が `--since` を知る版かを見分ける）
**実効上限**: explorer N / reviewer N / specialist N（Step 2.2 の plan の `explorer_cap` / `reviewer_cap` / `specialist_cap` を写す。効いた側は `cap_source` で、`effort` = **実行時** effort `{値}` の上限 / `size` = 規模キャップ `{帯}`（core N files / N lines）/ `scope` = `--focus` / `--exclude`）
  ※ reviewer の effort と動的ラウンド（meta / skeptic / 反証ゲート）は**実行時 effort に連動**する。skill frontmatter の effort はオーケストレーター用で別枠
**動的ラウンド**: Round 2 {未実行 | スキップ（unmet 全件が到達不能）| スキップ（unmet をメインで直接照会して解決）| 実行（再起動 reviewer N 体 / 追加 explorer M 体）} / Meta-reviewer {実行（N 件追加）| スキップ理由（`effort` / `config` / `no-high-severity` / `size-tier`）} / 冷や読み skeptic {実行（N 件追加）| skip（理由: effort/config/scope）| 非該当（surface なし）**← payload の `recall_skeptic.skip_reason` は `"no-surface"`。`fired=false` なので `null` にしない**} / 反証 {対象 N 件（うち meta 由来の追加バッチ M 件）| スキップ理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件
**前回の指摘への修正**: {Step 1 で `## prior-fixes` が出た回: `N 箇所を確認対象に戻した（観点: <キー>, …）` | 出なかった回はこの行を省く}（GitHub issue #298。絞り込んだ回でも、前回の指摘で入れた修正を見たかが読み手に見えるように）
**仕様整合**: {spec-compliance を起動した回: `<仕様ソース>`（Issue / session-context / knowledge / `--spec` / repo の仕様書 N 件（diff が触った M 件））と照合し、仕様違反 N 件（うち文書への未反映 K 件） | 起動しなかった回: Step 2.2 の plan から写す — `spec_source	none` なら `仕様ソースなし`、`dropped	spec-compliance	size-cap` なら `規模キャップで未起動`、`effort-cap` なら `effort 上限で未起動`、`excluded	spec-compliance` か `--focus` に無い回は `--focus / --exclude で対象外`}（spec-compliance の結論を 1 行で。起動の有無が読み手に見えないと、指摘 0 件が「仕様どおり」と読まれる）
**反証**: 対象 N 件 / 係争 M 件（BLOCKER/CRITICAL、本文に反証メモ）/ 取り下げ K 件（MAJOR以下、付録に理由）{**スキップ時もこの行を出す**（書式の正本は orchestration-dynamic-rounds.md `## 10` 手順 4）。`no-eligible-findings` は `未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）` と書く — 「対象 0 件」は「検証したが問題なし」と読まれる}

### 🚨 BLOCKER 指摘

1. [confidence: 70][severity: BLOCKER][セキュリティ] Hardcoded secret の疑い
   ファイル: src/config.ts:15
   影響: コミット時にシークレット漏洩

### ⚠️ CRITICAL 指摘

2. [confidence: 95][severity: CRITICAL][バグ] Missing null check
   ファイル: src/utils.ts:42
   影響: 特定入力で関数が落ちる

3. [confidence: 85][severity: CRITICAL][recall-skeptic][バグ] 空文字の draft が numeric 列へ素通りする
   ファイル: src/repo.ts:88
   影響: 22P02 で INSERT が落ちる
   {由来タグ: skeptic 単独由来は `[recall-skeptic]` / reviewer と重複した survivor は `[recall-skeptic:dup]`。Step 6.4 の publish で `findings_added` / `findings_overlap` を数える唯一の根拠なので落とさない。番号は他の指摘と通し連番にする}

### 📋 MAJOR 指摘

4. [confidence: 95][severity: MAJOR][設計] ...

### ✏️ コメント推敲（severity 対象外・Step 7 の適用確認で「適用する」を選ぶと comment-polish が適用する）
{`comment-accuracy` が構成に入っていれば（**バンドル相乗りを含む**）必ず見出しを出す（0 件なら「該当なし」。省略すると silent skip と区別できない）。構成に無ければ見出しごと省略し、**diff にコメントの追加・変更があるのに未起動だった場合のみ** `comment-accuracy` を欠損観点に記録する（トリガ不成立の未起動は正常系。記録すると `missing_coverage` の偏り集計が潰れる）。掲載上限 10 件、超過分は末尾に「他 N 件」}

1. src/foo.ts:12 [不要]
   before: `// カウンタをインクリメント`
   after: (削除)
   理由: `count++` が自明でコードの同語反復
{タグは 2 種: `[不要]`=読み手に必要な情報を含まない / `[冗長]`=情報は必要だが表現が冗長。以降も同形式}

### 📝 Markdown 推敲（severity 対象外・Step 7 で「適用する」を選ぶとメインが Edit で適用する）
{見出しを出す・省く規則と 1 件の書式の正本は `md-polish-guide.md` の 4 節。起動した回は 0 件でも「該当なし」を出す。`no-md-prose` の回は見出しごと省く}

{決定系 doc の design-review 委譲を起動した回は、「🧭 決定の品質」の節を Step 6.4 の publish の後に足す（この位置には書かない。書式の正本は `design-review-guide.md` の 4 節）}

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 🔎 閾値未満の候補
{**報告が 4 バケツすべて 0 件 かつ `below_threshold_counts` の合計が 1 件以上の回だけ出す**（それ以外は見出しごと省略）。件数だけ返った閾値未満は 🔁 付録に載らないので、この 1 行が無いと「何も見つからなかった回」と区別がつかない → scoring-guide.md `### 閾値未満の件数通知`}
- 報告閾値 {実効 `review_severity_threshold`} 未満の候補が N 件あります（CRITICAL a / MAJOR b / MINOR c。本文は reviewer が書いていないため省略）。見る場合は `review_severity_threshold` を下げて再実行してください

### 🔁 報告閾値を割った指摘（参考・人間が覆せる）
{reviewer が `#### 指摘事項` に列挙した指摘が報告マトリクスを通過しなかった場合に載る（総括・related-observations の記述からは起こさない）。**経路（反証 verdict / 加減算 / 最初から閾値未満）を問わず記録し、severity 別の扱いは正本に従う** → scoring-guide.md `## 報告閾値を割った指摘の記録`。0 件なら省略}
- [調整前: confidence XX / severity MAJOR] xxx の指摘
  ファイル: path/to/file:行番号
  脱落理由: <verdict: refuted | severity-inflated> — <軸>（反証根拠 file:line）／ <加減算: 規則名> — confidence XX → YY ／ <調整なし: reviewer の値のまま閾値未満>
  ※ 判断が誤りと思えばこの指摘は有効。再評価してよい
  ※ 推奨: <見送るのが惜しい理由。修正コストが小さい項目にだけ付ける。閾値を割った理由は上の欄にあるので繰り返さない>

### 総括
- 変更の概要
- コミット前に修正すべき項目（特に BLOCKER）
- 確認推奨の観点
```

**レポートを出力した直後に fleet 区間の終了マーカーを記録する**（Step 7 の修正方針確認＝人間の応答待ちを混ぜないため。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t2
```

> **「レポート出力 → `mark t2` → 6.4 の publish」は不可分の締めで、Step 6 はここまで**（GitHub issue #133）。番号は分かれているが 6.4 は独立した任意ステップではない。**publish を踏む前に Step 7（修正方針確認・修正作業）へ進まないこと** — publish は副作用のみで標準出力に何も足さないため、**脱落しても実行中は誰も気づかない**（実測: MAJOR 4 件を報告して全件修正した回が丸ごと欠測になり、meta 起動サンプルを 1 件失った）。ユーザーが事前に「指摘は全部修正して」と伝えている回ほど落ちやすい。

**次は Step 6.4**（SKILL.md に戻り、その見出しを見る）
