<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#0 @d7242421 -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
<!-- SSOT: code-review/references/orchestration-guide.md#1 @25f2409b -->
<!-- SSOT: code-review/references/orchestration-guide.md#2 @ac86f925 -->
<!-- SSOT: code-review/references/orchestration-guide.md#5 @ad2cb12f -->
<!-- SSOT: code-review/references/triage-guide.md#4 @dc5b3022 -->
### 5. レビューフェーズ（reviewer 並列起動）

**プロンプトテンプレートは Read しない。パスを渡して agent 自身に読ませる**（組み立て方の正本: `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md`。共通指示だけで約 7.3k tokens あり、体数ぶん転記すると出力トークンが `(N-1) × 本文長` 膨らむ — orchestration-guide.md `## 3.5`）。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus` で並列起動する。effort は実行時 `${CLAUDE_EFFORT}` に連動させる（low/medium/high（既定）→ `high`、xhigh/max → `xhigh`。設計意図は orchestration-guide.md `## 5`）。プロンプトは **Read させるパスの列挙 + 可変部**だけで構成する。**パスは `${CLAUDE_PLUGIN_ROOT}` の部分だけをプラグインの実パス（この SKILL.md を Read したパスの `skills/` より手前）に置き換え、`/references/prompts/...` 以降は下に書いたまま渡す**（agent の Read は変数を展開しない。`references/` を省いて短く書き直すと agent が最初の Read に失敗し、プロンプト探しに往復を使う — #282）:

- **必ず Read させる**:
  - `${CLAUDE_PLUGIN_ROOT}/references/prompts/reviewer-common.md`
  - `${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/<focus>.md`
  - `${CLAUDE_PLUGIN_ROOT}/references/prompts/pr-context-rules.md`（review では常に加える）
- **条件付きで加える**:
  - 観点バンドル時 → `${CLAUDE_PLUGIN_ROOT}/references/prompts/bundle-rules.md` と束ねる focus ファイル群
  - **ペア条件が成立したとき → `${CLAUDE_PLUGIN_ROOT}/references/prompts/angles.md`**（xhigh/max の実ペアだけでなく、**high 以下の angle 内挿でも渡す**。渡さないと「ペアを削った代償を angle で補う」という縮小の前提が空振りする）
  - セッションコンテキストが有効なとき → `${CLAUDE_PLUGIN_ROOT}/references/prompts/session-context.md`（confidence −30 の規約はここにある。パスだけ渡しても規約は届かない）
- <!-- COMMENT-POLISH: detach --> **`${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/comment-polish.md` は Read 対象に入れない**（self-review 限定。他人の PR に文面の推敲を投稿するのは越権になりやすい。混入は comment-polish 連結チェックが Critical で止める）
- **Markdown 推敲の agent（`${CLAUDE_PLUGIN_ROOT}/references/prompts/md-polish.md`）も起動しない**（self-review 限定。理由は上と同じ。review の payload に `md_polish` は載らない）
- **可変部の共通ブロック（全 agent 共通の実値集合）は 1 ファイルに落としてパス渡しする**: Step 2 の `## meta` が出す `agent_ctx_file=` のパスに **Write で 1 回だけ**書き出し、各プロンプトには「まず `<agent_ctx_file>` を Read せよ」の 1 行だけを置く。**入れる項目・残す項目・フォールバックの正本は orchestration-guide.md `## 3.5`「可変部の共通ブロックに入れるもの」**（`{{PLUGIN_ROOT}}` / PR 番号 / `{{HEAD_SHA}}` / `{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` / `$DIFF_FILE` / `$PR_CTX_FILE` / AGENTS.md パス / 確定事実 など。実測で reviewer 5 + skeptic 1 + meta 1 + 反証 3 の計 10 本に手書きしていた — #124 (c)）。**書き出したら、その応答の中でこの wave に出す Agent call（reviewer 全行 + 相乗りする skeptic + specialist）を列挙してから発行に移る**（発行直前チェックポイント / orchestration-guide.md `## 0`。列挙より後に思いついた観点は同じ層へ後追いせず Round 2 へ回す — #220）
- **プロンプト側に残す可変部**: 担当 focus（冗長ペアなら angle）と担当ファイル、**explorer 結果の選択的注入**（構成テーブルの「explorer 依存」列。複製係数がほぼ 1 なのでインラインのまま）。plan の `spec_source` 行のうち `repo-spec-touched` / `repo-spec-ref` のパスを、**spec-compliance 担当にだけ**「仕様ファイル: `<path>`（`<label>`。Read して照合元にする）」で 1 行ずつ添える。`repo-spec-touched` には「変更した行の節を節ごと読み、同じ節の古い説明も見る」を添える
- **確定事実は共通ブロックに入れず、reviewer にだけインライン注入する**: Step 4 でまとめた `## 確定事実（explorer 共通・裏取り済み）` を**全 reviewer（specialist・skeptic を除く）**に合計 10 行以内で注入する。**skeptic に渡すと findings 非注入という層の設計核が壊れる**（triage-dynamic-gates.md `## 8.5`）。扱いの規約は `${CLAUDE_PLUGIN_ROOT}/references/prompts/reviewer-common.md` 側（#122）
- 全エージェントを `isolation: "worktree"` で起動する
- **全 reviewer の Agent call を同一メッセージ内で一括発行し、全体の結果が届くまで次へ進まない**（orchestration-guide.md `## 0`）
- **冷や読み skeptic の相乗り**: Step 3.4 で surface=true かつ Phase 5.8 のゲートを通過している場合、skeptic 1 体（`model: opus`, `effort: max`、プロンプトは `${CLAUDE_PLUGIN_ROOT}/references/prompts/recall-skeptic.md` をパス渡し）を **この一括発行に含める**。skeptic は findings 非注入が設計の核で reviewer 出力に依存しないため、直列に置く理由がない（triage-dynamic-gates.md `## 8.5` 起動タイミング）。結果の統合は Phase 5.8 で行う。**publish の `recall_skeptic.launch` は `"rider"`**（起動経路の自己申告 / #216）
- **PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}`・`{{SEVERITY_THRESHOLD}}` は共通ブロックに含める（必須）**: 値の意味と欠落時の影響は orchestration-guide.md `## 1` / `## 1.1` / `## 2`（MAIN_ROOT を欠かすと「検証不能」の誤申告で wave を 1 本失う #113、SEVERITY_THRESHOLD を欠かすと閾値未満を書かせて捨てる #117）。**プロンプトに再掲しない**

一括発行の**直前**に fleet 区間の開始マーカーを記録する（orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式で決める。Step 4 で explorer を起動していれば記録済みなので `grep` ガードで二重記録を防ぐ。`||` 形なのでガードが偽でもブロックは成功終了する）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1 --pr <PR番号>
```

全 reviewer の完了を待ち、結果を収集する。**回収した直後**に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave --pr <PR番号>` を実行する（打点→`t2` = agent 非稼働が保証される synthesis 区間。**動的ラウンドの各回収点でも毎回繰り返す** — 後勝ちなので最後の wave を判断しなくてよい。orchestration-measurement.md `## 14`）。

**HEAD 検証の回収（必須）**: 各出力の `HEAD 検証:` 行を読み、不在・不一致なら `missing_coverage` に記録して当該 reviewer の指摘全件に `[unverified: HEAD 不一致]` を付ける。件数は締めフロー 4 の `head_verified` へ（手順の正本: orchestration-guide.md `## 5`）。

reviewer 起動の共通詳細（effort 設計意図・diff-first 原則・出力形式の検証と auto-retry・部分失敗耐性・最小保証の閾値）: → orchestration-guide.md `## 5`

**最小保証の閾値のみ抜粋**: Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促してから ExitWorktree する。それ以外は欠損観点を明示しつつ Step 6 に進む。

**次は Step 5.5**（SKILL.md に戻り、その見出しを見る）
