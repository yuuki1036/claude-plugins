<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-measurement.md#16 @c0aa9e2d -->
<!-- SSOT: code-review/references/scoring-guide.md#報告閾値を割った指摘の記録 @b298b210 -->
<!-- SSOT: code-review/references/triage-guide.md#2.5 @b0730968 -->
<!-- SSOT: code-review/references/triage-guide.md#4 @bf441ebd -->
<!-- SSOT: code-review/references/triage-guide.md#5 @a2dc3482 -->
<!-- SSOT: code-review/references/triage-guide.md#6.2 @81106eca -->
### 7. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。**理由・補足はこのセクション本文に書き、payload の `missing_coverage` 配列には識別子のみを入れる**（語彙は orchestration-measurement.md `## 16`。自由文を入れると綴りが割れて集計不能になる）。

**冷や読み skeptic の観測可能性（issue #85）**: surface を含む変更では skeptic（Phase 5.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 5.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと**締めフロー 4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-dynamic-rounds.md `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## レビュー結果

{emergency モード時のみ先頭に: **⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること**}

**[mode: {emergency|doc-review|dba|supply-chain|skip|default}, size: {small|medium|large} (core N files / N lines), agents: [<focus 名のリスト>]]**

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従って決定）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**実効上限**: explorer N / reviewer N / specialist N（default-mode は Step 3.2 の plan の `explorer_cap` / `reviewer_cap` / `specialist_cap` を写し、効いた側を `cap_source` で書く（`effort` = **実行時** effort `{値}` の上限 / `size` = 規模キャップ `{帯}`）。他のモードはモードの推奨構成）
  ※ reviewer の effort と動的ラウンド（meta / skeptic / 反証ゲート）は**実行時 effort に連動**する。skill frontmatter の effort はオーケストレーター用で別枠
**動的ラウンド**: Round 2 {未実行 | スキップ（unmet 全件が到達不能）| スキップ（unmet をメインで直接照会して解決）| 実行（reviewer N 体 / explorer M 体）} / Meta-reviewer {実行（N 件追加）| skip 理由（`effort` / `config` / `no-high-severity` / `size-tier` / `emergency`）} / 冷や読み skeptic {実行（N 件追加）| skip（理由: config/emergency）| 非該当（surface なし）**← payload の `recall_skeptic.skip_reason` は `"no-surface"`。`fired=false` なので `null` にしない**} / 反証 {対象 N 件（うち meta 由来の追加バッチ M 件）| skip 理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件
**仕様整合**: {spec-compliance を起動した回: `<仕様ソース>`（Issue / session-context / knowledge / `--spec` / PR に紐づく Issue / repo の仕様書 N 件（diff が触った M 件））と照合し、仕様違反 N 件（うち文書への未反映 K 件） | 起動しなかった回: Step 3.2 の plan から写す — `spec_source	none` なら `仕様ソースなし`、`dropped	spec-compliance	size-cap` なら `規模キャップで未起動`、`effort-cap` なら `effort 上限で未起動`。default-mode 以外は `モード <名前> の構成で未起動`}（spec-compliance の結論を 1 行で。起動の有無が読み手に見えないと、指摘 0 件が「仕様どおり」と読まれる）
**反証**: 対象 N 件 / 係争 M 件（BLOCKER/CRITICAL、本文に反証メモ）/ 取り下げ K 件（MAJOR以下、付録に理由）{**スキップ時もこの行を出す**（書式の正本は orchestration-dynamic-rounds.md `## 10` 手順 4）。`no-eligible-findings` は `未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）` と書く — 「対象 0 件」は「検証したが問題なし」と読まれる}

### 🚨 BLOCKER 指摘

1. [confidence: 65][severity: BLOCKER][セキュリティ] 潜在的な SQL injection の疑い
   ファイル: src/api.ts:23-25
   影響: 攻撃成立時に DB 全体の漏洩・破壊
   修正案: parameterized query への変更

### ⚠️ CRITICAL 指摘

2. [confidence: 95][severity: CRITICAL][バグ] Missing error handling
   ファイル: src/auth.ts:67-72
   影響: 認証失敗時に null 参照で落ちる

3. [confidence: 90][severity: CRITICAL][re-flag: @reviewer-1] xxx（2026-04-22 に既指摘、diff で未修正）
   ファイル: src/api.ts:30-35

4. [confidence: 85][severity: CRITICAL][recall-skeptic][バグ] 空文字の draft が numeric 列へ素通りする
   ファイル: src/repo.ts:88
   影響: 22P02 で INSERT が落ちる
   {由来タグ: skeptic 単独由来は `[recall-skeptic]` / reviewer と重複した survivor は `[recall-skeptic:dup]`。締めフロー 4 の publish で `findings_added` / `findings_overlap` を数える唯一の根拠なので落とさない。番号は他の指摘と通し連番にする}

### 📋 MAJOR 指摘

5. [confidence: 95][severity: MAJOR][設計] ...

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

### 良かった点
- [src/auth.ts:67-72] 認証失敗の異常系を網羅的に分岐していて堅牢
- [src/parser.ts] 境界値テストが追加されており回帰検知が効く

### 総括
- 変更の目的と全体像
- 影響範囲
- 人間が最終確認すべき観点（特に BLOCKER の低 confidence 指摘）
```

**重要**: BLOCKER は confidence が低くても報告される設計。「疑わしい」段階で人間判断を促す目的なので、必ず「影響」フィールドで重大度の根拠を示すこと。

**良かった点の扱い**: 著者が意図的に良くした箇所を **0〜2 件** 具体的に挙げる（該当ファイル:行を添える）。設計判断・テストの充実・エッジケース対応・可読性の工夫など、レビューを通して見えた優れた点を拾う。指摘ばかりに偏らずメンタリング効果を持たせる狙いだが、「全体的に良い」のような中身のない称賛はノイズになるので書かない。特筆すべき点がなければセクションごと省略する。

**レポートを出力した直後に fleet 区間の終了マーカーを記録する**（締めフロー＝人間の応答待ちを混ぜないため。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t2 --pr <PR番号>
```

レポート出力後、以下の順で締める。締めフロー 1〜3 の詳細手順（AskUserQuestion の文言・options 提示条件・3 分類の判定基準・解説の観点・ドラフトのパターン×voice・メタ行・署名・writing-polish 推敲・出力フォーマット）の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/closing-flow-guide.md`（以下「closing-flow-guide」。1〜3 のいずれかを実行する場合のみ読む）

1. **指摘の精査（必要性ゲート / 任意）**: 報告マトリクス通過後の指摘が **1 件以上** ある場合のみ実行（指摘 0 件、または `--emergency` 時はスキップして 2 へ）。Step 6 の機械フィルタ（閾値を超えるか）と Phase 5.9 反証（事実として正しいか）に対し、**第 3 軸＝必要性（signal/noise）** を人間に委ねるステップ。closing-flow-guide `## 1` に従い AskUserQuestion で要否を確認し、「精査する」なら各指摘を取り下げ / 降格 / 残存に 3 分類して `## 精査結果` と調整後レポートを再出力する。**精査を行わなかった場合は報告マトリクス通過後の全指摘を「残存」とみなす**（以降のステップが参照する「残存・降格した指摘」はこの確定集合を指す）。以降の返答ドラフト・publish は精査後（post）の確定値を使う。

2. **PR・指摘の解説（任意）**: 返答ドラフトの前に PR の全体像や指摘の背景を解説して判断材料を揃える（チャット出力のみ・投稿はしない）。`--emergency` 時はスキップして 3 へ。closing-flow-guide `## 2` に従い AskUserQuestion で対象（PR について / 指摘について）を確認して解説する。解説の結果ユーザーが取り下げ・降格を望んだ場合は 1 の 3 分類に差し戻して調整後レポートを再出力してから 3 へ進む。

3. **投稿コメントのドラフト生成（任意）**: 精査後に残存／降格した指摘が **1 件以上** ある、**または** 総合判定が **Approve / Approve with nits** の場合に実行（どちらにも該当しなければスキップして 4 へ）。closing-flow-guide `## 3` に従い AskUserQuestion で要否と対象を確認し、`reply-tone-guide.md` `## 0 必須ルール` を厳守した文面を生成する（パターン×voice 選定・メタ行・署名・断定抑止・`Skill` tool 経由の writing-polish 推敲を含む）。**投稿は行わずドラフト出力のみ**。ユーザーが GitHub UI で手動投稿する。

4. **このステップの直前に `${CLAUDE_PLUGIN_ROOT}/references/orchestration-measurement.md` を Read する**（publish 先の固定・`TS_FILE` のパス導出・区間の算出式・payload 契約の正本。レビュー本体の実行には不要なのでここまで読まない）。**Event Bus publish (`review:completed`)**: 集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**指摘の精査を行った場合は精査後（post）の確定件数を使う**（取り下げ・降格を反映）。レポートに必要な数値（critical = confidence ≥ 90 件数、warning = 80 ≤ confidence < 90 件数、missing_coverage 配列）は既に手元にあるはず。

   **publish は専用スクリプトで行う**（書込先の固定・所要時間の算出・一時ファイルの掃除をまとめて担当する）。`duration_*` と **`agents.explorer_waves`** は**渡さない** — スクリプトが計測ファイル（explorer wave の打点）から算出して注入する:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh" \
     --plugin code-review:review --pr <PR番号> --payload '<orchestration-measurement.md `## 16` の review 用テンプレートを実値で埋めたもの。effort は '"${CLAUDE_EFFORT}"' の実値>'
   ```

   - **報告した指摘を `findings_class` に分類して入れる**（`lint` / `test` / `judgement`。合計は報告件数と一致。分類の基準と「0 件を目標にしない」理由は orchestration-measurement.md `## 16` の「`findings_class` の使い方」）
   - **publish の WARN に `⚠️ 計測:` の追記指示が出たら、レポート末尾にその 1 行を追記する**（#135 / #172。explorer の一括発行違反・wave 打点漏れ・**全層の wave 分割**（`wave-split`）は実行中に何も起きず、しかも打点漏れは違反の証拠自体を消す）
   - スクリプトが payload の JSON 妥当性検証・**`missing_coverage` の語彙検証**（識別子以外＝理由つき自由文は `FATAL` で弾く。**理由はレポートの「⚠️ 欠損観点」に書き、フィールドごと落として通さない** / issue #132）・**動的層の `skip_reason` の語彙検証**（`adversarial_verify` / `recall_skeptic` / `meta_reviewer` の許容値は orchestration-measurement.md `## 16` が正本。**外れると `FATAL` で publish せず落ちる**ので、理由の補足はレポート本文に書く。`fired=false` で理由を書き忘れた回だけは落とさず `measurement_gaps` に倒す）・書込先のメインリポジトリ固定・一時ファイルの掃除まで行う（→ orchestration-measurement.md `## 13`）。**`measurement_gaps` / `derived_markers` / `diff_digest` / `tokens` / `models`（**モデル世代**。transcript の `message.model` からの機械計測で、渡しても捨てられる / issue #169）と版マーカーの整数（`schema` / `gate_schema` / `attribution_schema` / `calibration_schema`）も渡さない**（`derived_markers` は**打点が落ちた区間を agent の実測時刻で埋めた記録**で、`measurement_gaps` とは排他ではない / issue #161） — 計測ファイル・一時 diff・transcript から算出して注入される（定数の手書きは version drift 中に落ちサンプルが逆の版バケツに入るため v2.65.0 で移した / issue #125）。**渡すのは実行時の事実だけ**で、層のオブジェクト自体（`adversarial_verify` / `recall_skeptic` / `meta_reviewer` / `pre_adjust_counts` / `below_threshold_counts`）と各層の `fired` は**必ず入れる**（落ちると `measurement_gaps` に `payload:<field>` が立つ）。**`agents` の内訳は transcript 由来の `dispatch.agents` と突合される**（issue #154）— 合わないと `agents-mismatch` が立つので、`specialist` / `round2` を実際に起動したのに 0 のままにしない（publish は止まらないが、`agents` は体数と時間・トークンの相関すべての分母なので申告漏れがそのまま集計を歪める）

   **payload 契約の正本は orchestration-measurement.md `## 16`**（フィールドの意味・版マーカー・後方互換をここに複写しない）。review 固有の点のみ:
   - `review_mode` は Stage 0（Step 3.0）で確定したモードから `-mode` を外した名前（`default` / `emergency` / `doc-review` / `dba` / `supply-chain` / `skip`）。**省かない** — publish はこの値が `default` の回だけ、plan ファイルが無ければ `measurement_gaps` に `plan` として立てる（GitHub issue #387）。欠けた回は `payload:review_mode` が立ち、語彙外は publish が `FATAL` で止める
   - `pr` は Step 1 で取得した PR 番号の文字列（失敗時は `"local"`）。`head_verified` は review のみ（Step 4 / Step 5 の `HEAD 検証:` 行の集計）。`duration_closing_min` は締めフロー（人間の応答待ち）を捉えるが**改善の効果測定には使わない**（人間の都合で 10 倍振れる）
   - `agents.round2` / `recall_skeptic.findings_added` はレポートの「動的ラウンド」行の数値と一致させる。**`meta_reviewer.findings_added` も同様**（`[meta]` タグ付き指摘を数える。#121）

   **publish の直後に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh"` を実行する**（→ 同 `## 18`）。出力は**そのままレポートの後ろに出す**（要約・再解釈をしない）。**⚠️ シグナル行が出たときだけ**戻り先ドキュメントを示して 1〜2 行の所見を添え、無い回は集計表だけ出す。失敗しても続行（best-effort）。

   **決定系 doc の design-review 委譲**（Step 3.3 で起動すると決めた回だけ）: retro の後、`Skill` tool で `design-doc:design-review` を `--path <path> --embed --effort ${CLAUDE_EFFORT}` で doc ごとに呼び、戻りを「🧭 決定の品質」の節としてレポートの後ろに出す（PR の worktree の中にいるうちに呼ぶ）。Step 6 のスコアリング・反証には入れない。呼び方・失敗の扱い・節の書式の正本は `design-review-guide.md` の 2〜4 節。publish の後に置くのは、design-review が起動する agent を計測の窓に入れないため。この節の指摘を投稿したいと言われたら、締めフロー 3 の手順でドラフトを作る

5. **agent worktree の掃除（ExitWorktree の直前 / 必須）**: agent は `isolation: "worktree"` で起動するため体数ぶんの worktree が配下に残り、**この状態では `ExitWorktree(remove)` が state 検証に失敗して worktree を畳めない**（GitHub issue #105）。**同じブロックで publish 済みかを確認する**（4 の publish は副作用のみで出力に何も足さないため、脱落しても実行中は気づけない。ここは必須ステップなので通過が保証される / GitHub issue #133。**警告が出たら ExitWorktree の前に 4 へ戻る** — session id が無い環境では `TS_FILE` の slug が worktree のパス由来になり、抜けた後では同じ計測ファイルを引けなくなる / orchestration-measurement.md `## 13.1`）:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" publish-pending --pr <PR番号>
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/cleanup-agent-worktrees.sh"
   ```

   削除対象は **①現在の worktree の配下 ②未コミット変更なし ③自分自身ではない** の 3 条件を満たすものだけ（並行レビューや開発用 worktree には触れない）。**出力の件数をレポートに 1 行残し**、失敗が 1 件以上なら手動 remove を案内する。掃除に失敗しても続行する（best-effort）。→ 残留する理由: `design-notes/orchestration-rationale.md`

6. **ExitWorktree** で worktree から抜ける。

7. **関連 worktree の teardown 案内（任意・非ブロッキング）**: ExitWorktree 後（main clone 上）、PR ブランチに紐づく**開発用 worktree**（dev-workflow:worktree-setup で作成したもの）が残っていないか検出する。ブランチ名一致だけではレビュー用に EnterWorktree した一時 worktree（`.claude/worktrees/` 配下）と区別できないため、**パス除外 + worktree-setup マーカーの 2 条件**で開発用 worktree に限定する:

   ```bash
   # ブランチ名を SKILL 本文に埋めない（PR 作者が制御する文字列がシェルで評価される経路になる）。
   # PR 番号だけ渡し、ブランチ名の取得はスクリプト内に閉じる
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-dev-worktree.sh" --pr <PR番号>
   ```

   - 検出した場合のみ、最後に一言案内する: 「関連する開発用 worktree が残っています: `<path>`。作業が完了していれば該当 worktree 内で `/worktree-teardown` を実行して片付けられます」
   - dev-workflow の有効判定は self-review Step 8 と同じ enabled-only 判定（`grep -Eq '"dev-workflow@[^"]*"[[:space:]]*:[[:space:]]*true'` を global / project / local の settings 3 ファイルに対して実行）。無効なら `git worktree remove <path>` の手動案内に切り替える
   - worktree-teardown は worktree 内からしか実行できないため、ここでは**自動起動しない**（案内のみ）
   - 未検出なら何も出力しない
   - 補足: 開発用 worktree が PR ブランチを checkout したままだと、Step 1 の `gh pr checkout` は二重チェックアウト禁止で失敗する（レビュー自体は `gh pr diff` ベースで劣化続行できる）。その経路でも本ステップの検出は機能する

**ここで終わり**
