# 決定系 doc の design-review 委譲（review / self-review / GitHub issue #334）

diff に含まれる決定系 doc（RFC / ADR / design doc）の**決定の質**を、design-doc プラグインの design-review に `--path <file> --embed` で見させ、結果を severity マトリクスの外の別節に出す。**起動条件・呼び出し・結果の扱い・レポートの正本**。視点のチェックリストと反証の手順は design-review 側が正本で、ここには写さない。

**読むタイミング**: Step 1 / 2 のダイジェストの `## decision-docs` に doc の行（`<数>\t<path>`）があるとき（下の 1 節で起動を決める）。`design_doc=` と `decision_docs_total=` の行は数えない。doc の行が無い回は読まない。

- **なぜ要るか**: doc-substance は文書の整合性（A 軸）と文書としての成立性（B 軸）を見る。「この決定は最善か」（代替案との比較・目的と手段の対応・既存コードとの整合・範囲の線引き）は B 軸の 1 項目として 1 体が問うだけで、視点を分けて見る構成と、その指摘を反証する手順を持たない。業務 PR の RFC で、review の指摘は整合性の MINOR に寄り、design-review を別に回して初めて決定に関わる MAJOR が 5 件出た（#334）
- **なぜ視点別 reviewer を code-review に持たないか**: design-review の視点・反証・severity の扱いを code-review に複製することになる（プラグイン間で複製が出たら分け方の誤りとみなす / ルート CLAUDE.md）
- **なぜ publish の後か**: design-review は main から design-reviewer agent を起動する。publish の前に呼ぶと、計測の窓（t0 から publish まで）にその agent が入り、`agents` の申告と transcript の突合（`agents-mismatch`）と wave 本数の期待値が崩れる

## 1. 起動条件と skip の理由

**上から順に**当てはめ、最初に当たった行で決める:

| 条件 | 起動 |
|---|---|
| `## decision-docs` に、追加した語を持つ行が 10 以上の doc が無い（typo・整形だけの決定系 doc の変更） | しない |
| self-review の `--embed`（feature-dev 等の呼び出し元に受け手が無い。G-V ループの度に回すと重い） | しない |
| `--focus` を指定した / `--exclude` に `design-review` を含む | しない |
| `--emergency`（review） | しない |
| 実行時 effort = `${CLAUDE_EFFORT}` が `low` | しない |
| `design_doc=0`（design-doc が有効でない） | しない。doc-substance が決定の質の問いを持つ（doc-substance の B 軸「決定の質」。パスは `${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/doc-substance.md`）ので、それで補う |
| 上のどれでもない | **する** |

- 対象は `## decision-docs` の上から **2 件まで**（追加した語を持つ行が多い順に並んでいる）。3 件目以降はレポートの節に「対象外: <path> ほか N 件（`/design-doc:design-review --path <path>` で個別に回せる）」と 1 行書く。N は `decision_docs_total=` から 3 を引いた数（一覧は 10 件で切れているので、行を数えない）
- **体数の上限（effort 上限・規模キャップ）の外**。reviewer 枠にも specialist 枠にも数えない
- Phase 0 の構成テーブルに `design-review` の行を 1 行足す（起動するなら「publish の後に <件数> 件」、しないなら理由）
- `--exclude design-review` は観点ではなく、この委譲を止める（`md-polish` と同じ扱い。スコープの絞り込みには数えない）

## 2. 呼び出し（publish と retro の後）

- self-review: Step 6.4 の publish と `review-retro.sh` の後、Step 7 の前
- review: 締めフロー 4（publish と `review-retro.sh`）の後、5 の掃除の前（PR の worktree の中にいるうちに呼ぶ）
- doc ごとに `Skill` tool で `design-doc:design-review` を呼ぶ。引数は `--path <repo ルート相対のパス> --embed --effort <実行時 effort>`。2 件のときは 1 件ずつ順に呼ぶ（design-review が自分で agent を並列起動するので、こちらで並列にしない）
  - **`--embed` を落とさない**。落とすと doc への反映の AskUserQuestion で止まり、doc を Edit しうる
  - 戻りの最後の行に `[embed-mode: design-review, no-edit]` が無い・Skill がエラーで終わったときは、その doc を「失敗」として節に 1 行書く。**決定の質のレビューを自分で代わりにやらない**。retry しない
- design-review が返したらターンを終えず、続きの手順（self-review は Step 7 / review は締めフロー 5）へ進む

## 3. 結果の扱い

- **Step 5（self-review）/ Step 6（review）のスコアリングと反証レイヤーを通さない**（design-review が自分の Phase 4.5 で反証する。もう一度通すと severity が二重に較正される）
- 報告件数・`findings_class`・`pre_adjust_counts`・付録・payload のどれにも数えない（publish の後なので、そもそも載らない）
- **二重掲載は除かない**。同じ箇所を doc-substance が整合性の観点で指摘していても、読み手の扱いが違う（整合性は著者が直すだけで済み、決定の質は採否の議論が要る）ので、両方の節に残す
- self-review の Step 7 の修正方針の確認に含めない（決定の質の指摘は採否の判断が要り、機械的に適用できない）

## 4. レポート（本体のレポートの後に足す節）

```
### 🧭 決定の品質（design-review / severity マトリクス対象外・採否は議論で決める）
<doc ごとに、design-review が返した Phase 4 のレポートをそのまま載せる（`## Design Review: <title>` の見出しは `#### <path>` に読み替える。表・詳細・裏取りされた前提は省かない）>
<失敗した doc: 「<path>: design-review を実行できなかった（<理由>）」>
<対象外にした doc があれば 1 節の 1 行>
```

- 起動しなかった回は節ごと省く（`## decision-docs` に doc の行が無い回と区別したいときは、Phase 0 の構成テーブルの行で足りる）
- review では締めフロー 3（投稿コメントのドラフト）の後に出る。利用者がこの節の指摘の投稿を頼んだら、closing-flow-guide の 3 の手順でドラフトを作る

## 5. 既知の限界

- 計測（`review:completed` の payload）に載らない。起動するかどうかと skip の理由は publish の時点で決まっているので、payload に層を足せば呼び出しの位置を変えずに載せられる。design-review の体数と所要を数えるには publish の前へ移す必要があり、`agents` の突合と wave 本数の期待値を design-review の分だけ補正する手当てが要る
- 委譲を起動した回は、事後の計測（`review-backfill.sh`）から「窓の外にも同セッションの agent がある（別レビュー混入）」として落ちる。design-reviewer の agent が t2 の数分後に起動するため。決定系 doc を含む回だけが backfill の母集団から抜けるので、母集団の欠けを読むときはこの理由も疑う
- design-doc の有効判定は設定ファイル（ユーザー / プロジェクト / プロジェクトのローカル）の `"design-doc@…": true|false` を見るだけで（`scripts/plugin-enabled.sh`）、`--plugin-dir` で読み込んだものは拾わない
- 決定系 doc の判定はパス（`adr(s)/` `rfc(s)/` `decision(s)/`（単数・複数とも）・`.claude/designs/`）と frontmatter の `type: rfc | adr` だけで、本文の中身からは判定しない（判定の正本は `scripts/triage-signals.sh` の `decision_docs`）
- review の対象は PR の head の doc だが、design-review は doc の全文を見る（変更した節に絞らない）。既存の長い ADR に数行足しただけの PR でも全文が対象になるので、起動の閾値（追加した語を持つ行が 10 以上）で絞っている
