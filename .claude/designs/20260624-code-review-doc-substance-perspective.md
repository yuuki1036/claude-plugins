---
id: 20260624-code-review-doc-substance-perspective
title: code-review への doc-substance（内容妥当性）レビュー観点の追加
status: approved
phase: current
last-validated: 2026-06-24
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: []
tags: [code-review, doc-review, perspective, triage, scoring, grounding]
---

# code-review への doc-substance（内容妥当性）レビュー観点の追加

> **実装済み（code-review 2.27.0、phase: current）**: reviewer-prompts.md `## 3`（doc-substance Focus）/ `## 7`（反証軸 doc 読み替え）/ triage-guide.md（doc-review-mode 行・観点判定表 doc-substance 行・「doc-substance の起動（重要度ゲート）」節）/ scoring-guide.md（explorer +10 流用・≤40 クランプ拡張・git blame ガード付き CRITICAL 昇格）/ plugin.json 2.27.0 + CHANGELOG + marketplace + INDEX 同期。SKILL は triage/reviewer-prompts/scoring に委譲のため本体編集なし。静的検証（validate-ssot / validate_plugin_quality / claude plugin validate）通過。**runtime smoke 実走済み（8 シナリオ全 PASS、独立 reviewer agent ×5 + 決定的トリアージ/scoring）**。smoke 設計・実走で実装の穴を 2 件修正: ① 昇格ガードが「コードが古い→非昇格」で安定コードへの誤記まで殺していた→「別経路/同時変更/intended でのみ非昇格」に修正、② doc-review-mode が doc-substance を無条件併走させ typo PR でも起動→両経路で起動条件を共通化。残: 実 PR での「実質 prose 10 行」閾値・design-review 内挿軽量版のチューニング（open 参照）。
>
> 2026-06-24 design-review（minimal / pragmatic / risk 3 視点）の findings を反映済み。主な修正: ゲート指標を「diff 行数比率」→「変更ファイル数比率」に訂正（BLOCKER）/ 反証レイヤーは「specialist 以外全て」でなく effort 別の非対称ゾーン限定だと訂正し偽陽性抑制戦略を再設計（BLOCKER）/ 裏取り報酬を新設 +15 から既存 explorer 裏付け +10 に変更 / 5 種別サブレンズを廃し単一プロンプト化（種別は委譲判定のみに残す）/ effort 別起動制御を追加 / 裏取り CRITICAL 昇格に git blame 検算ガード / grounding explorer の読み取り対象を diff 変更 doc の参照コード ∩ 実在パスに限定 / 観点判定表への登録を実装ブリッジに明記 / userConfig トグルを廃止。

## TL;DR

review 系スキルは docs を含む PR で内容の妥当性をレビューできていない。`doc-substance`（内容妥当性）観点を既存 perspective カタログに追加し、変更ファイル数比率でなく **doc の意味的重要度**で起動・grounding explorer で主張をコード裏取り・裏取り証拠で severity 昇格させることで、「diff の整合性」から「書かれた中身が現実と合い・筋が通り・有用か」までを既存構造の拡張だけでカバーする。

## 背景 / 課題

review 系スキル（code-review / self-review）は docs を含む PR で、書かれている内容の本質的な妥当性をレビューできていない。原因は 2 つの失敗モードに分解できる。

**① docs 主体 PR（`*.md` が変更ファイル数の ≥ 80%）— 設計的に内容を捨てている**
`triage-guide.md:40` の `doc-review-mode` が発火すると、観点が「リンク健全性 / コード片の SQL 安全性 / 構造整合性」の 1-2 reviewer に絞られる。最小保証の bug-detection も「リンク切れ＝bug 相当」に読み替えられるだけで、**主張が正しいか・妥当か・有用かを見る観点が定義上存在しない**。トークン削減のための分岐が、内容レビューを構造的に殺している。ADR 1 件だけの PR は `*.md` 比率 100% でこのモードに入るため、最も内容レビューが要る変更が最も内容を見られない。

**② 混在 PR（`*.md` が変更ファイル数の < 80%）— prose が誰にも見られない**
比率閾値未満の PR は `default-mode`（`triage-guide.md:44`）に落ち、Stage 1 の reviewer 観点判定表（`triage-guide.md:98-115`）に入る。だがこの 18 観点はすべてコード向け（bug / security / type / api …）で、prose を担当する観点がない。コード多数 + `CLAUDE.md` / ADR 1 ファイルのような PR は `*.md` ファイル比率が小さく default-mode 入りし、**意味的に重要な doc がコード観点の巻き添えレビューしか受けない**。`reviewer-prompts.md:366-386` の `comment-accuracy` はインラインコメントだけ「コメント⇔コード一致」を見るが、doc ファイル本文は対象外。

> ゲートが **変更ファイル数比率**（`triage-guide.md:63`、巨大 lockfile に引っ張られないための仕様）で測られるため、ファイル数では小さいが意味的に重要な doc が取りこぼされる。重要度とファイル数比率が無関係なのが構造的な穴。

リポジトリ全体を見ても、汎用 docs の「内容が正しいか」をレビューする観点は存在しない。`design-doc:design-review` の 4 視点はコード裏取りで内容妥当性を見る良い型を持つが、(a) 別スキルの手動起動、(b) 実装前 design doc 専用に最適化されており、code-review の流れに乗らない。`writing-polish` は語句・トーンのみ、`doc-freshness` は frontmatter / link の鮮度のみで、いずれも内容の正否は非対象。

## ゴール / 非ゴール

- **ゴール**: docs の「内容妥当性」（主張のコード整合・論理の健全性・規範の正しさ・有用性・意味の陳腐化）を code-review の標準フローでレビューできるようにする
- **ゴール**: 起動ゲートを変更ファイル数比率から **doc の意味的重要度**へ移し、ファイル数の小さい重要 doc（CLAUDE.md / ADR / design doc / README）を取りこぼさない
- **ゴール**: 既存の reviewer / explorer / 反証 / scoring 機構を再利用し、新スキル・新 agent・新 hook を作らない
- **非ゴール**: 語句・トーン・冗長性の推敲（`writing-polish` の責務）。doc-substance は「真偽・論理・規範の正しさ・有用性」に限定する。表現の好みの除外は reviewer の自己判断でなく scoring クランプで機械的に行う（下記 C、`reviewer-prompts.md:39`「観点を自分で削らない」原則との衝突回避）
- **非ゴール**: 実装前 design doc の深掘り多視点レビュー（`design-doc:design-review` の責務。決定系 doc は soft 委譲で借りる）
- **非ゴール**: doc 鮮度（last-validated / link 切れ）の機械検証（`doc-freshness` の責務。境界は「frontmatter / link の決定的検証＝doc-freshness、本文の主張＝doc-substance」で機械的に切る）

## 確定した前提

grill Phase および design-review でコード裏取り済みの事項。出典は実ファイルで照合済み。

- **現行 `doc-review-mode` は整合性のみ**（`triage-guide.md:40` の PR 種別分岐表 1 行 + `:56-57` 出力例）。`*.md` ファイル比率 ≥ 80% で 1-2 reviewer に絞り、bug-detection をリンク切れ検出に読み替える。内容観点なし
- **比率は変更ファイル数で測る**（`triage-guide.md:63`）。行数比率ではない。doc-review-mode 発火も default-mode フォールバックもこの指標
- **観点は観点判定表で起動する**（`triage-guide.md:98-115`）。既存 18 観点はすべてこの表で diff パターンマッチにより条件付き起動。新観点はここに登録しないと起動しない（reviewer-prompts.md の Focus 定義追加だけでは不十分）
- **`comment-accuracy` が最も近い既存観点**（`reviewer-prompts.md:366-386`）。doc-substance はこれを doc ファイル本文へ一般化したもの（概念的アンカー）
- **報告マトリクスは severity × confidence の決定的フィルタ**（`scoring-guide.md:54-71`）。BLOCKER=conf 60+、CRITICAL=conf 80+、MAJOR / MINOR=conf 95+。severity 未付与は CRITICAL 扱い
- **scoring の既存補正を流用する**（`scoring-guide.md`）。「explorer 裏付け +10」(:101)、「複数エージェント +15」(:96)、「好みベース → confidence ≤ 40 クランプ」(:118-120) が既存。**裏取り報酬は新設せず既存 explorer +10 に乗せる**（+15 新設はキャリブレを割る）
- **反証レイヤーは effort 別の非対称ゾーン限定**（`triage-guide.md:299-330`）。high（既定）で「BLOCKER 60-94 / CRITICAL 80-94」のみ、low / medium はスキップ、MAJOR と 95+ は high で対象外、specialist 由来は全除外。**「specialist 以外を全て通す」ではない**。doc-substance の MAJOR（論理 / 有用性）は既定 effort で反証されない
- **高 severity は反証で消えない不変条件**（`scoring-guide.md:175`）。BLOCKER / CRITICAL は refuted でも注記のみで報告に残る。裏取り CRITICAL 昇格はこの不変条件に直撃する（下記 C / open）
- **dormant 判定はリポジトリ標準の settings grep**（例 `linear-workflow/skills/issue-create/SKILL.md:150-156` の `grep -q '"design-doc@' "$HOME/.claude/settings.json"`）
- **トリガーは重要度ゲート**、**severity モデルは裏取り証拠で昇格**（ユーザー確定）

## 採用案

既存 perspective カタログ + triage の拡張で解く。新コンポーネントは作らない（`component-addition-advisor` の退路確保を満たす）。

### A. `doc-substance` 観点の定義（reviewer-prompts.md）

`comment-accuracy` と同形式の**単一プロンプト**（検出対象リスト + severity 目安）として Section 3 カタログに追加する。doc 種別マトリクスは作らない（severity は下記 2 軸でしか分岐しないため、種別表は分岐を生まず過剰）。種別の区別は委譲判定（決定系 → design-review）にだけ使う。

検出対象と severity 目安:

- **ground-truth 正確性**: doc の技術的主張がコードと食い違う。grounding explorer / reviewer が code:line で矛盾を証明 → **CRITICAL（conf 80+ で報告）**。ただし昇格ガードあり（下記 C）
- **規範の正しさ**: 規約 doc（CLAUDE.md 等）の指示通りで動かない / 既存ルールと直接矛盾（別 doc:line で証明可能）→ MAJOR、直接矛盾を示せれば CRITICAL
- **論理的健全性**: 自己矛盾・非論理。内部矛盾の出典を doc:line ×2 で示せる → MAJOR
- **有用性**: 曖昧・hand-wavy・行動に移せない → MINOR〜MAJOR
- **意味の陳腐化**: 内容がコード現状と食い違う（リンク切れではない）→ 証明できれば CRITICAL、できなければ MAJOR

severity の本質は「裏取りできた内容誤り（CRITICAL）」と「裏取りできない論理 / 有用性（MAJOR / MINOR）」の **2 軸**。後者は根拠（code:line または doc:line ×2）を示せなければ表現の好みとみなされ scoring ≤40 クランプで自動除外される（C）。reviewer プロンプトには「表現・言い回しの好みは根拠なし（低 confidence）として申告する」とだけ書き、**観点の自己削除はさせない**（`reviewer-prompts.md:39` と非衝突）。

委譲: 決定系 doc（ADR / design doc / RFC 根拠）は `design-doc` 導入時のみ design-review (minimal / risk) へ dormant soft 委譲。未導入時は doc-substance が内製で代替。

### B. triage の作り替え（triage-guide.md）

**B-1. `doc-review-mode` を「整合性のみ」→「整合性必須 + doc-substance 条件付き」に改稿**
改稿対象は `triage-guide.md:40` の doc-review-mode 表行 + `:56-57` の出力例。docs 主体 PR で整合性 reviewer は必須、doc-substance は下記の共通起動条件を満たす場合のみ追加（typo・整形だけの doc PR には付けない）。

**B-2. 起動ゲートを変更ファイル数比率 → doc 重要度に（重要度ゲート、両経路共通条件）**
doc-substance の**起動条件は経路によらず共通**: **高価値 doc パス**（`CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING*` / `README*` / `.claude/adr/**` / `.claude/designs/**`）の prose 変更を含む **OR** 任意 `*.md` で実質 prose 変更（frontmatter / list マーカー / link-only 行を除いた追加・変更 prose 行が概ね 10 行以上）。typo / 整形 / frontmatter のみ / link-only の doc 変更には付けない。この条件を 2 経路の両方に適用する:
1. doc-review-mode 経路（`*.md` ≥ 80%）: 整合性 reviewer 必須 + 条件を満たせば doc-substance
2. 混在 PR 経路（`*.md` < 80%、default-mode）: 観点判定表（`triage-guide.md:98-115`）の `doc-substance` 行（同一条件）

高価値 doc パスの**正本は「doc-substance の起動」節の 1 箇所**に置き、観点判定表・種別分類・委譲はそこを参照する（複数表に重複定義しない）。

> smoke 実走（scenario D）で判明: 当初 doc-review-mode 経路は doc-substance を無条件併走させており、typo だけの `*.md` 100% PR でも grounding が起動してしまう穴があった。起動条件を両経路で共通化して修正。

**B-3. effort 別の起動制御**（既存の Phase 5.5/5.6/反証と同じく effort 適応に乗せる）:

| 実行時 effort | doc-substance 起動 |
|---|---|
| `low` | skip（反証も効かないため抑制） |
| `medium` | 高価値 doc パスを含む PR のみ |
| `high`（既定）/ `xhigh` / `max` | 重要度ゲート全面 |

「反証が効かない effort では doc-substance も抑制する」整合を取る。

**B-4. grounding は条件付き + 対象制限**
grounding explorer は必須化しない。既存 explorer の条件付き起動判定（`triage-guide.md:84-92`）に乗せ、対象コードが大きい / 分散している場合のみ起動、単一ファイルの主張は reviewer 自身の Read で裏取りする（small PR フォールバック 0 体と非衝突）。explorer が読む対象は **diff で変更された doc が参照するコード ∩ リポジトリ実在パス**に限定し、doc 本文（＝レビュー対象＝信頼できない入力）の任意パス記述を鵜呑みにしない。

**B-5. doc 種別分類**は委譲判定のためにのみ行う（記述 / 決定 / 規約 / 手順 / 概念 → 決定系のみ design-review へ）。

### C. scoring の調整（scoring-guide.md）

- **裏取り報酬**: grounding explorer / reviewer が code:line で主張⇔コード矛盾を確認した doc-substance 指摘は、既存「explorer 裏付け +10」(`scoring-guide.md:101`) の発火源として扱う（新規 +15 は作らない）
- **主観抑制**: 根拠（code:line / doc:line ×2）を示せない doc-substance 指摘は「好みベース」とみなし confidence ≤ 40 クランプ（既存 :118-120 流用）= 実質除外。これが MAJOR ノイズの主たる抑制機構（反証は既定 effort で MAJOR に効かないため）
- **severity モデル + grounding ガード**: 裏取り証拠ありの内容誤りは CRITICAL（conf 80+）。ただし「高 severity 非削除」不変条件（`scoring-guide.md:175`）に直撃するため、**昇格は矛盾の相手が「doc が実際に参照する・実在する・現行の」コード経路の場合に限る**。(a) 別経路 / stale パスとの突き合わせ（grounding 誤読）、(b) この PR が参照先を doc と整合に同時変更済み（git blame で同一 PR 同時変更＝実矛盾なし）、(c) doc が「将来 / 計画中」と明示、のいずれかでは昇格しない。**コードが doc より古いこと自体は昇格を妨げない**（安定コードへの誤記は正当な CRITICAL）。証拠なしの論理 / 有用性は MAJOR / MINOR のまま
  > smoke シナリオ設計時に判明: 当初「コードが doc より古い → 昇格しない」と書いていたが、それでは安定コードへの誤記（主要正例）まで昇格しなくなる。ガードは「別経路 / 同時変更 / intended」で絞るべきで、blame の前後関係単体ではない。

### D. 反証レイヤーへの組み込み（review Phase 5.8 / self-review Phase 4.8）

doc-substance の **CRITICAL（裏取り誤り、conf 80-94）は既定 effort の反証ゾーンに入る**ため、反証軸に doc 向け読み替えを明記する: `misread`（reviewer が doc の主張範囲を誤読）、`pre-validated`（別 doc / コードで既に正しく補足済み）、`intended`（doc が「将来 / 簡略化」と明示）、`pre-existing`（git blame でコードが doc より新しく、doc 側が陳腐）。一方 **MAJOR の論理 / 有用性は既定 effort では反証対象外**なので、その偽陽性抑制は C の ≤40 クランプ（根拠なし除外）に依存する。この非対称を前提に運用する。

### E. self-review との対称化

self-review SKILL（Phase 4.x）も同じ重要度ゲート・effort 制御・doc-substance を持つ。command↔skill ペアの allowed-tools 一致ルールに従い両者を同期する。

## 検討した代替案

| 観点 | 案 A: 重要度ゲート + 新観点（採用） | 案 B: docs 主体 PR のみ起動 | 案 C: design-review へ全委譲 |
|------|------------------------------------|------------------------------|------------------------------|
| 取りこぼし | 小（混在 PR・ファイル数小の重要 doc もカバー） | 中（混在 PR の prose は素通り継続） | 中（手動起動依存・流れに乗らない） |
| 実装変更量 | 中（5 ファイル + メタ） | 小（doc-review-mode 内のみ） | 小（triage で振り分けるだけ） |
| ノイズ/コスト | 中（≤40 クランプ + effort 制御 + 反証で抑制） | 小 | 中（記述/規約 doc に噛み合わず空振り） |
| 既存構造との整合 | 高（perspective + triage の自然な拡張） | 高 | 低（design-review はコード裏取り/実装前専用） |
| 汎用 doc への適合 | 高 | 中（範囲が狭い） | 低（記述系/規約系に弱い） |

- **案 B 不採用**: 失敗モード②（混在 PR の prose 素通り）を解けない。ファイル数比率では拾えない重要 doc が放置される
- **案 C 不採用**: design-review はコード裏取り前提・実装前 design doc に最適化されており、README / CLAUDE.md など記述系・規約系に噛み合わず空振りする。決定系 doc では強力なので案 A の中で dormant soft 委譲として部分採用する

## 設計判断ログ

- [local] doc-substance は `comment-accuracy` の「主張⇔コード一致」を doc 本文へ一般化したものと位置づける（新概念でなく既存観点の射程拡張として実装・説明する）
- [local] doc 種別は単一プロンプト内のサブ観点選択と委譲判定にのみ使い、severity 分岐は「裏取り CRITICAL / 非裏取り MAJOR-MINOR」の 2 軸に集約する（5 種別マトリクスは分岐を生まず過剰）
- [local] 裏取り報酬は新規 +15 を作らず既存「explorer 裏付け +10」に乗せる（観点ごとに加点が割れるキャリブレ破壊を避ける）
- [local] 表現の好みの除外は reviewer の自己削除でなく scoring ≤40 クランプで機械的に行う（`reviewer-prompts.md:39` の自己交渉禁止原則と非衝突にする）
- [local] grounding explorer は条件付き起動 + 読み取り対象を diff 変更 doc の参照コード ∩ 実在パスに限定（信頼できない doc 本文に任意パスを選ばせない）
- [local] doc-substance の起動を effort 適応表に乗せ、反証が効かない low/medium では抑制する（偽陽性が反証スキップで素通りする最悪の組合せを断つ）
- [local] 裏取り CRITICAL 昇格に git blame 前後関係検算を必須化（コードが doc より古い場合の誤昇格 + 高 severity 非削除不変条件への直撃を防ぐ）
- [→ADR候補] review 系の観点ゲートを「変更ファイル数比率」から「変更対象の意味的重要度」へ移す方針（doc-review 以外の triage 判断にも波及しうる横断方針）
- [→ADR候補] docs の内容妥当性は「決定的検証 > LLM 判定」の例外として LLM 観点を正式採用する（リポジトリの配置哲学への明示的な線引き。**LLM 観点の偽陽性抑制が effort に依存する**制約も併記する）

## 未解決事項 (open)

- **「実質 prose 変更」の閾値（目安 10 行）の妥当性**
  - (a) 固定行数閾値 / (b) prose 行比率 / (c) LLM 判定のみ
  - 現時点の方向性: (c) 寄りの (a)。高価値 doc はパスで決定的に拾い、それ以外は LLM 判定 + 行数を下限ガードに使う（純粋 LLM 判定だと再現性が落ちる。既存観点判定はすべて決定的マッチで、LLM 文脈ゲートは新規挙動）
  - 確定タイミング: 実装後、実 PR 数件での誤起動 / 取りこぼし観察で調整
- **design-review の非対話起動可否**
  - triage / reviewer フローの中から `Skill` tool で design-review に観点・対象を非対話で渡せるか（design-review SKILL は単体起動前提の可能性）
  - 現時点の方向性: dormant soft 委譲は「決定系 doc では doc-substance プロンプトに design-review の minimal/risk チェックリストを内挿する」軽量版に倒し、スキル間呼び出しに依存しない案を有力とする
  - 確定タイミング: 実装時に `design-doc/skills/design-review/SKILL.md` の起動 API を確認して確定
- **裏取り CRITICAL が反証 refuted でも残る経路の最終扱い**
  - 高 severity 非削除不変条件（scoring:175）と doc レビューの双方向曖昧性（doc が正・コードが古いケース）の緊張
  - 現時点の方向性: git blame 検算ガード（C）で誤昇格自体を抑える。なお残る場合 doc-substance の裏取り誤りだけ CRITICAL でなく MAJOR に留める案も比較する
  - 確定タイミング: 実装時の smoke（既知の「コードが新しく doc が古い」逆ケース）で挙動を見て確定
- **doc-substance の冗長化（x2）条件**
  - 現時点の方向性: 初版は単体起動。effort high+ かつ決定系 doc 複数のときのみ angle 分割（裏取り軸 / 論理軸）を許可
  - 確定タイミング: 実装時に reviewer-prompts.md Section 4 angle 定義へ追記するか判断

## 実装ブリッジ (Implementation Bridge)

**1. 実装着手の単位（Issue / コミット分解案）**

1. `reviewer-prompts.md`: Section 3（`## 3. Focus テンプレート`）に `doc-substance` 単一プロンプト追加（検出対象 + 2 軸 severity 目安 + 「表現の好みは低 confidence 申告・観点の自己削除はしない」明記）。Section 4 angle は当面追記しない（open）
2. `triage-guide.md`:
   - `:40` doc-review-mode 表行 + `:56-57` 出力例を「整合性 + doc-substance」に改稿（B-1）
   - `:98-115` 観点判定表に `doc-substance` 行を追加（起動条件 = 高価値 doc パス OR 実質 prose ≥10 行。混在 PR 経路、B-2）
   - effort 適応箇所に doc-substance の起動制御表を追加（B-3）
   - grounding は既存 explorer 条件付き起動に乗せ、対象パス制限を注記（B-4）
   - 高価値 doc パスの正本をこの表に置く（重複定義しない）
3. `scoring-guide.md`: 裏取り → 既存 explorer +10 の発火源に追加 / 根拠なし ≤40 クランプ流用 / 裏取り CRITICAL 昇格 + git blame 検算ガード（C）
4. review SKILL Phase 5.8 / self-review Phase 4.8: 反証軸の doc 読み替え（misread / pre-validated / intended / pre-existing）を明記（D）。両 SKILL の Phase 0 トリアージ記述に重要度ゲート + effort 制御を反映（E）。design-review soft 委譲は `grep -q '"design-doc@' "$HOME/.claude/settings.json"` で dormant 判定
5. メタ: `code-review/.claude-plugin/plugin.json` を version 2.26.0 → 2.27.0（MINOR）、`CHANGELOG.md` 更新（Added）、`.claude-plugin/marketplace.json` 同期。**userConfig トグルは追加しない**（無効化は既存 `review_severity_threshold` で代替）

> feature-dev で一気通貫する場合: `/feature-dev code-review に doc-substance 観点を追加（重要度ゲート + effort制御 + grounding裏取り + 裏取り昇格ガード）`

**2. 検証方法**

- 静的: `/quality-check`（marketplace 同期 / allowed-tools 一致 / hooks 安全性 / references 参照整合）+ `claude plugin validate`
- 回帰: `evals/runner.py` でトリガーフレーズ → スキル選択の pass^k=3（doc-review 系フレーズで code-review が選ばれるか）
- runtime smoke（正例 + **負例**）:
  - 正例 (a) コードと食い違う README diff で doc-substance が裏取り CRITICAL を出すか
  - 正例 (b) docs 主体 PR で整合性指摘と内容指摘の両方が出るか
  - 正例 (c) 混在 PR（コード多数 + CLAUDE.md 1 行）で重要度ゲートが起動するか
  - 負例 (d) frontmatter のみ / typo 1 行の `*.md` で doc-substance が**起動しない**か
  - 負例 (e) 「言い回しを変えたい」級の主観が ≤40 クランプで消えるか
  - 負例 (f) コードが doc より新しい逆ケースで裏取り CRITICAL に**昇格しない**か（git blame ガード）
  - 負例 (g) grounding explorer が doc 本文の実在しない参照パスを読みに行かないか
  - 抑制 (h) effort=low で doc-substance が起動しないか

**3. 実装完了時の doc 更新手順**

- frontmatter の `phase: target` → `current`、`last-validated` を実装日に更新
- 実装と乖離した箇所（閾値の最終値・委譲の軽量版採否・CRITICAL 留め置き判断）を「確定した前提」へ反映、方式ごと変わったら supersede
- [→ADR候補] 2 件（重要度ゲート方針 / LLM 観点の正式採用）を adr-keeper へ切り出し済みか確認し、id を frontmatter `adrs:` に追記

## 関連

- 関連 Issue: なし
- 関連 spec: なし
- 関連 ADR: （未切り出し。[→ADR候補] 2 件）
- 関連 design doc: [[20260623-review-adversarial-verify-layer]]（反証レイヤー。doc-substance の裏取り CRITICAL は同レイヤーを通るが、MAJOR は既定 effort で対象外）
