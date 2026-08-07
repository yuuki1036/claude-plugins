# オーケストレーション実行ガイド（review / self-review 共通の実行フェーズ詳細）

review / self-review SKILL.md の各フェーズから参照される実行詳細の正本。SKILL.md 本文は高レベルワークフロー（Phase 一覧・各 Phase の目的と入出力・分岐条件）を保持し、具体的な手順・bash・失敗時の扱いは本ファイル群に置く。エージェント構成の決定ロジック（起動条件・effort 適応・上限）は triage-guide.md、プロンプト本文は `prompts/` を参照。

## この分割の読み方（必要になった節だけ Read する）

**本ファイルは「毎回必要になる中核」だけを持つ。** 条件付きのフェーズは別ファイルに切り出してあり、**そのフェーズが実際に走ると決まってから Read する**（読まなければトークンを払わない）。

| ファイル | 内容 | 読むタイミング |
|---|---|---|
| **orchestration-guide.md**（本ファイル） | `## 0` skill 差分 / `## 1` HEAD SHA 注入 / `## 3.5` ファイル経由渡し / `## 4` AGENTS.md / `## 5` reviewer 起動 / `## 8` 観点カバレッジ検算 | **常時**（実行手順の冒頭で 1 回） |
| `orchestration-dynamic-rounds.md` | `## 6` Round 2 / `## 7` meta-reviewer / `## 9` 冷や読み skeptic / `## 10` 反証レイヤー | 各フェーズのスキップ条件を評価し、**実行すると決まったとき**。全スキップなら読まない |
| `orchestration-measurement.md` | `## 13` publish 先固定 / `## 13.1` `TS_FILE` パス / `## 14` 区間分割計測 / `## 16` payload 契約 / `## 17` トークン計測 | **publish 手前**（review 締めフロー 4 / self-review Step 6.4）。`## 17` だけは publish と独立で、前後比較したいときに任意 |
| `orchestration-optional-flows.md` | `## 2` Issue 必読 / `## 11` Vault 照合 / `## 12` 訂正の伝播前ガード / `## 15` embed mode JSON | 各フローの適用条件を満たしたときだけ |
| `design-notes/` | 設計判断・実測値・失敗の履歴 | **実行時には読まない**（本ファイル群を編集するときに読む） |

節番号は分割前の番号を維持している（外部からの参照を切らないため）。**他ファイルの節を指すときは必ずファイル名を前置する**（`orchestration-measurement.md ## 14` のように）。

## 0. skill 間の差分（本ファイル全体に適用）

| 項目 | review | self-review |
|---|---|---|
| agent の isolation | 全 agent を `isolation: "worktree"` で起動（PR ブランチの状態でファイルを読むため） | `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため） |
| PR 番号・期待 HEAD SHA 注入 | 必須（`## 1`） | 不要（PR を持たない） |
| diff の取得 | `triage-signals.sh --pr <N>`（内部で `gh pr diff`＝ GitHub 上の正しい差分） | `triage-signals.sh --base <ref>`（内部で `git diff`。base 差分 + staged + unstaged。`--staged` で staged のみ） |
| レビュー中止時 | ExitWorktree してから終了 | そのまま終了 |
| 動的ラウンドの Phase 番号 | 5.5 / 5.6 / 5.7 / 5.8 / 5.9 | 4.5 / 4.6 / 4.7 / 4.8 / 4.9 |

**同期起動の明示（両 skill・全 agent 起動に適用）**: explorer / reviewer / 追加 explorer / 再起動 reviewer / meta-reviewer / 冷や読み skeptic / 反証エージェントのすべてで、Agent call に `run_in_background: false` を必ず明示する。CC 2.1.198 で Agent tool の既定が background 実行に変わったため、省略するとオーケストレーターが結果を待たずに次フェーズへ進み、完了通知の遅れた agent の出力を取りこぼす（「反応が返ってこない agent」の正体）。`orchestration-dynamic-rounds.md` の各起動手順にもこのルールが適用される。

**並列発行の明示（複数体を起動する全フェーズに適用）**: `run_in_background: false` は「1 体ずつ順に起動する」ことを意味**しない**。複数体を起動するフェーズでは、**同一アシスタントメッセージ内に対象フェーズの全 Agent call を並べて一括発行し、その 1 応答で全結果を待つ**。**2 つは直交する独立の要件**（前者は取りこぼし防止、後者は並列性）。単体起動のフェーズ（meta-reviewer / 冷や読み skeptic）には適用対象がない。→ 根拠と実測: `design-notes/orchestration-rationale.md`

## 1. PR 番号・期待 HEAD SHA 注入（review のみ / agent 起動時に必須）

review skill が worktree で起動する **すべての agent**（explorer / reviewer / 追加 explorer / 再起動 reviewer / meta-reviewer / skeptic / 反証エージェント）に適用する。

agent prompt の冒頭に「PR 番号: `<PR_NUMBER>` / 対象 head ref: `<headRefName>` / **期待 HEAD SHA: `<headRefOid>`**」を必ず明記し、`prompts/explorer-common.md` / `prompts/reviewer-common.md` の `{{PR_NUMBER}}` / `{{HEAD_REF}}` / `{{HEAD_SHA}}` プレースホルダを実数値に置換する。`isolation: "worktree"` の子 worktree は親 branch を継承せず origin/default-branch から派生するため、checkout 指示を欠かすと PR の変更を観測できず偽陽性を量産する（GitHub issue #56）。

```bash
# PR_NUMBER / HEAD_SHA は Step 1 で取得済み（gh pr view の --json で再取得可能）
PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null || echo "<番号>")
HEAD_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid -q .headRefOid 2>/dev/null)
[ -n "$HEAD_SHA" ] || echo "FATAL: headRefOid を取得できない"
```

- **`HEAD_SHA` が空のまま agent を起動してはならない**。取得できない場合は PR コンテキスト取得失敗（review Step 1）と同格に扱い、ExitWorktree して中止する
- **ブランチ名での checkout は使わない**。子 agent 側は `refs/pull/<N>/head` を fetch して **detach で入る**（親 worktree と競合しない）
- **HEAD 検証は `{{HEAD_SHA}}` との突合で行う**（`{{HEAD_REF}}` はブランチ名なので detach 後の検証には使えず、プロンプト冒頭の文脈情報としてのみ残す）。セットアップ bash の正本は `prompts/reviewer-common.md` / `prompts/explorer-common.md`

→ 空 SHA が「静かな品質劣化」に倒れる仕組みと、ブランチ名 checkout が構造的に必ず失敗する経緯（issue #98 / #69）: `design-notes/orchestration-rationale.md`

## 3.5. 大きい共有コンテキストはファイル経由で渡す（review / self-review 共通 / GitHub issue #100 A）

**同一の内容を N 体のプロンプトに書き出さない。ファイルに落として agent に Read させる。**

オーケストレーターの出力トークンが `(N-1) × ブロック長` ぶん減り、agent が読むのがバイト同一の原本になるので忠実性も上がる。→ 実測と経緯: `design-notes/orchestration-rationale.md`

対象と扱い:

| 対象 | 渡し方 | 備考 |
|---|---|---|
| **プロンプトテンプレート**（reviewer / explorer / specialist / meta / 反証 / skeptic） | `prompts/` 配下の**パスのみ**注入し、agent 自身に Read させる。**オーケストレーターは Read しない** | 複製係数が最大（同一の共通指示が全 agent に付く）。共通指示だけで約 7.3k tokens あり、6 体構成では約 44k tokens の出力複製になっていた。索引は reviewer-prompts.md / explorer-prompts.md |
| **diff**（`gh pr diff` / `git diff`） | `triage-signals.sh` が `$DIFF_FILE` に保存し、**パス + 担当ファイル名**を注入。agent は `diff-slice.sh` で担当ぶんを切り出す | メインコンテキストは diff 全文を**一度も読まない**（Phase 0 はシグナルダイジェストで回す）。large PR ほど効く |
| PR コンテキストブロック | `fetch-pr-context.sh` の出力を `$PR_CTX_FILE` に保存し、**パスのみ**注入 | メインコンテキストは Phase 0 のタイプ判定のために 1 回だけ Read する |
| AGENTS.md / CLAUDE.md（`## 4`） | **元ファイルのパスをそのまま**注入（コピーを作らない） | 既にディスク上にあるので追加コストゼロ。パスは `triage-signals.sh` の `## agents-md` が出す |
| explorer 結果（review Step 5 / self-review Step 4 の選択的注入） | **従来どおりインラインで注入する** | 選択的注入なので複製係数がほぼ 1（1 explorer → 依存する 1〜2 reviewer）。ファイル化すると explorer 体数ぶんの Write が増えて逆効果 |

> **判断基準は「複製係数」**（= その内容が何体のプロンプトに現れるか）。係数が 1 に近いものはインラインの方が安い（Write / Read の往復が増えるだけ）。係数が体数ぶん立つものは必ずパス渡しにする。**同一内容を 2 体以上に書くと分かった時点でパス渡しを検討する。**

`$PR_CTX_FILE` のパスは**スクリプトが導出する**（`fetch-pr-context.sh --save` が保存先パスを stdout に返す）。**パスの組み立てを SKILL 本文や doc に複製しないこと** — 正本は `scripts/lib/review-paths.sh` で、作成側と削除側が食い違うと一時ファイルが恒久的に残る。

- **`WT` の導出を別ブロックの変数に頼らないこと**（orchestration-measurement.md `## 13.1` の `TS_FILE` と同じ理由）。シェル変数は Bash 呼び出し間で消えるため、空のまま `printf %s "" | cksum` を通すと**エラーにならず定数 `4294967295` が返り**、パスが「ホスト上の全リポジトリで共有される固定値」に潰れる。この経路は欠測ではなく**誤値**（別リポジトリの PR コンテキストを掴む）に倒れるので、orchestration-measurement.md `## 13.1` の「縮退先は欠測」原則の例外になってしまう。パスを組み立てる bash ブロックには必ず `WT=` の行を含める
- **プロンプトには「このファイルを最初に Read せよ」と明示する**（パスだけ置いても読まない agent が出る）。テンプレートの正本は `prompts/pr-context-rules.md`
- **`>` はスクリプトが失敗しても空ファイルを残す**。空・ヘッダ欠落のファイルは「読める」ため reviewer の「読めなかった場合」ガードをすり抜け、「過去指摘なし」と誤判定される。**一時ファイルに書いて成功時のみ `mv` する**こと（下記の bash はこの形にしてある）
- ファイル書込に失敗した場合は**従来どおりインライン注入にフォールバックする**（レビュー本体をブロックしない）。フォールバックしたことは `missing_coverage` には記録しない（観点の欠損ではないため）
- 掃除（review 締めフロー 4）も**同一ブロックで `WT` を再導出**してから消す。作成側と削除側でパスが食い違うと一時ファイルが恒久的に残る

## 4. AGENTS.md 階層動的選択（reviewer 起動前 / review Step 4.9・self-review Step 3.9）

変更ファイルパスから対応する `{dir}/AGENTS.md` を探索し、該当層だけを reviewer プロンプトに同梱する。リポジトリ全体の AGENTS.md / CLAUDE.md を毎回フルロードせず、変更があった層のみ拾うことで reviewer 入力 token を典型 30〜50% 削減する。

**探索は `triage-signals.sh` が Phase 0 で済ませている**（`## agents-md` セクション）。オーケストレーターは別途 bash を走らせず、ダイジェストのその行をそのまま使う。ロジック（変更ファイルの親ディレクトリから root まで遡って `AGENTS.md` / `CLAUDE.md` を拾い、`sort -u` する）はスクリプト側が正本。

ヒットした**ファイルのパス一覧**を、各 reviewer のプロンプトに `## 該当層の AGENTS.md / CLAUDE.md` セクションとして渡し、「最初に Read せよ」と明示する（`## 3.5`。既にディスク上にあるファイルなので本文をプロンプトへ転記しない — reviewer 体数ぶんの複製がそのまま消える）。オーケストレーター自身は読む必要がない。AGENTS.md が無いリポジトリでは `## agents-md` が空になるだけで no-op（後方互換）。

## 5. reviewer 起動の共通詳細

### effort 設計意図

reviewer の effort は実行時 `${CLAUDE_EFFORT}` に連動させる: **low/medium/high（既定）→ `high` / xhigh・max（明示 escalation）→ `xhigh`**。オーケストレーター（skill frontmatter）は `high`。これにより effort ゲート付きの独立レイヤー（meta-reviewer / 冷や読み skeptic）は既定で不発とし、high-risk 変更をレビューしたい時だけ `xhigh`/`max` で明示起動して escalation する運用にする。

> **reviewer_effort_profile（A/B 実験）**: userConfig `reviewer_effort_profile=differentiated` のときは、上の high 帯マッピングを focus 別に差別化し低密度観点だけ `medium` に下げる（高密度観点・specialist は `high` 維持、xhigh/max は無視）。マップと位置づけの正本は triage-guide.md `## 7.1`、既定 `uniform` は本項どおり。

> **体数の下限に注意**: 「常に 2 体以上」は不変条件では**ない**。`doc-review-mode` は 1〜2 体、`skip-mode` は `spec-compliance` のみ 1 体（triage-guide.md `## 2.5` のモード構成は Stage 2 の上限・最小保証より**優先**する）、self-review の `--focus` 指定時は最小保証すら起動しない。他所でこの不変条件を援用しないこと。

層ごとの effort:

| 層 | 体数 | effort | 既定 high で起動するか |
|---|---|---|---|
| meta-reviewer | 1 体・1 round（triage-dynamic-gates.md `## 8`） | `max` | しない（xhigh/max 起点） |
| 冷や読み skeptic | PR あたり 1 体・1 round（triage-dynamic-gates.md `## 8.5`） | `max` | しない（xhigh/max 起点） |
| 反証エージェント | **5 件ごと 1 体・上限 3 体**（triage-dynamic-gates.md `## 9`）＝唯一の変動費 | **`high`**（v2.41.0 で `max` から引き下げ） | **する**（非対称ゾーンに限定） |

> **反証 effort の引き下げは scoring-guide の不変条件に依存している**（BLOCKER / CRITICAL は `refuted` でも `severity-inflated` でも報告から消さず係争注記を付ける）。**不変条件を緩める変更をするときは、反証 effort を `max` に戻すかどうかを同時に判断すること。**

切り分けの原則は「**下げるのは『全レビューで走る』または『指摘数に比例する』レイヤー、据え置くのは 1 体固定の検証レイヤー**」。→ 各層の根拠: `design-notes/orchestration-rationale.md`

### diff-first 原則

各エージェントには **diff ファイルのパス（`$DIFF_FILE`）と担当ファイル名**を渡す（本文は渡さない。`## 3.5`）。agent 側は `scripts/diff-slice.sh "$DIFF_FILE" <path>...` で担当ぶんのハンクを切り出して読む。

レビューの真のソースは diff であることは変わらない。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

**担当ファイルの割り当ては観点に応じて決める**（`triage-signals.sh` の `## files` と `## focus-signals` の根拠ファイルが材料）。担当を絞れない観点（cross-cutting / pattern-consistency / spec-compliance 等）には `--list` で全ファイル名を渡し、必要なぶんを自分で切り出させる。

### 出力形式の検証と auto-retry（GitHub issue #69）

各 reviewer の出力が「レビュー結果」として妥当か機械的に検証する。以下のいずれも欠く出力は **非レビュー出力**（空応答・system-reminder / skill 案内の断片・tool_use ゼロでの早期終了等）とみなす:

- `### レビュー結果` 見出し（または `#### 指摘事項` / `#### 総括` のいずれか）
- 指摘が 1 件以上ある場合、`[confidence: XX]` と `[severity: ...]` タグを含む行が存在する
- **review の場合、`HEAD 検証:` 行が存在する**（下記）

### HEAD 検証の回収（review のみ / GitHub issue #98）

`## 1` の checkout は agent 側で走るため、**「検証したか」をオーケストレーターが観測できなければ、base branch を読んだままの agent の指摘が silent に報告へ混ざる**。そこで両プロンプトテンプレートの出力フォーマットに **必須 1 行** を置く（→ 経緯: `design-notes/orchestration-rationale.md`）:

```
HEAD 検証: <実測 SHA> / 期待 <{{HEAD_SHA}}> / 一致|不一致|未実行
```

オーケストレーターは結果回収時（review Step 4 / Step 5）にこの行を読み、以下を行う:

- **`不一致` / `未実行` / 行そのものが無い** → `missing_coverage` に `HEAD 不一致: <agent の focus>（実測 <SHA>）` を記録し、**その agent の指摘すべてに `[unverified: HEAD 不一致]` を付ける**（scoring-guide の claim grounding と同じ扱い）
- 行が無いだけの場合は上記の非レビュー出力と同様に **1 回だけ auto-retry** してよい（retry 後も無ければ記録して続行）
- 集計は `review:completed` payload の `head_verified` に載せる（`{ok, mismatch, unknown}`）。「何体が正しい HEAD を見ていたか」を事後に追えるようにするのが目的

**この行の不在自体が信号になる**ことが要点で、agent の善意に依存しない。self-review は PR を持たず checkout もしないため対象外。

非レビュー出力を検出した reviewer は、**同一プロンプトで 1 回だけ auto-retry** する（複数同時検出時はまとめて並列 retry）。retry 出力も非レビュー出力なら、その reviewer の focus / angle を `missing_coverage` に「非レビュー出力（auto-retry 後も形式不正）」として記録して続行する（欠損観点として扱い、フィルタを素通りさせない）。「指摘ゼロ」を明示的に報告した妥当な出力（`### レビュー結果` を持ち問題なしと結論）は非レビュー出力ではないため retry 対象にしない。

### 部分失敗耐性

- **explorer**: 個別 explorer が失敗しても全体を中止しない。失敗した explorer の type / focus / エラー要旨を `missing_coverage` リストに記録し、残った explorer の結果で続行する。該当 focus に依存する reviewer には、reviewer 起動時に「探索結果なし（失敗理由）」を明示して渡す
- **reviewer**: 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer の focus / angle / エラー要旨を `missing_coverage` リストに追記する

### 最小保証の閾値

Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す（review では ExitWorktree してから終了する）。それ以外は欠損観点を明示しつつスコアリング step に進む。

## 8. 観点カバレッジ検算（起動前検算 + 事後突合）

### 8a. 起動前検算（review Step 3.3・self-review Step 2.3 / 構成テーブル確定前・常時実行）

reviewer を起動する **前** に、Stage 1 の判定結果を機械的に検算する:

1. `triage-guide.md` の「reviewer の観点判定」表の各条件を、実際の diff シグナル（変更ファイルパス・diff 内文字列）に対して **メインコンテキストで再評価** する
2. **「条件を満たすのに構成に入っていない focus」** を検出する（例: `migrations/` 変更があるのに migration 不在、`.tsx` 変更があるのに ui-quality 不在、`package.json` 変更があるのに dependency 不在）
3. 検出した focus は **構成テーブルに追加してから確定する**（実効上限＝ effort 上限（triage-guide.md `## 7`）と規模キャップ（triage-guide.md `## 6.2`）の min に収まる範囲。**検算による追加で実効上限を超えてはならない** — 上限に達したら観点バンドル（triage-guide.md `## 7`）で既存 reviewer に相乗りさせ、それも不能なら `missing_coverage` に「観点未起動: <focus>（diff シグナル: <根拠>）」として記録する）
4. **モード除外（review のみ）**: Stage 0 で `default-mode` 以外（`--emergency` / `doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode`）に確定した場合、モードの推奨構成が観点判定表より優先するため**構成追加は行わない**。検出した focus は `missing_coverage` に「観点未起動: <focus>（mode: <mode> により意図的縮退）」として記録のみする。self-review は `--focus` / `--exclude` 指定時にその範囲内でのみ検算する

### 8b. 事後突合（review Phase 5.7・self-review Phase 4.7 / logging のみ・agent 追加起動なし）

スコアリング直前に、8a で確定した構成テーブルと **実際に起動・完走した focus** をメインコンテキストで突合し、差分（未起動・失敗・非レビュー出力で欠損した focus）を `missing_coverage` に追記する。**本フェーズで agent は追加起動しない**（観点漏れの検出は 8a へ前倒し済み。目的はレポートの「欠損観点」セクションを確定させること）。`## 5` の部分失敗耐性による記録と重複してよい（dedup してレポートに出す）

> **失敗 reviewer の補完起動は v2.39.0 で廃止した**（直列 wave 削減とのトレードオフ）。失敗 focus は `missing_coverage` として欠損観点セクションに必ず明示され、必要ならユーザーが再実行を指示する。auto-retry（`## 5` の出力形式検証）は形式不正のみが対象でハード失敗は救わない — **この差は仕様であり見落としではない**。→ 経緯: `design-notes/orchestration-rationale.md`

