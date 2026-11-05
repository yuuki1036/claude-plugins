---
id: 20261105-reviewer-plan-script
title: reviewer 構成を script で決めて起動前に検算する（#351）
status: draft
phase: current
last-validated: 2026-11-05
supersedes: []
superseded-by: null
issue: "#351"
spec: null
adrs: []
tags: [code-review, self-review, review, triage, reviewer-plan, spec-compliance]
---

# reviewer 構成を script で決めて起動前に検算する（#351）

## TL;DR

reviewer の構成（実効上限・単独で起動する観点・束ね・落とした観点とその理由）を、オーケストレーターが triage-guide を読んで数えるのをやめ、`code-review/scripts/plan-reviewers.sh plan` に決めさせる。起動前検算（orchestration-guide `### 8a`）では、確定したテーブルを `plan-reviewers.sh check` に流し、規則に反すれば exit 1 で止める。仕様ソースの有無は script が自分で検出し、spec-compliance を LLM の自己申告で決めない。

## 背景 / 課題

GitHub #351。self-review が triage-guide の reviewer 構成の規則を守らず、仕様ソースがあるのに spec-compliance を起動しなかった。

- effort high の reviewer 上限は 6（triage-guide `## 7`）なのに、5 体で構成した
- 「単独維持の観点が上限に収まらないときの順」（最小保証 2 体 → 仕様ソースがあれば spec-compliance → security → …、triage-guide `## 4` 末尾）に反し、security を起動して spec-compliance を落とした
- 規模は large で規模キャップは無かったのに、レポートに「規模の上限で未起動」と書いた
- 起動前検算（`### 8a`）はこの構成を止めなかった

同型の過去 Issue は #295（pattern-consistency が起動されない）。手順の文書を直しても、構成を LLM が決める限り再発する。

## ゴール / 非ゴール

- **ゴール**: 構成を script が決め、オーケストレーターはその結果に従う。起動前に「仕様ソースがあるのに spec-compliance が無い」「上限が effort 表と違う」構成を機械的に止める。レポートの未起動の理由（規模・effort・上限超過）を script の出力から写す
- **非ゴール**: specialist / explorer の構成（上限値だけは表示する。構成の規則が別系統で、今回の不具合と無関係）、照合元の拡張（#352）、整合スキル（#365）

## 確定した前提

- 上限の正本は triage-guide `## 7`（reviewer 4 / 6 / 10）と `## 6.2`（small 3 / medium 5 / large 上限なし）。数値は self-review / review の SKILL.md の 2 本に複製されているが、一致を見るテストは無い
- 仕様ソースを検出している script は無い（triage-signals.sh は `## issue-ids` だけ）。session-context の branch 一致・Issue ファイル・`--spec` の判定は LLM の手作業（self-review SKILL.md の Step 1、review SKILL.md のコンテキスト収集）
- `### 8a` は LLM がメインコンテキストで再評価するだけで、機械的に止める処理は無い
- triage-guide `### 6.5` は feature-dev が SSoT pin しているので、今回は触らない
- 構成まで script が決める（2026-11-05 決定）。上限と必須観点だけを script に持たせる案は、束ねの数え違いが残るので採らない
- review（default-mode のみ）と self-review の両方に入れる

## 採用案

### ファイル

- 新規 `code-review/scripts/plan-reviewers.sh`（bash の入口。一時ファイルのパス・作業ツリー・メインのチェックアウト・現ブランチを解決して python に渡す）
- 新規 `code-review/scripts/lib/reviewer_plan.py`（定数と純関数 `compute_plan` / `check_table`、仕様ソースの検出、plan ファイルの読み書き）
- `lib/review-paths.sh` に一時ファイルの種別 `plan` を足す。triage-signals.sh の冒頭（前回の残骸の掃除）と publish の後の掃除で消す
- self-review / review の SKILL.md: 数値の複製を plan の呼び出しに置き換え、`### 8a` の後に check を足し、レポートの未起動の理由を plan の行から写す
- triage-guide / orchestration-guide `### 8a`: 規則を script が適用する旨の注記

### plan

入力: `--effort`・`--size-tier`（`--since` の回は delta の帯）・`--activated`（Stage 1 で起動条件を満たした観点）・`--prior`（前回の対象の観点）・`--delta`・`--focus` / `--exclude`・`--spec <path>`・`--spec-source pr-issue:#N | knowledge:<path>`。

- 仕様ソースのうち、session-context（frontmatter の `branch` が現ブランチと一致）・ブランチ名と一致した session-context の `issue_id` の Issue ID に対応する Issue ファイル（`.claude/{indie,linear}/*/issues/<ID>.md`。worktree ならメインのチェックアウト側も見る）・`--spec` の実在は script が検出する
- spec-compliance は `--activated` に入れさせない（入っていたら exit 2）。仕様ソースだけで決める
- 出力は key=value（`effort_cap` / `size_cap` / `reviewer_cap` / `cap_source` ほか）と、`reviewer` / `dropped` / `spec_source` などの TSV 行。plan はセッションの一時ファイルにも保存する

手順:

1. 候補の観点を集める（Stage 1 の観点 + 最小保証 2 体 + 仕様ソースがあれば spec-compliance + 前回の対象）
2. 上限 R = min(effort 上限, 規模キャップ)。`--focus` / `--exclude` の回は規模キャップを掛けない
3. 単独維持の観点を順（bug-detection → claude-md-compliance → spec-compliance → security → layer-responsibility）に 1 体ずつ取る。low / medium では layer-responsibility の位置に設計バンドルを置く
4. 前回の対象（`--delta` の回）は規模キャップの外の専任にする。effort 上限を超える分は相乗りにする
5. 残りの観点を固定の近さの順（`ADJACENCY`）に並べ、空き枠へ均等に割る（1 体 3 観点まで）
6. 落とした理由は、規模キャップを外して割り当て直して入るなら `size-cap`、それでも入らない単独維持の観点は `effort-cap`、それ以外は `overflow`。large には規模キャップが無いので、`size-cap` は構造上出ない

### check

確定したテーブル（plan と同じ形の行）を stdin で受け、保存した plan と突き合わせる。止める規則: `over-cap` / `min-guarantee` / `spec-missing` / `solo-bundled` / `over-bundled` / `unaccounted` / `redundant-not-allowed`（high 以下で同じ観点が 2 行）/ `unknown-focus` / `not-in-plan`（plan の候補に無い観点）/ `wrong-reason`（落とした理由が plan と違う）/ `dropped-revived`（plan が落とした観点を起こした）/ `bad-prior`（prior の行が plan の前回の対象の単独行と違う）/ `bad-piggyback`（plan に無い相乗り）/ `not-plan-row`（前回の対象の専任を除く行の観点の組が plan の行と 1 対 1 で一致しない。束ね直して体数を変えた構成を止める）。kind 列と相乗りは LLM が書くので、plan と同じものだけを認める（認めないと落とした観点を prior の行や相乗りで書き足せる）。exit 0 = ok / 1 = NG / 2 = plan が無い・入力の形が違う。

## 検討した代替案

| 観点 | 案 A: 構成まで script（採用） | 案 B: 上限と必須だけ script | 案 C: PreToolUse hook で起動を止める |
|------|------------|------|------|
| 数え直しの余地 | 無い | 束ねの組み方が LLM に残る | 起動時点で止まるが、構成の決定は LLM |
| 変更量 | 中 | 小 | 大 |
| 判定の述語 | 集合演算と if で決まる | 同左 | reviewer の wave かを transcript から決める必要がある |

- 案 B: 束ねの数え違い（吸収容量の誤算・単独維持の観点の束ね）が残るので採らない（2026-11-05 決定）
- 案 C: 止める述語が決定的に書けないので採らない

## 設計判断ログ

- [local] 束ねの塊は均等に割る（先頭から 3 個ずつ詰めない）。attention の希釈を最小にするため
- [local] 単独維持でない観点があふれたら、`ADJACENCY` の後ろから落とす（triage-guide に順の規定が無い）
- [local] low / medium の設計バンドルは security の直後に置く
- [local] `--delta` で前回の対象と spec-compliance が枠を取り合うときは、単独維持を先に取る
- [local] `--focus` の回も effort 上限は掛ける（規模キャップだけを外す）
- [local] size_tier=unknown は規模キャップを掛けず、WARN を出す（small に潰すと大きな diff が最小構成で黙って処理される）
- [local] `--since` の回の前回の対象は、単独維持の観点も含めて規模キャップの枠を使わない専任（prior の行）にする。単独維持の観点は単独維持の順の位置で取り、low / medium の layer-responsibility も設計バンドルに入れない（相乗りや束ねにすると修正の確認が他の観点の片手間になる）
- [local] delta が空の回は plan / check を使わない（`### 6.5` の「前回の対象の reviewer だけ」を、最小保証を必ず足す plan では表せない）
- [local] check は保存した plan と突き合わせる。check のときに引数を渡し直させない（check だけ別の引数で通す経路を作らない）

## 未解決事項 (open)

- **plan / check を呼ばない経路**: SKILL.md の指示だけでは守られない回が残る。(a) publish で plan ファイルが無い default-mode の回に `measurement_gaps` へ記録する（観測のみ・小さい）/ (b) 呼び出しを強制する hook（述語が難しい）。有力は (a)。確定タイミング: この変更のマージ後、別 Issue で
- **pr-issue / knowledge の渡し忘れ**: 呼び出し側の申告に残る。plan が `gh pr view --json closingIssuesReferences` を自分で引く案は、gh 依存を plan に持ち込むので今回は採らない。確定タイミング: (a) の観測で渡し忘れが見えたら

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位: 同じセッションの feature-dev（CP-9 / #351）で続けて実装する。順序:
   1. `review-paths.sh` に `plan` 種別、triage-signals.sh 冒頭と publish の後の掃除
   2. lib の定数と、triage-guide の表との突き合わせテスト
   3. `compute_plan` と単体テスト
   4. `check_table` と単体テスト
   5. `plan-reviewers.sh` と CLI テスト
   6. triage-guide / orchestration-guide の注記
   7. self-review / review SKILL.md の置き換え
   8. CHANGELOG（vNEXT）→ `bump-version.sh code-review --sync` → `run-tests.py`
2. 検証方法: `.claude-plugin/scripts/tests/test_code_review_reviewer_plan.py`（表との突き合わせ・#351 の回帰・帯と effort の境界・check の規則ごとに鳴る場合と黙る場合の対・CLI での仕様ソースの検出）と self-review
3. 実装完了時の doc 更新手順: frontmatter の `phase: target` → `current`、`last-validated` を更新。実装と乖離した箇所は追記、方式ごと変わったら supersede

## 関連

- 関連 Issue: #351（同型: #295）
- 関連 spec: なし
- 関連 ADR: なし
- 関連 design doc: なし
