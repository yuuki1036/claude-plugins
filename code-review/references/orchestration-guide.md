# オーケストレーション実行ガイド（review / self-review 共通の実行フェーズ詳細）

<!-- 正本依存（SSoT pin）。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->

review / self-review SKILL.md の各フェーズから参照される実行詳細の正本。SKILL.md 本文は高レベルワークフロー（Phase 一覧・各 Phase の目的と入出力・分岐条件）を保持し、具体的な手順・bash・失敗時の扱いは本ファイル群に置く。エージェント構成の決定ロジック（起動条件・effort 適応・上限）は triage-guide.md、プロンプト本文は `prompts/` を参照。

## この分割の読み方（必要になった節だけ Read する）

**本ファイルは「毎回必要になる中核」だけを持つ。** 条件付きのフェーズは別ファイルに切り出してあり、**そのフェーズが実際に走ると決まってから Read する**（読まなければトークンを払わない）。

| ファイル | 内容 | 読むタイミング |
|---|---|---|
| **orchestration-guide.md**（本ファイル） | `## 0` skill 差分 / `## 1` HEAD SHA 注入 / `## 3.5` ファイル経由渡し / `## 4` AGENTS.md / `## 5` reviewer 起動 / `## 8` 観点カバレッジ検算 | **常時**（実行手順の冒頭で 1 回） |
| `orchestration-dynamic-rounds.md` | `## 6` Round 2 / `## 7` meta-reviewer / `## 9` 冷や読み skeptic / `## 10` 反証レイヤー | 各フェーズのスキップ条件を評価し、**実行すると決まったとき**。全スキップなら読まない |
| `orchestration-measurement.md` | `## 13` publish 先固定 / `## 13.1` `TS_FILE` パス / `## 14` 区間分割計測 / `## 16` payload 契約 / `## 17` トークン計測 / `## 18` 振り返り集計 / `## 19` 重複検出 | **publish 手前**（review 締めフロー 4 / self-review Step 6.4）。`## 17` は publish と独立で任意、`## 19` だけは重複検出（Step 2.4 / 1.4）の背景を引くときに読む |
| `orchestration-optional-flows.md` | `## 2` Issue 必読 / `## 11` Vault 照合 / `## 12` 訂正の伝播前ガード / `## 15` embed mode JSON | 各フローの適用条件を満たしたときだけ |
| `design-notes/` | 設計判断・実測値・失敗の履歴 | **実行時には読まない**（本ファイル群を編集するときに読む） |

節番号は分割前の番号を維持している（外部からの参照を切らないため）。**他ファイルの節を指すときは必ずファイル名を前置する**（`orchestration-measurement.md ## 14` のように）。

## 0. skill 間の差分（本ファイル全体に適用）

| 項目 | review | self-review |
|---|---|---|
| agent の isolation | 全 agent を `isolation: "worktree"` で起動（PR ブランチの状態でファイルを読むため） | `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため） |
| PR 番号・期待 HEAD SHA 注入 | 必須（`## 1`） | 不要（PR を持たない） |
| `{{MAIN_ROOT}}` 注入 | 必須（`## 1.1`） | 不要（worktree を使わないので依存はそのまま読める） |
| 実効報告閾値 `{{SEVERITY_THRESHOLD}}` 注入 | **必須（`## 2`）** | **必須（`## 2`）** |
| diff の取得 | `triage-signals.sh --pr <N>`（内部で `gh pr diff`＝ GitHub 上の正しい差分） | `triage-signals.sh --base <ref>`（内部で `git diff`。base 差分 + staged + unstaged。`--staged` で staged のみ） |
| レビュー中止時 | ExitWorktree してから終了 | そのまま終了 |
| 動的ラウンドの Phase 番号 | 5.5 / 5.6 / 5.7 / 5.8 / 5.9 | 4.5 / 4.6 / 4.7 / 4.8 / 4.9 |

**同期起動の明示（両 skill・全 agent 起動に適用）**: explorer / reviewer / 追加 explorer / 再起動 reviewer / meta-reviewer / 冷や読み skeptic / 反証エージェントのすべてで、Agent call に `run_in_background: false` を必ず明示する。CC 2.1.198 で Agent tool の既定が background 実行に変わったため、省略するとオーケストレーターが結果を待たずに次フェーズへ進み、完了通知の遅れた agent の出力を取りこぼす（「反応が返ってこない agent」の正体）。`orchestration-dynamic-rounds.md` の各起動手順にもこのルールが適用される。

**並列発行の明示（複数体を起動する全フェーズに適用）**: `run_in_background: false` は「1 体ずつ順に起動する」ことを意味**しない**。複数体を起動するフェーズでは、**同一アシスタントメッセージ内に対象フェーズの全 Agent call を並べて一括発行し、その 1 応答で全結果を待つ**。**2 つは直交する独立の要件**（前者は取りこぼし防止、後者は並列性）。**1 体しか起動しないフェーズも「他フェーズと同一 wave」なら適用対象**である（冷や読み skeptic は reviewer wave に相乗り / **meta-reviewer は反証バッチと同一メッセージ** — v2.61.0。起動タイミングの正本は triage-dynamic-gates.md `## 8` / `## 8.5`）。真に単独 wave になるのは skeptic の fallback 起動だけ。**守られたかは publish 時に事後計測される** — `meta.json` の `toolUseId` から wave を復元し、**単独 wave が 3 連続以上**なら payload の `dispatch.verdict` が `serial` になり WARN が出る（orchestration-measurement.md `## 16` / GitHub issue #142・#149）。層ごとに wave が分かれること自体（explorer → reviewer → 反証）は `layered` で、違反ではない。**ただし `serial` は 3 連続を要求するので「reviewer 5 体のうち 1 体だけ先に出した」型を取り逃す**（実測: fleet span の 20% ＝ 9 分を失った回が `layered` 判定だった）。`agents.explorer_waves` も explorer 層しか数えない。**全層を見るのは `measurement_gaps` の `wave-split`**（v2.85.1 / 期待 wave 本数との突合 / `## 16`）で、**v2.91.0 から WARN を出す**（偽陽性 2 型が同定できたので測定段階を抜けた / #172。実測では判定可能な直近 5 レビュー中 4 件が本物の違反で、既存 2 経路は 4 件とも取り逃していた）。**3 経路とも事後計測で、実行中には止まらない**。→ 根拠と実測: `design-notes/orchestration-rationale.md`

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

### 1.1 メインリポジトリのパス注入（`{{MAIN_ROOT}}` / GitHub issue #113）

**同じ agent 群に `{{MAIN_ROOT}}` も必ず注入する。** 子 worktree には `node_modules` などの gitignore 対象の依存が存在しないため、これを欠かすと **ディスク上にある事実を agent が「検証不能」と誤申告**し、Round 2 が走る構成でしか回収されない（実測: 初回 wave で 3 件が `unmet_information` に落ち、Round 2 で全件解決して MAJOR 1 件がそこで初めて出た = wave 1 本ぶんの遅延）。

**値は Phase 0 の digest から取る。組み立てを SKILL 本文に書かない**（`## 3.5` の一時ファイルパスと同じ理由）。`triage-signals.sh` の `## host-deps` セクションが出す:

| 行 | 内容 | プロンプトでの扱い |
|---|---|---|
| `main-root <path>` | メイン作業ツリーの絶対パス（`lib/review-paths.sh` の `review_main_root`。linked worktree からも解決できる） | `{{MAIN_ROOT}}` を置換する。**行が無ければ導出失敗**なので `{{MAIN_ROOT}}` を注入せず、依存の読み取り先は渡さない（誤値を注入するより注入しない方が安全側） |
| `dep-dir <path>` | メイン側に実在する依存ディレクトリ（`node_modules` / `vendor` / `.venv` / `venv` / `.yarn`）。**symlink と `main-root` 配下に収まらない実体は除外済み**（CWE-59） | 冒頭に列挙して渡す。0 件なら列挙しない |
| `lockfile-changed <path>` | PR が lockfile を変更している | **出ていれば冒頭に明記する**。メイン側の依存が PR 後の状態と一致しないため、agent は根拠にする際に confidence を下げる |

- **`{{MAIN_ROOT}}` は「依存を読むための逃げ道」であって、レビュー対象を読む場所ではない**。メイン側はユーザーの作業ツリーで PR と無関係な未コミット変更を含みうる。この非対称はプロンプト側（`prompts/reviewer-common.md` / `prompts/explorer-common.md`）にも書いてあるが、注入時に潰さないこと
- self-review は `isolation: "worktree"` を使わない（依存はそのまま読める）ため**注入不要**
- **`main-root` 行が出ない場合がある**（メイン作業ツリーを導出できないとき。スクリプトは stderr に WARN を出す）。そのときは `{{MAIN_ROOT}}` を未置換のまま渡さず、**プロンプトからこの節ごと省く**。agent 側は未注入時に本節を適用しない規約になっている（`prompts/reviewer-common.md`）

→ 空 SHA が「静かな品質劣化」に倒れる仕組みと、ブランチ名 checkout が構造的に必ず失敗する経緯（issue #98 / #69）: `design-notes/orchestration-rationale.md`

## 2. 実効報告閾値の注入（`{{SEVERITY_THRESHOLD}}` / **review・self-review 共通** / GitHub issue #117）

**reviewer には userConfig `review_severity_threshold` の実効値を必ず渡す**（既定 `MAJOR`）。報告マトリクスと本閾値は**直列に掛かる 2 段のフィルタ**で、reviewer は後段を知らされていなかったため、構造的にほぼ報告されない severity に出力予算を使い続けていた（実測: MINOR 調整前 60 → 報告 9 件 = **85% 破棄**、うち confidence 95+ が 7 件）。

- 閾値未満と判定した指摘は reviewer が本文を書かず **`## below-threshold` に件数だけ**返す。規約の正本は `prompts/reviewer-common.md`「実効報告閾値」
- **オーケストレーターは `pre_adjust_counts` にこの件数を足す**（`orchestration-measurement.md ## 16`）。足さないと「検出しなかった」と「列挙しなかった」が 0 に潰れ、本施策の効果測定と再評価の根拠が同時に失われる
- **足した件数は `below_threshold_counts` にも再掲する**（同 `## 16` / #146）。合算のままでは「本文を書いてから捨てた」と「件数だけ返した」を分離できず、**本施策が出力トークンを実際に節約できているか**が測れない
- **抑制されるのは列挙だけで判定は従来どおり**。閾値未満を理由に severity を繰り上げさせない（較正が壊れ、`pre_adjust_counts` も歪む）
- **self-review の B 系統（`## コメント推敲提案`）は severity を持たないため対象外**。閾値も抑制も効かない（`prompts/focus/comment-polish.md`）

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
| **可変部の共通ブロック**（全 agent 共通の実値集合 / v2.63.0） | `triage-signals.sh` の `## meta` が出す `agent_ctx_file=` のパスに**オーケストレーターが 1 回だけ書き出し**、各プロンプトには**パスと focus 固有の差分だけ**を書く | 複製係数 = 体数で表中最大級。実測（issue #124）では reviewer 5 + skeptic 1 + meta 1 + 反証 3 の**計 10 本に同一ブロックを手書き**しており、wave 間のメイン時間 ≈16.1 分（fleet の 26%）がここに効いていた。中身は下記 |
| **explorer の「確定事実」**（`## 確定事実（explorer 共通・裏取り済み）`） | **共通ブロックには入れず、reviewer にだけインライン注入する**（**specialist・skeptic には渡さない**）。**合計 10 行以内** | **意図的にファイル化しない唯一の枠。** 共通ブロックに同梱すると skeptic にも届き、`triage-dynamic-gates.md ## 8.5` の「findings 非注入がこのレイヤーの設計の核」が壊れる（false-negative hunter が fleet の所見を前提にしてしまう）。10 行上限で複製コストは既に抑えられており、**独立性と引き換えにする価値がない** |

> **判断基準は「複製係数」**（= その内容が何体のプロンプトに現れるか）。係数が 1 に近いものはインラインの方が安い（Write / Read の往復が増えるだけ）。係数が体数ぶん立つものは必ずパス渡しにする。**同一内容を 2 体以上に書くと分かった時点でパス渡しを検討する。**

### 可変部の共通ブロックに入れるもの（v2.63.0 / GitHub issue #124 (c)）

`agent_ctx_file` に**全 agent で同一の実値**を書き、プロンプト側は「まず `<agent_ctx_file>` を Read せよ」の 1 行 + focus 固有の差分だけにする:

- `{{PLUGIN_ROOT}}` の実パス（テンプレート内の `${CLAUDE_PLUGIN_ROOT}` の読み替え指示を含む）
- `$DIFF_FILE` のパスと `diff-slice.sh` の使い方
- **base ref**（`## meta` の `base=`。skeptic / 反証 / base 検算がいずれも要求する）
- `{{SEVERITY_THRESHOLD}}` の実効値
- AGENTS.md / CLAUDE.md のパス一覧（`## 4`）
- **review のみ**: `{{MAIN_ROOT}}` と `dep-dir` 一覧（`## 1.1`）、PR 番号と `{{HEAD_SHA}}`、`$PR_CTX_FILE` のパス
- session-context が有効なときはそのパス
- 全 agent 共通の重点指示（`--focus` / `--exclude` のスコープ等）

**共通ブロックに入れないもの**（agent ごとに違う / 渡してはいけない）: Read させるテンプレートのパス（`focus/<name>.md` 等）、担当 focus と angle、担当ファイル、explorer 結果の選択的注入、Vault 注入、**explorer の確定事実**（上表のとおり reviewer 限定でインライン。specialist / skeptic には渡さない）、**findings**（反証エージェントに reviewer の理由文を渡さない規約）。

- **書き出すのは explorer wave の回収後・reviewer 一括発行の直前に 1 回**（`## meta` はもっと早く出るが、パスを控えておくだけで書き出しはここ）。**explorer プロンプトは対象外**（explorer は共通ブロックより前に走るので従来どおりインライン可変部）
- **20 行以内に収まるならインラインでよい**（Write / Read の往復の方が高くつく）。実運用では上記を並べると常に超えるので**ファイル化が既定**。この 20 行は**共通ブロック全体**の閾値で、上表の確定事実の 10 行とは別の数字
- **書き出しは 1 回だけ**。wave をまたいで内容が変わらないので、Round 2 / meta / 反証の各 wave でも同じパスを渡す
- **書込に失敗したら従来どおりインライン注入にフォールバックする**（レビュー本体をブロックしない。`missing_coverage` には記録しない）
- 掃除は `publish-review-event.sh` が行う（`$DIFF_FILE` / `$PR_CTX_FILE` と同じ扱い）

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


> **体数の下限に注意**: 「常に 2 体以上」は不変条件では**ない**。`doc-review-mode` は 1〜2 体、`skip-mode` は `spec-compliance` のみ 1 体（triage-guide.md `## 2.5` のモード構成は Stage 2 の上限・最小保証より**優先**する）、self-review の `--focus` 指定時は最小保証すら起動しない。他所でこの不変条件を援用しないこと。

層ごとの effort:

| 層 | 体数 | effort | 既定 high で起動するか |
|---|---|---|---|
| meta-reviewer | 1 体・1 round（triage-dynamic-gates.md `## 8`） | `max` | しない（xhigh/max 起点） |
| 冷や読み skeptic | PR あたり 1 体・1 round（triage-dynamic-gates.md `## 8.5`） | `max` | **する**（high 起点 / surface=true のときだけ。v2.52.0 で昇格） |
| 反証エージェント | **5 件ごと 1 体・本体上限 3 体 ＋ meta 由来の追加バッチ 1 体**（計 4 体 20 件 / v2.61.0。triage-dynamic-gates.md `## 9`）＝唯一の変動費 | **`high`**（v2.41.0 で `max` から引き下げ） | **する**（非対称ゾーンに限定） |

> **反証 effort の引き下げは scoring-guide の不変条件に依存している**（BLOCKER / CRITICAL は `refuted` でも `severity-inflated` でも報告から消さず係争注記を付ける）。**不変条件を緩める変更をするときは、反証 effort を `max` に戻すかどうかを同時に判断すること。**

切り分けの原則は「**下げるのは『全レビューで走る』または『指摘数に比例する』レイヤー、据え置くのは 1 体固定の検証レイヤー**」。→ 各層の根拠: `design-notes/orchestration-rationale.md`

### diff-first 原則

各エージェントには **diff ファイルのパス（`$DIFF_FILE`）と担当ファイル名**を渡す（本文は渡さない。`## 3.5`）。agent 側は `scripts/diff-slice.sh "$DIFF_FILE" <path>...` で担当ぶんのハンクを切り出して読む。

レビューの真のソースは diff であることは変わらない。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

**担当ファイルの割り当ては観点に応じて決める**（`triage-signals.sh` の `## files` と `## focus-signals` の根拠ファイルが材料）。

**全ファイルを渡してよい観点は次の 3 つに限る**（GitHub issue #144）: `cross-cutting` / `pattern-consistency` / `spec-compliance`。いずれも**ファイル間の関係そのものが観点**なので、部分集合では判定が成立しない。この 3 つには `--list` で全ファイル名を渡し、必要なぶんを自分で切り出させる。

**それ以外の観点は絞る。** 旧版はこの 3 つを「等」で開いていたため、`## focus-signals` に根拠ファイルを持つ観点まで既定で全件に落ちていた（実測: `claude-md-compliance` に全変更ファイルを渡した回が重み付き **857k で指摘 1 件**）。絞る材料が本当に無ければ全件を渡してよいが、**その reviewer の構成テーブル `指示` 欄に `担当: 全件` と書く** — 判断して全件にしたのか、既定で落ちたのかを事後に区別できないと、この規約が守られたかどうかを観測できない。

**`class`（core/test/doc/gen）による機械的な絞り込みは採らない**（→ `design-notes/pending-optimizations.md` `## 10`）。

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

- **`不一致` / `未実行` / 行そのものが無い** → `missing_coverage` に識別子 `head-mismatch:<agent の focus>` を記録し（**実測 SHA はレポート本文へ**）、**その agent の指摘すべてに `[unverified: HEAD 不一致]` を付ける**（scoring-guide の claim grounding と同じ扱い）
- 行が無いだけの場合は上記の非レビュー出力と同様に **1 回だけ auto-retry** してよい（retry 後も無ければ記録して続行）
- 集計は `review:completed` payload の `head_verified` に載せる（`{ok, mismatch, unknown}`）。「何体が正しい HEAD を見ていたか」を事後に追えるようにするのが目的

**この行の不在自体が信号になる**ことが要点で、agent の善意に依存しない。self-review は PR を持たず checkout もしないため対象外。

非レビュー出力を検出した reviewer は、**同一プロンプトで 1 回だけ auto-retry** する（複数同時検出時はまとめて並列 retry）。retry 出力も非レビュー出力なら、その reviewer の focus / angle を `missing_coverage` に識別子 `<focus>` を記録して続行する（**auto-retry 後も形式不正だった旨はレポート本文へ**）（欠損観点として扱い、フィルタを素通りさせない）。**retry も agent wave なので、retry 出力を回収した直後に `mark wave` を記録し直す**（後勝ち。打ち忘れると retry の実時間が `duration_synthesis_min` に混入し、「agent 非稼働が構造的に保証される区間」という定義が破れる — orchestration-measurement.md `## 14`）。「指摘ゼロ」を明示的に報告した妥当な出力（`### レビュー結果` を持ち問題なしと結論）は非レビュー出力ではないため retry 対象にしない。

### 部分失敗耐性

- **explorer**: 個別 explorer が失敗しても全体を中止しない。失敗した explorer を `missing_coverage` に識別子 `explorer:<focus>` として記録し（**エラー要旨はレポート本文へ**）、残った explorer の結果で続行する。該当 focus に依存する reviewer には、reviewer 起動時に「探索結果なし（失敗理由）」を明示して渡す
- **reviewer**: 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer を `missing_coverage` に識別子 `<focus>` として追記する（**angle・エラー要旨はレポート本文へ**）

### 最小保証の閾値

Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す（review では ExitWorktree してから終了する）。それ以外は欠損観点を明示しつつスコアリング step に進む。

### origin 主張の base 検算（レポート掲載前 / 常時実行 / v2.63.0・GitHub issue #124 (d)）

**「この diff による退行」と主張する指摘は、レポートに載せる前にオーケストレーターが base 側を確認する。**

```bash
# ローカルに同名ブランチが無い / 古い場合があるので origin 側を先に試す
# （triage-signals.sh も `origin/${BASE}...HEAD` → `${BASE}...HEAD` の 2 段を持つ）
git show "origin/<base>:<path>" || git show "<base>:<path>"
```

- **対象**: 指摘が `退行` / `regression` / 「変更前は X だった」/ `origin: this-diff` を load-bearing な根拠にしているもの。**severity と confidence に関わらず**掛ける（掲載前の 1 コマンドで決まる）
- **base に同経路があれば pre-existing** として `scoring-guide.md`「severity 調整ルール」の**「オーケストレーターの base 検算で pre-existing と判定した場合」**に従う（reviewer 申告があるケースの項ではない — あちらは「reviewer が既に下げているので追加調整しない」なので、**申告の無い skeptic 指摘に当てると何も起きない**）。diff が周辺の前提を変えて潜在問題を顕在化させた場合は pre-existing としない（この区別は従来どおり）
- **どちらのコマンドも解決できない場合は検算不能**として理由欄に `base 検算: 未実行（base ref 未解決）` を残す（silent に飛ばさない）
- **確認できたら理由欄に `base 検算: <結果>（git show <base>:<path>）` と残す**（reviewer 側の申告と二重に降格しないため。判別規約は `scoring-guide.md`）

**なぜオーケストレーター側にも要るか**: reviewer は `prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」で縛られているが、**冷や読み skeptic はこの規約を継承していない**（`prompts/recall-skeptic.md` が `reviewer-common.md` を参照するのは worktree セットアップと出力フォーマットの 2 点だけ）。実測（issue #124）では skeptic が「0 行取込でグリッドが全消えするのは本 diff 由来の退行」と主張し、オーケストレーターがそれを支持してユーザーに伝えたあと、反証レイヤーが `refuted`(axis: pre-existing) で覆した — **`git show <base>:<file>` 1 コマンドで決まる事実**だった。

**影響の非対称**: 反証レイヤーは effort ≥ high でしか走らないので、**low / medium では誰も検算せず誤帰属がそのまま報告される**。本検算は effort に依存しない決定的な手順なので、その穴を塞ぐ位置にある。

## 8. 観点カバレッジ検算（起動前検算 + 事後突合）

### 8a. 起動前検算（review Step 3.3・self-review Step 2.3 / 構成テーブル確定前・常時実行）

reviewer を起動する **前** に、Stage 1 の判定結果を機械的に検算する:

1. `triage-guide.md` の「reviewer の観点判定」表の各条件を、実際の diff シグナル（変更ファイルパス・diff 内文字列）に対して **メインコンテキストで再評価** する
2. **「条件を満たすのに構成に入っていない focus」** を検出する（例: `migrations/` 変更があるのに migration 不在、`.tsx` 変更があるのに ui-quality 不在、`package.json` 変更があるのに dependency 不在）
3. 検出した focus は **構成テーブルに追加してから確定する**（実効上限＝ effort 上限（triage-guide.md `## 7`）と規模キャップ（triage-guide.md `## 6.2`）の min に収まる範囲。**検算による追加で実効上限を超えてはならない** — 上限に達したら観点バンドル（triage-guide.md `## 7`）で既存 reviewer に相乗りさせ、それも不能なら `missing_coverage` に識別子 `<focus>` を記録する（**根拠の diff シグナルはレポート本文へ**））
4. **モード除外（review のみ）**: Stage 0 で `default-mode` 以外（`--emergency` / `doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode`）に確定した場合、モードの推奨構成が観点判定表より優先するため**構成追加は行わない**。検出した focus は `missing_coverage` に識別子 `<focus>` のみ記録する（**mode による意図的縮退である旨はレポート本文へ**）。self-review は `--focus` / `--exclude` 指定時にその範囲内でのみ検算する

### 8b. 事後突合（review Phase 5.7・self-review Phase 4.7 / logging のみ・agent 追加起動なし）

スコアリング直前に、8a で確定した構成テーブルと **実際に起動・完走した focus** をメインコンテキストで突合し、差分（未起動・失敗・非レビュー出力で欠損した focus）を `missing_coverage` に追記する。**本フェーズで agent は追加起動しない**（観点漏れの検出は 8a へ前倒し済み。目的はレポートの「欠損観点」セクションを確定させること）。`## 5` の部分失敗耐性による記録と重複してよい（dedup してレポートに出す）

> **失敗 reviewer の補完起動は v2.39.0 で廃止した**（直列 wave 削減とのトレードオフ）。失敗 focus は `missing_coverage` として欠損観点セクションに必ず明示され、必要ならユーザーが再実行を指示する。auto-retry（`## 5` の出力形式検証）は形式不正のみが対象でハード失敗は救わない — **この差は仕様であり見落としではない**。→ 経緯: `design-notes/orchestration-rationale.md`

