<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-measurement.md#16 @2a27f9ea -->
### 6.4. Event Bus publish（`review:completed` / 計測用）

**このステップの直前に `${CLAUDE_PLUGIN_ROOT}/references/orchestration-measurement.md` を Read する**（publish 先の固定・`TS_FILE` のパス導出・区間の算出式・payload 契約の正本。レビュー本体の実行には不要なのでここまで読まない）。

レポート出力後、集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**embed / 非 embed の両モードで実行する**（LLM 駆動 fan-out の「観点取りこぼし」「severity/confidence のパース安定性」を後から定量化するための計測データを蓄積する目的。review skill と同じ `review:completed` イベントで集計を揃える）。副作用のみで標準出力にレポート文字を足さないため embed mode の出力フォーマット（Step 6.5 の JSON ブロック → marker の順序）には影響しない。self-review は PR を持たないため `pr` は `"local"` 固定とする。

**publish は専用スクリプトで行う**（書込先の固定・所要時間の算出・一時ファイルの掃除をまとめて担当する）。`duration_*` と **`agents.explorer_waves`** は**渡さない** — スクリプトが計測ファイル（explorer wave の打点）から算出して注入する。self-review では `duration_closing_min` を `-1`（測定不能）に固定する:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh" \
  --plugin code-review:self-review --payload '<orchestration-measurement.md `## 16` の self-review 用テンプレートを実値で埋めたもの。effort は '"${CLAUDE_EFFORT}"' の実値>'
```

- スクリプトは payload の JSON 妥当性と **`missing_coverage` / 動的層の `skip_reason` の語彙**を検証してから書く（不正なら publish せず `FATAL:` で落ちる。識別子以外＝理由つき自由文は弾かれるので、**理由はレポートの「⚠️ 欠損観点」に書き、フィールドごと落として通さない** / issue #132）。**`skip_reason` の許容値は orchestration-measurement.md `## 16` の各層の節が正本**で、層をまたいだ流用も弾かれる（`fired=false` で理由を書き忘れた回だけは落とさず `measurement_gaps` に倒す）。**`measurement_gaps` / `derived_markers` / `diff_digest` / `models` / `review_scope` も渡さない**（`review_scope` は triage-signals.sh が size ファイルに書いた範囲から作る / #313）（`models` は**モデル世代**で、transcript の `message.model` からの機械計測。渡しても捨てられる / issue #169）（計測ファイル・agent transcript・一時 diff から算出して注入される。`derived_markers` は**打点が落ちた区間を agent の実測時刻で埋めた記録**で、`measurement_gaps` とは排他ではない / issue #161）。計測ファイルと diff の一時ファイルもスクリプトが掃除する
- **版マーカーの整数も渡さない**（`schema` / `gate_schema` / `attribution_schema` / `calibration_schema`。v2.65.0 でスクリプト注入に移した — 定数の手書きは version drift 中に落ち、サンプルが逆の版バケツに入る / issue #125）。**渡すのは実行時の事実だけ**で、層のオブジェクト自体（`adversarial_verify` / `recall_skeptic` / `meta_reviewer` / `pre_adjust_counts` / `below_threshold_counts`）と各層の `fired` は**必ず入れる**（落ちると `measurement_gaps` に `payload:<field>` が立つ）。**`agents` の内訳は transcript 由来の `dispatch.agents` と突合される**（issue #154）— 合わないと `agents-mismatch` が立つので、`specialist` / `round2` を実際に起動したのに 0 のままにしない（publish は止まらないが、`agents` は体数と時間・トークンの相関すべての分母なので申告漏れがそのまま集計を歪める）。**`tokens` も self-review に載る**（v2.70.0 で review 限定を撤回 / issue #143。`measure-tokens.sh` は publish 時点の transcript を読むので `t0 → publish` は閉じており、窓に Step 7 の修正作業が混ざるのは遅れて publish した回だけ ＝ `window: "since-t0-late"` で区別される）。これも**スクリプトが注入するので渡さない**。取り込み内訳や特定セッションを見たいときだけ `measure-tokens.sh` を手動実行する（→ 同 `## 17`）
- **報告した指摘を `findings_class` に分類して入れる**（`lint` / `test` / `judgement`。合計は報告件数と一致。分類の基準と「0 件を目標にしない」理由は orchestration-measurement.md `## 16` の「`findings_class` の使い方」）
- **書込先はメインリポジトリのルートに固定される**。self-review は worktree に入らないが、dev-workflow の作業用 worktree 内から実行されると cwd 相対では Step 8 の teardown で消える（→ orchestration-measurement.md `## 13`）。**publish の WARN に `⚠️ 計測:` の追記指示が出たら、レポート末尾にその 1 行を追記する**（#135 / #172。explorer の一括発行違反・wave 打点漏れ・**全層の wave 分割**（`wave-split`）は実行中に何も起きず、しかも打点漏れは違反の証拠自体を消す）

**payload 契約の正本は orchestration-measurement.md `## 16`**（フィールドの意味・版マーカー・後方互換をここに複写しない）。self-review 固有の点のみ:
- `pr` は常に `"local"`（PR を持たない）
- **`duration_closing_min` は常に `-1`（測定不能）**: publish（Step 6.4）が Step 7 の修正方針確認より前にあるため t2→t3 に人間の応答待ちが入らない。0 を publish すると「人間待ちが無かった」と誤読される
- **`duration_min`（全体）の意味は publisher 間で非対称**（review は締めフロー込み / self-review は Step 7 手前まで）。**`plugin` で層別してから比較する**。`head_verified` は publish しない（checkout を行わないため）。`recall_skeptic.skip_reason` は `"scope"`（`--focus`/`--exclude` 指定）も取りうる
- `recall_skeptic.findings_added` / `meta_reviewer.findings_added` はレポートの「動的ラウンド」行の数値と一致させる（それぞれ `[recall-skeptic]` / `[meta]` タグ付き指摘を数える。#121）
- **`comment_polish` は self-review のみのフィールド**（v2.45.0。`fired` / `suggested` の定義と計数基準は orchestration-measurement.md `## 16` が正本）
- **`md_polish` も self-review のみのフィールド**（v2.131.0）。**起動しなかった回も `fired: false` と `skip_reason` で必ず入れる**（落とすと `payload:md_polish` が立つ）。推敲 agent は `agents` に数えず、publish が `md_polish.fired` を申告体数に足して突合する。定義の正本は orchestration-measurement.md `## 16`

**publish の直後に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh"` を実行する**（→ 同 `## 18`。**`--embed` ではスキップ** — Step 6.5 の出力フォーマットに集計テキストを混ぜない）。出力は**そのままレポートの後ろに出す**（要約・再解釈をしない）。**⚠️ シグナル行が出たときだけ**戻り先ドキュメントを示して 1〜2 行の所見を添え、無い回は集計表だけ出す。失敗しても続行（best-effort）。

**決定系 doc の design-review 委譲**（Step 2 で起動すると決めた回だけ・`--embed` では起動しない）: retro の後、`Skill` tool で `design-doc:design-review` を `--path <path> --embed --effort ${CLAUDE_EFFORT}` で doc ごとに呼び、戻りを「🧭 決定の品質」の節としてレポートの後ろに出す。Step 5 のスコアリング・反証と Step 7 の修正方針の確認には入れない。呼び方・失敗の扱い・節の書式の正本は `design-review-guide.md` の 2〜4 節。publish の後に置くのは、design-review が起動する agent を計測の窓に入れないため

**次は Step 6.5**（SKILL.md に戻り、その見出しを見る）
