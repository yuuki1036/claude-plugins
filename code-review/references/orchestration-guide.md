# オーケストレーション実行ガイド（review / self-review 共通の実行フェーズ詳細）

review / self-review SKILL.md の各フェーズから参照される実行詳細の正本。SKILL.md 本文は高レベルワークフロー（Phase 一覧・各 Phase の目的と入出力・分岐条件）を保持し、具体的な手順・bash・失敗時の扱いは本ファイルに置く。エージェント構成の決定ロジック（起動条件・effort 適応・上限）は triage-guide.md、プロンプト本文は explorer-prompts.md / reviewer-prompts.md を参照。

## 0. skill 間の差分（本ファイル全体に適用）

| 項目 | review | self-review |
|---|---|---|
| agent の isolation | 全 agent を `isolation: "worktree"` で起動（PR ブランチの状態でファイルを読むため） | `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため） |
| PR 番号注入 | 必須（`## 1`） | 不要（PR を持たない） |
| diff の取得 | `gh pr diff`（GitHub 上の正しい差分） | `git diff`（base branch との差分 + 未コミット） |
| レビュー中止時 | ExitWorktree してから終了 | そのまま終了 |
| 動的ラウンドの Phase 番号 | 5.5 / 5.6 / 5.7 / 5.8 / 5.9 | 4.5 / 4.6 / 4.7 / 4.8 / 4.9 |

**同期起動の明示（両 skill・全 agent 起動に適用）**: explorer / reviewer / 追加 explorer / 再起動 reviewer / meta-reviewer / 冷や読み skeptic / 反証エージェントのすべてで、Agent call に `run_in_background: false` を必ず明示する。CC 2.1.198 で Agent tool の既定が background 実行に変わったため、省略するとオーケストレーターが結果を待たずに次フェーズへ進み、完了通知の遅れた agent の出力を取りこぼす（「反応が返ってこない agent」の正体）。本ガイドの `## 6`〜`## 10` の各起動手順にもこのルールが適用される。

**並列発行の明示（複数体を起動する全フェーズに適用 / GitHub issue #95）**: `run_in_background: false` は「1 体ずつ順に起動する」ことを意味**しない**。複数体を起動するフェーズでは、**同一アシスタントメッセージ内に対象フェーズの全 Agent call を並べて一括発行し、その 1 応答で全結果を待つ**。`run_in_background: false` は取りこぼし防止（結果を待つ）、同一メッセージ内の一括発行は並列性（フェーズの実時間を相内最長に収める）で、**2 つは直交する独立の要件**。1 体ずつ別メッセージで発行するとフェーズの実時間が相内最長ではなく全体の合計になる（実測: 12 体のレビューで 20.9 min で済むところが 72.9 min、約 3.5 倍。issue #95）。単体起動のフェーズ（meta-reviewer / 冷や読み skeptic）には適用対象がない。

## 1. PR 番号注入（review のみ / agent 起動時に必須）

review skill が worktree で起動する **すべての agent**（explorer / reviewer / 追加 explorer / 再起動 reviewer / meta-reviewer / skeptic / 反証エージェント）に適用する。

agent prompt の冒頭に「PR 番号: `<PR_NUMBER>` / 対象 head ref: `<headRefName>`」を必ず明記し、explorer-prompts.md / reviewer-prompts.md 共通指示の `{{PR_NUMBER}}` と `{{HEAD_REF}}` プレースホルダを実数値に置換する。`isolation: "worktree"` の子 worktree は親 branch を継承せず origin/default-branch から派生するため、checkout 指示を欠かすと PR の変更を観測できず偽陽性を量産する（GitHub issue #56）。`{{HEAD_REF}}` 注入により、EnterWorktree 済みの親 worktree と二重 checkout になるケースを子 worktree 側でスキップできる（GitHub issue #69）。

```bash
# PR_NUMBER は Step 1 で取得済み（gh pr view --json number -q .number で再取得可能）
PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null || echo "<番号>")
```

## 2. Issue ファイル必読フロー（review Step 1 の任意フロー / issue-workflow 併用時）

PR head / base branch 名から Issue ID を抽出し、ローカルの Issue ファイルがあれば agent prompt に同梱する。仕様・受入条件・設計判断を踏まえた spec-compliance 判定の精度が上がる（GitHub issue #43）。

```bash
# 1. branch 名から [A-Z]+-\d+ パターンで Issue ID を抽出
HEAD_REF=$(gh pr view <PR番号> --json headRefName -q .headRefName)
BASE_REF=$(gh pr view <PR番号> --json baseRefName -q .baseRefName)
ISSUE_IDS=$(echo "$HEAD_REF $BASE_REF" | grep -oE '[A-Z]+-[0-9]+' | sort -u)

# 2. ローカル Issue ファイル探索（local / linear 両 backend の dir を走査）
for ID in $ISSUE_IDS; do
  find .claude/linear -name "*.md" 2>/dev/null | xargs grep -l "$ID" 2>/dev/null
  find .claude/indie -name "*.md" 2>/dev/null | xargs grep -l "$ID" 2>/dev/null
done | sort -u
```

- ヒットしたファイルを Read で読み込み、内容を spec-compliance reviewer の prompt に `## Issue ファイル` セクションとして同梱する（reviewer-prompts.md の `## 2. セッションコンテキスト注入テンプレート` と同じ要領）
- Issue 本文内に「親 Issue: [FOO-1234](...)」「Parent: FOO-1234」のような親リンクがあれば **1 段だけ追跡** （深い再帰は禁止：トークン爆発防止）
- Issue ID が抽出できない / ファイルが存在しない場合は本フローをスキップ（best-effort）
- `.claude/linear/` と `.claude/indie/` 双方が無いリポジトリでは Glob が空配列を返すだけで no-op（後方互換）

## 3. PR コンテキストブロックの構造（review Step 2.5 の参考）

`fetch-pr-context.sh` のスクリプト出力の構造（参考）:

```
## PR コンテキスト

### PR 情報
- #<番号> <タイトル>
- 著者: @<author>
- Base → Head: <base> → <head>
- State: <state>
- URL: <url>

### PR 説明（著者が明示したスコープ・意図）
<body 全文。空なら「（空）」>

### Issue コメント（PR 全体への議論）
- [@user, YYYY-MM-DD] body
- ...

### レビューサマリ
- [@reviewer, STATE, YYYY-MM-DD] body
- ...

### 行単位レビューコメント（過去の指摘）
- [#id] [@reviewer, path:line] body
  - 返信 [#親id への返信] [@user] body
- ...
```

データが無い項目は `fetch-pr-context.sh` が「（なし）」を出力する。

## 4. AGENTS.md 階層動的選択（reviewer 起動前 / review Step 4.9・self-review Step 3.9）

変更ファイルパスから対応する `{dir}/AGENTS.md` を Bash で探索し、該当層だけを reviewer プロンプトに同梱する。リポジトリ全体の AGENTS.md / CLAUDE.md を毎回フルロードせず、変更があった層のみ拾うことで reviewer 入力 token を典型 30〜50% 削減する。

```bash
# 変更ファイルから親ディレクトリを抽出
# 変更ファイル一覧の取得は review: `git diff <base>...HEAD --name-only` / self-review: `git diff "${BASE}..HEAD" --name-only`
git diff "${BASE}..HEAD" --name-only | xargs -n1 dirname 2>/dev/null | sort -u | while read dir; do
  # 当該ディレクトリから root まで遡って AGENTS.md / CLAUDE.md を探索
  while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
    [ -f "$dir/AGENTS.md" ] && echo "$dir/AGENTS.md"
    [ -f "$dir/CLAUDE.md" ] && echo "$dir/CLAUDE.md"
    dir=$(dirname "$dir")
  done
done | sort -u
```

ヒットしたファイルのみ Read で読み込み、各 reviewer のプロンプトに `## 該当層の AGENTS.md / CLAUDE.md` セクションとして注入する。AGENTS.md が無いリポジトリでは探索結果が空になるだけで no-op（後方互換）。

## 5. reviewer 起動の共通詳細

### effort 設計意図

reviewer の effort は実行時 `${CLAUDE_EFFORT}` に連動させる: **low/medium/high（既定）→ `high` / xhigh・max（明示 escalation）→ `xhigh`**。reviewer は**全レビューで必ず走り、体数も最大（典型 2〜10 体。`## 7` の最小保証 2 体 〜 上限 10 体）のため、レビュー総コストの最大項**であり、ここが最大のコストレバー（`max`→`xhigh` に続く 2 段目の引き下げ。唯一ではない。下記の変動費も参照）。既定パスを `high` に引き下げた根拠は 2 つ: ① Opus 5 はコードレビュー・バグ発見が低 effort でも精度が落ちにくい（公式モデルガイダンス）② reviewer 単発の深さには依存しない補償層（反証 / skeptic / meta-reviewer、いずれも `max` 据え置き）がある。escalation 時は従来どおり `xhigh` で深掘りする。効果は `review:completed` メトリクス（blocker/critical 件数・findings 推移）で監視し、悪化が観測されたら既定を `xhigh` に戻す。

> **体数の下限に注意**: 「常に 2 体以上」は不変条件では**ない**。`doc-review-mode` は 1〜2 体、`skip-mode` は `spec-compliance` のみ 1 体（triage-guide `## 2.5` のモード構成は Stage 2 の上限・最小保証より**優先**する）、self-review の `--focus` 指定時は最小保証すら起動しない。他所でこの不変条件を援用しないこと。

オーケストレーター（skill frontmatter）は `high`（＝ Opus 5 の既定 effort に揃える。Opus 4.8 と同じ既定値なので旧世代でも同運用）。これにより effort ゲート付きの独立レイヤー（meta-reviewer / 冷や読み skeptic）は既定で不発とし、high-risk 変更をレビューしたい時だけ `/self-review` を `xhigh`/`max` で明示起動して escalation する運用にする。

**独立検証レイヤー（meta-reviewer / 冷や読み skeptic / 反証エージェント）は `max` 据え置き**。ただし据え置きの根拠は「体数が小さいから」ではなく（下表のとおり反証は体数が指摘数に比例する）、**誤判定コストの非対称性**にある:

| 層 | 体数 | 既定 high で起動するか |
|---|---|---|
| meta-reviewer | 1 体・1 round（triage-guide `## 8`） | しない（xhigh/max 起点） |
| 冷や読み skeptic | PR あたり 1 体・1 round（`## 8.5`） | しない（xhigh/max 起点） |
| 反証エージェント | **指摘ごと 1 体**（`## 9`）＝指摘数に比例 | **する**（非対称ゾーンに限定） |

- **反証の誤却下は指摘を落とす**（消えるのは MAJOR / MINOR のみ。BLOCKER / CRITICAL は refuted でも消さず係争注記が scoring-guide の不変条件で機械保証される）
- **skeptic の見落としは recall 補強そのものを無効化する**（足す係が足さなければ層ごと無意味）

**下げるのは全レビューで必ず走る常時レイヤー、据え置くのは誤判定コストが非対称な検証レイヤー**という切り分けを意図的に取る。なお**次点の変動費は反証（既定パスで opus×`max`×指摘数）と specialist（reviewer 枠とは別枠で上限 6 体。triage-guide `## 7`）**であり、コストが再び問題化したらこの 2 つが次の検討対象になる。

### diff-first 原則

各エージェントには diff の出力（review: `gh pr diff` / self-review: `git diff`）を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

### 出力形式の検証と auto-retry（GitHub issue #69）

各 reviewer の出力が「レビュー結果」として妥当か機械的に検証する。以下のいずれも欠く出力は **非レビュー出力**（空応答・system-reminder / skill 案内の断片・tool_use ゼロでの早期終了等）とみなす:

- `### レビュー結果` 見出し（または `#### 指摘事項` / `#### 総括` のいずれか）
- 指摘が 1 件以上ある場合、`[confidence: XX]` と `[severity: ...]` タグを含む行が存在する

非レビュー出力を検出した reviewer は、**同一プロンプトで 1 回だけ auto-retry** する（複数同時検出時はまとめて並列 retry）。retry 出力も非レビュー出力なら、その reviewer の focus / angle を `missing_coverage` に「非レビュー出力（auto-retry 後も形式不正）」として記録して続行する（欠損観点として扱い、フィルタを素通りさせない）。「指摘ゼロ」を明示的に報告した妥当な出力（`### レビュー結果` を持ち問題なしと結論）は非レビュー出力ではないため retry 対象にしない。

### 部分失敗耐性

- **explorer**: 個別 explorer が失敗しても全体を中止しない。失敗した explorer の type / focus / エラー要旨を `missing_coverage` リストに記録し、残った explorer の結果で続行する。該当 focus に依存する reviewer には、reviewer 起動時に「探索結果なし（失敗理由）」を明示して渡す
- **reviewer**: 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer の focus / angle / エラー要旨を `missing_coverage` リストに追記する

### 最小保証の閾値

Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す（review では ExitWorktree してから終了する）。それ以外は欠損観点を明示しつつスコアリング step に進む。

## 6. Adaptive deepening 実行手順（追加 explorer ラウンド / review Phase 5.5・self-review Phase 4.5）

1. 全 reviewer 出力をパースし、`## unmet_information` セクションを集約する
2. 集約結果から **最大 3 件** の追加探索ターゲットを選ぶ（多すぎる場合は BLOCKER 候補に関わる unmet を優先）
3. explorer-prompts.md の `re-explore` テンプレートで追加 explorer を `model: sonnet` で並列起動する（全 call を同一メッセージ内で一括発行する — `## 0` 並列発行の明示）
   - 各 explorer に対応する unmet_information（focus, target, why, related_finding）を指示として渡す
   - isolation は `## 0` に従う（review は `isolation: "worktree"`（PR ブランチ）、self-review は使用しない）
   - **PR 番号注入（review のみ・必須）**: `## 1` に従い prompt 冒頭に PR_NUMBER / head ref を明記し `{{PR_NUMBER}}` を置換（issue #56）
4. 追加 explorer 完了後、unmet を申告した reviewer のみ（最大 3 体）を `model: opus`、**初回 reviewer と同じ effort** で再起動する（`## 5` の連動表に従う）
   - 再起動 reviewer には初回指摘 + 追加 explorer 結果を context として渡し、「初回 confidence を再評価せよ」と指示
   - 再起動 reviewer の出力は **初回出力を置換**（dedup のため）
   - **PR 番号注入（review のみ・必須）**: `## 1` に従う
5. レポートに「Round 2 trigger: <reason>」を記録（レポート出力 step = review Step 7 / self-review Step 6 で出力）

**失敗時**: 追加 explorer / 再起動 reviewer が失敗した場合は初回結果のままで続行（missing_coverage には追記しない、Round 2 は best-effort）

## 7. Meta-reviewer 実行手順（review Phase 5.6・self-review Phase 4.6）

1. reviewer-prompts.md の `## 6. Meta-reviewer テンプレート` を使用
2. meta-reviewer agent を 1 体、`model: opus`, `effort: max` で起動
   - 入力: diff、全 reviewer の指摘リスト（フィルタ前）、起動された focus 一覧、explorer 結果
   - isolation は `## 0` に従う。**PR 番号注入（review のみ・必須）**: `## 1` に従う
3. meta-reviewer の出力（追加指摘）を既存指摘に統合
   - 重複は dedup（同一ファイル ±5 行 + 類似内容）
   - meta-reviewer の指摘も通常のスコアリング・フィルタリング対象

**失敗時**: meta-reviewer が失敗した場合は missing_coverage に `meta-reviewer: <failure reason>` を追記して続行

## 8. 観点カバレッジ・セルフチェック手順（review Phase 5.7・self-review Phase 4.7）

1. `triage-guide.md` の「reviewer の観点判定」表の各条件を、実際の diff シグナル（変更ファイルパス・diff 内文字列）に対して **メインコンテキストで再評価** する
2. **「条件を満たすのに起動されなかった focus」** を検出する（例: `migrations/` 変更があるのに migration 不在、`.tsx` 変更があるのに ui-quality 不在、`package.json` 変更があるのに dependency 不在）
3. 検出した観点漏れは `missing_coverage` に「観点未起動: <focus>（diff シグナル: <根拠>）」として追記する
4. effort が `high` 以上 かつ 追加 1 体で補える観点なら、その focus の reviewer を 1 体だけ `model: opus`、**初回 reviewer と同じ effort**（`## 5` の連動表）で追加起動して結果をスコアリング step に合流させてよい（任意・best-effort。失敗しても missing_coverage 記載のまま続行）。**effort を揃えるのは、非対称な深さの指摘が同じ confidence 軸で合流するのを避けるため**

## 9. 冷や読み skeptic 実行手順（review Phase 5.8・self-review Phase 4.8）

1. **surface 判定**: 変更 diff に対し triage-guide.md `## 8.5` の判定を行う。DB 書込（`INSERT`/`UPDATE`/`DELETE` の生 SQL または ORM 書込 API `.create(`/`.update(`/`.save(`/`.upsert(` 等）/ 金銭・数量 numeric 演算 / 認可・認証、いずれかの正規表現ヒット、**または** reviewer が `[surface:high-risk]` フラグを返した場合に high-risk surface と判定する。review では **PR 自己申告 D1-High** も OR 判定に含める（self-review は PR を持たないため正規表現 + reviewer フラグのみ）
2. reviewer-prompts.md の `## 8 冷や読み skeptic テンプレート` を使用し、skeptic agent を **1 体**、`model: opus`, `effort: max` で起動する（isolation は `## 0` に従う）
   - **findings / reviewer の推論は渡さない**（独立性の核）。diff と最小 focus、base ref のみ渡す
   - **PR 番号注入（review のみ・必須）**: `## 1` に従う
3. skeptic の指摘（`[recall-skeptic]` タグ付き）を既存指摘に統合。重複は dedup（同一ファイル ±5 行 + 類似内容）。skeptic の指摘も通常のスコアリング・報告マトリクス・**反証レイヤーの対象**に含める
   - **dedup 時はタグを残す側へ引き継ぐ**（どちらの本文を採用するかに関わらず）。reviewer 指摘と重複したときにタグごと捨てると skeptic の寄与が不可視になり過少計上される。**独立の skeptic が同じ問題に到達した事実は、reviewer が先に見つけていても失われない**
   - ただし**タグは 2 種に分ける**。重複の有無で意味が正反対になるため、同一カウンタに載せてはならない:
     - `[recall-skeptic]` — **skeptic 単独由来**（dedup で reviewer 指摘と重複しなかった）。fleet 共通盲点を実際に破った事例＝ skeptic の価値そのもの
     - `[recall-skeptic:dup]` — **重複 survivor**（reviewer も同じ問題に到達していた）。skeptic が独立に到達した記録としては残すが、**盲点でなかった事例なので recall の足し前はゼロ**
   - **`[recall-skeptic:dup]` を価値率の分子に混ぜない**。skeptic は generalist 一頭で reviewer 最大 10 体と同じ diff を読むため**重複は常態**であり、混ぜると価値率が 100% に張り付いて「findings_added=0 なら縮小」の分岐が原理的に発火しなくなる（過少計上の裏返しで、過大計上という別の壊れ方になる）
   - タグは**レポート本文の指摘行まで持ち越す**（Step 7 / Step 6 のレポート契約。publish 時に `findings_added` / `findings_overlap` を数える唯一の根拠）

**失敗時 / スキップ時**: skeptic が失敗 / タイムアウトした場合は `missing_coverage` に `recall-skeptic: <failure reason>` を追記して続行する。スキップ条件（effort / config / scope・emergency）に該当した場合でも、surface 判定（正規表現・grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と独立に必ず実施する。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・スキップのいずれでもレポート（review Step 7 / self-review Step 6 の「動的ラウンド」行）に必ず出す**（silent skip で偽の安心を防ぐ・issue #85）

## 10. 反証レイヤー実行手順（review Phase 5.9・self-review Phase 4.9）

1. triage-guide.md `## 9 反証レイヤー` の選定ルールで対象指摘を選ぶ（high: 非対称ゾーン BLOCKER 60-94 / CRITICAL 80-94、xhigh/max: 報告ゾーン全体 + MAJOR）。**specialist 由来の指摘は全 effort で除外**
2. 対象指摘ごとに reviewer-prompts.md `## 7 Adversarial-verify テンプレート` で反証エージェントを `model: opus`, `effort: max` で並列起動する（isolation は `## 0` に従う。全 call を同一メッセージ内で一括発行する — `## 0` 並列発行の明示）
   - 指摘の主張（severity / confidence / file:line / 内容）のみ渡し、**reviewer の理由文は渡さない**（アンカリング防止）
   - **PR 番号注入（review のみ・必須）**: `## 1` に従う
   - `pre-existing` / `intended` 鮮度の git 判定（`git show <base>:<file>` / `git blame`）を反証エージェントに許可する
3. 各 verdict（refuted / confirmed / uncertain / severity-inflated）を収集し、スコアリング step に渡す
4. レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（レポート出力 step で出力）

**失敗時**: 反証エージェントが失敗した指摘は verdict なし（= 反証スキップ）として元の confidence / severity のまま続行する（best-effort、missing_coverage には記録しない）

## 11. Vault 照合手順（self-review Step 1.5 / 過去の指摘・落とし穴の retrieval）

**利用可否の検出（未導入なら skip / 後方互換）**:

```bash
# kvault コマンド または /vault-recall skill のいずれかが使えれば実行
command -v kvault >/dev/null 2>&1 && echo "kvault: available"
```

`kvault` も `/vault-recall` skill も使えない環境では本ステップ全体を skip する（vault 未導入リポジトリでは no-op）。

**照合手順**:

1. Step 1 で収集した変更ファイルのパス・主要な識別子（関数名・型名・コンポーネント名）・技術語をクエリ語にする
2. 代表的なクエリを 1〜3 個 `kvault recall "<query>"` で実行する（`/vault-recall` skill が使える場合はそちら経由でも可）。出力は `results[]`（`similarity` / `title` / `excerpt` / `path` / `tags`）の JSON
3. 各結果の `similarity` と、上位ヒットと下位ヒットの **gap**（スコア差）で関連度を判断する。上位が明確に分離して高 similarity（目安: 上位 `similarity` ≥ 50 かつ次点との gap が明確）なら関連ありとみなす。全体が低 similarity で団子状なら関連なしと判断して注入しない（ノイズ注入を避ける）
4. 関連ありと判断した知見（`title` + `excerpt` + `path`）を reviewer 起動 step（self-review Step 4）の各 reviewer プロンプトに `## Vault prior findings（過去の関連指摘・落とし穴）` セクションとして注入する

**注意**:
- `--embed` 呼び出し（feature-dev Phase 6 等）でも本ステップは動作する（呼び出し元が retrieval 基盤を共有する前提）
- vault 照合は best-effort。`kvault` 実行が失敗・タイムアウトしても `missing_coverage` には記録せず skip して続行する（レビュー本体をブロックしない）

## 12. 訂正の伝播前ガード（self-review Step 7 / over-correction 防止 / GitHub issue #71）

findings をコード/文書本文に**反映する前に**、その修正が依拠する load-bearing な事実主張を一次ソースで再確認する。修正を「探す」段だけでなく「書く」段にもツール接地を効かせる（reviewer-prompts.md「事実主張のツール接地」の対）。

- **repo で確認できる主張**(コード挙動・型・呼び出し関係）→ Read/Grep で現物を確認してから書き換える。記憶や推測で本文を直さない
- **repo で確認できない主張**（DB/本番の現状態・外部数値・運用設定・「本番では解消済み」等）→ 「事実」として断定的に書かない。正本（spec / PR / Issue / ADR / コミットメッセージ）で裏が取れない限り **「要確認（典拠=X）」マーカーを残す**。reviewer 指摘が `[unverified: ...]` 付きなら、その不確実性を修正後の本文にも引き継ぐ
- **暫定入力を確定として伝播しない**: ユーザーや reviewer の推測的な言及（「〜かも」「たぶん」「〜のはず」）を、確定した事実として複数箇所に展開しない。確定させるには一次ソースを引くこと
- **1 箇所先行確認 → 確証後に展開**: 同じ訂正を複数箇所に広げる場合、まず 1 箇所で正本確認し、確証が取れてから他箇所へ展開する（未検証の訂正を一括で 5 箇所に広げて全部誤り、という失敗を防ぐ）
- **複数観点の独立一致は高信頼**: 同一箇所を複数の独立した reviewer 観点が指している場合は、相互の誤検出が打ち消されるため高信頼として扱ってよい
