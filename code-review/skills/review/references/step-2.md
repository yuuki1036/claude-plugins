<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
<!-- SSOT: code-review/references/triage-guide.md#3 @2ed7bbac -->
<!-- SSOT: code-review/references/triage-guide.md#6.1 @d6a3bd92 -->
<!-- SSOT: code-review/references/triage-guide.md#6.2 @f3e171ae -->
<!-- SSOT: code-review/references/triage-guide.md#5 @0b306f42 -->
### 2. diff の保存とシグナルダイジェストの取得

**diff 全文をメインコンテキストに載せない。** `triage-signals.sh` が diff をファイルへ保存し、Phase 0 に必要な**事実だけ**を compact に出力する。diff は reviewer / explorer へ**パスで渡す**（本文を転記しない。orchestration-guide.md `## 3.5`）。

**Step 2 と 2.4 は 1 つの Bash 呼び出しにまとめる**（GitHub issue #147）。間に LLM の判断が挟まらない — 後段は前段の**出力を読んで決める**のではなく、同じシェルが書いたファイルを読むだけなので、分けると往復ぶんの `cache_read` を払うだけになる。**Step 1 とは合流させない**（`gh pr checkout` の失敗＝中止経路を挟むため。失敗したまま `triage-signals.sh` を走らせると base branch の diff を掴む）。

```bash
# diff を $DIFF_FILE に保存し、シグナルダイジェストのみ stdout に出す。
# 出力に diff 本体は含まれない（large PR でもメインコンテキストは一定サイズ）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --pr <PR番号>

# Step 2.4 の重複検出。triage-signals.sh が書いた diff ファイルを読むので**この順序**
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-recent-review.sh" --pr <PR番号> --skill code-review:review

# 同じファイルを触った過去の merged PR のレビューコメント（GitHub issue #286）。triage-signals.sh が
# 書いた core の一覧を読むのでこの順序。コメントがあったときだけパスを 1 行出す
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-past-reviews.sh" --pr <PR番号> --base "$(gh pr view <PR番号> --json baseRefName -q .baseRefName)" --save
```

**`fetch-past-reviews.sh` がパスを出したら、Step 5 の共通ブロックに `past_reviews_file=<そのパス>` として入れる**（読み方の規約は reviewer-common.md「過去 PR の指摘」）。何も出さない回（コメント 0 件・GitHub に届かない repo）は入れない。`skip:` の 1 行は欠損観点ではないので `missing_coverage` に記録しない

**`set -e` を張らないこと**（CLAUDE.md Gotchas の ERR trap family。前段が落ちても後段は無害に空で返る）。

出力セクションと使い道:

| セクション | 内容 | 使う場所 |
|---|---|---|
| `## meta` | `diff_file=` / **`agent_ctx_file=`** の**パス**、base ref、`models=`（**実行世代** / #210。引けなければ行ごと出ない） | 以降の全 agent へ渡す。**ただし `models=` だけは渡さない** — 世代を伝えるとレビュー挙動が変わりうる（#210 のスコープ外）。人が回す前に見るための表示 |
| `## size` | `core_files` / `core_lines` / `size_tier` / `md_ratio` / `generated_ratio` / `migration_files` | Stage 0 のモード判定・Stage 2 の規模キャップ |
| `## files` | 変更ファイルの `class`(core/test/doc/gen) × 増減行数 | 担当ファイルの割り当て |
| `## hunks` | core ファイルの `@@` 行（関数コンテキスト付き） | 変更の性質の把握 |
| `## focus-signals` | 観点判定表（triage-guide.md `## 3`）のヒット数と根拠ファイル | Stage 1 のタイプ判定・Step 3.3 の起動前検算 |
| `## red-flags` | specialist 自動起動パターンのヒット | specialist 構成 |
| `## surface` | high-risk surface 判定（`db-write` / `money-numeric` / `authz`） | Step 3.4 の skeptic 相乗り判断 |
| `## explorer-signals` | 共通モジュール変更・500 行超ファイル | explorer の必要性判定 |
| `## agents-md` | 変更ファイル階層でヒットした AGENTS.md / CLAUDE.md のパス | Step 4.9（reviewer へパス渡し） |
| `## decision-docs` | `design_doc=`（design-doc が有効か）・`decision_docs_total=`（決定系 doc の総数）と、決定系 doc（RFC / ADR / design doc）ごとの追加した語を持つ行の数（10 件まで） | Step 3.3 の design-review 委譲の起動判定（`design-review-guide.md` の 1 節） |
| `## issue-ids` | branch 名から抽出した Issue ID | Step 3.2 の plan の `--issue-id`（Issue ファイルは plan が探す） |

**`size_tier` はスクリプトが triage-guide.md `### 6.2` の帯定義を機械適用した値**をそのまま使う（core = lock・生成物・テスト・doc を除いた実質規模。テスト 5 + doc 1 を含む 9 ファイルの PR が実質 3 ファイル `+22 -13` なのに large 扱いで 17 体起動する事故を防ぐ。GitHub issue #96）。Phase 0 の構成テーブル・Step 7 レポート冒頭・締めフロー 4 の `size_tier` に記録する。

**シグナルは事実であって判定ではない。** モード決定・観点採否・体数は triage-guide が決める（スクリプトは policy を持たない）。ヒット数 0 の観点は出力に現れない＝条件不成立、と読む。**例外はスクリプトが見ない条件だけ**: 常時必須の `bug-detection` / `claude-md-compliance`、仕様ソースの有無で決まる `spec-compliance`、`performance` の「ループ内の await」。前の 2 つと spec-compliance は Step 3.2 の plan が足し、ループ内の await は Step 3.3 の起動前検算で自分で評価する（それ以外の行は、表の条件をスクリプトが出すことをテストが固定している / GitHub issue #295）

**`diff_file=` と `agent_ctx_file=` の値は以降ずっと使うので、パス文字列そのものを控えておく**（後者は Step 5 の共通ブロック書き出し先。**slug は不透明な cksum 値なので、控え損ねると復元できない**）（シェル変数は Bash 呼び出し間で消えるため、`$DIFF_FILE` として引き回さず実パスを毎回書く）。

**ダイジェストで判断が付かない場合のみ** `diff-slice.sh` で必要なファイルの diff だけを読む（全文 Read はしない）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh" "<diff_file の実パス>" path/to/file.ts
```

**その他のコンテキスト収集:**
- PR 会話データ（Step 1 の fetch-pr-context.sh 出力をそのまま使用）
- `.claude/session-context.md` と knowledge ファイルの探索（spec-compliance の reviewer に同梱するため。Issue ファイルは自分で探さず、plan の `spec_source	issue-file` の行を使う / GitHub issue #389）。**spec-compliance を起動するかは自分で決めない** — session-context の branch 一致と Issue ファイルは Step 3.2 の plan が探す。knowledge と PR に紐づく Issue（`closingIssuesReferences`）は見つけたら plan に `--spec-source knowledge:<path>` / `--spec-source pr-issue:#N` で渡す（紐づく Issue は本文を保存した `--pr-issue-body <file>` も一緒に）
- プロジェクト特性シグナル（`package.json` の `react` / `next` 有無 = triage-guide.md `## 3` の React/Next.js 判定）

**スクリプトが失敗した場合**（`FATAL:` で終了）は従来どおり `gh pr diff <PR番号> --name-only` と `--stat` でファイル一覧と規模を取り、triage-guide.md `### 6.4` のフォールバック構成に落とす。**diff 全文の Read はこの経路でも行わない**。

**次は Step 2.4**（SKILL.md に戻り、その見出しを見る）
