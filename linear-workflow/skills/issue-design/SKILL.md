---
name: issue-design
description: >
  Linear 連携プロジェクトの Issue documentation の書き方ガイド。9 セクションテンプレと設計判断ルール（決定 vs open の
  境界、現時点の方向性マーカー、後続の双方向記述、確定タイミング明示）に沿って、Issue 本文を
  設計・構造化・リライトする。新規 Issue の起票・Linear 取り込みは issue-create、
  作成済み Issue の整理・圧縮・品質チェックは issue-maintain に任せる
  （このスキルは設計判断の言語化と構造リライトに専念する）。
  トリガー: 「Issue 設計」「Issueの書き方」「Issueを設計し直す」「Issueリライト」「設計判断どう書く」「決定とopenの仕分け」「9セクション設計」「/issue-design」
effort: medium
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Skill
  - AskUserQuestion
---

# Issue Design

Issue documentation pattern の規範を提供し、Issue 本文を 9 セクション構造で設計・リライトするスキル。
「どんな構造で・どんな判断軸で Issue を書くべきか」を定義し、ユーザーの素材や既存 Issue をその構造に落とし込む。

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| Issue 本文をどう構造化するか、設計判断（決定 / open）をどう書くか | **issue-design**（本スキル） |
| 既存 Issue を 9 セクション構造にリライト・設計し直す | **issue-design**（本スキル） |
| 新しい Issue を Linear から取り込む / 新規起票する | `issue-create`（テンプレ選択 + ファイル生成） |
| 作成済み Issue の品質チェック・圧縮・knowledge 切り出し | `issue-maintain` |

> 「Issue を作って」「新しいタスク」は issue-create の領分。本スキルは **設計・書き方・リライト** に専念する。
> 意図が曖昧な場合（「Issue 書きたい」など）は AskUserQuestion で「新規起票（create）」か「設計・リライト（design）」かを確認する。

## 参照する規範（references）

設計時は以下を Read で読み込んで適用する。

- `${CLAUDE_SKILL_DIR}/references/template-9sections.md` — 9 セクションの定義・書き方・コピペ用雛形（普遍）
- `${CLAUDE_SKILL_DIR}/references/design-rules.md` — 決定 vs open の境界、現時点の方向性、双方向依存、確定タイミング（普遍）
- `${CLAUDE_SKILL_DIR}/references/linear-syntax.md` — Linear 固有記法（collapsible / Issue リンク / インライン pros/cons）

---

## ワークフロー

### Phase 0: 対象の特定

1. 新規本文の設計か、既存 Issue のリライトかを判別する
2. 既存 Issue の場合: 対象ファイルを特定して Read する
   - ブランチ名から Issue ID を抽出し `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
   - 特定できなければユーザーに対象を確認する
3. 意図が曖昧（新規起票なのか設計なのか不明）なら **AskUserQuestion** で確認:
   - question: 「Issue を新規起票しますか、既存の設計・リライトをしますか？」
   - options: 「新規起票（issue-create に切替）」/「設計・リライト（このまま続行）」
   - 「新規起票」選択時は issue-create に案内して終了する

### Phase 0.5: BDD bilayer モード（bdd-spec 連携・opt-in）

`bdd-spec` plugin が同居している場合、Issue を **human 層（9 セクション散文・背景・設計判断）と AI 層（BDD `spec.md` の Feature / Scenario / Examples）の二重化（bilayer）** で設計できる。AI ハーネスには AI 層だけ Read させる運用（AGENTS.md / CLAUDE.md 側で制御）を想定し、このスキルは **生成のみ**を担う。bdd-spec 未インストール時は本フェーズは完全に dormant（従来の単一ファイル設計）。

1. bdd-spec のインストールを判定する（check-deps.sh と同じ方式）:
   ```bash
   if grep -q '"bdd-spec@' "$HOME/.claude/settings.json" 2>/dev/null; then BDD_BILAYER=1; else BDD_BILAYER=0; fi
   ```
   - `BDD_BILAYER=0` → 本フェーズを skip し、従来の単一ファイル設計のまま Phase 1 へ
2. `BDD_BILAYER=1` のとき **AskUserQuestion** で確認:
   - question: 「bdd-spec が利用可能です。Issue を human 層（9 セクション）+ AI 層（BDD spec.md）の bilayer で設計しますか？」
   - header: 「bilayer 設計」
   - options:
     1. label: 「bilayer (推奨)」/ description: 「9 セクション本文（human 正本）に加え bdd-spec:create-spec で spec.md（AI 用 BDD）を生成」
     2. label: 「従来通り」/ description: 「9 セクション単一ファイルのみ。spec.md は生成しない」
   - 「従来通り」選択 → dormant（Phase 1 へ）
3. 「bilayer」を選んだ場合、Phase 1〜4 で 9 セクション本文（human 正本）を設計・反映したうえで、**AI 層を生成**する:
   - `Skill` tool で `bdd-spec:create-spec` を呼ぶ。非対話 API（bdd-spec の安定保証セクション参照）に従い引数で渡す:
     - `role=<Issue から得た役割>` / `want=<実現したいこと>` / `why=<背景、不明なら省略>` / `shortPath=<true/false 省略可>`
   - 引数で全要素が埋まっていれば bdd-spec 側は AskUserQuestion を発火せず非対話実行する
   - 生成された `spec.md` のパスを Issue 本文の「成果物」または「参考資料」にファイルリンクで記録する（human 層 → AI 層のポインタ）
4. fallback: bdd-spec:create-spec が失敗（version 不整合・内部エラー等）したら warning を出し、9 セクション本文のみで完了する（後方互換 100%）

### Phase 1: 9 セクション構造で設計

1. `references/template-9sections.md` を Read する
2. ユーザーの素材（メモ・箇条書き・既存 Issue 本文）を 9 セクションにマッピングする
   - Why / 成果物 / 対応内容 / 完了条件 / 依存・ブロッカー / 決定事項 / 判断ポイント(open) / 参考資料 / スコープ外
3. 各セクションのアンチパターン（What だけで Why が無い、主観的な完了条件など）を避ける

### Phase 2: 決定 vs open の仕分け

1. `references/design-rules.md` を Read する（ルール1〜5）
2. 確定事項を「決定事項」、未確定を「判断ポイント (open)」に振り分ける
   - 仕分けの問い: 「今ここで根拠を書き切れるか？」YES→決定 / NO→open
3. 各 open には必ず以下を添える:
   - `(a)(b)(c)` の選択肢 + pros/cons
   - **現時点の方向性**（有力案 + 理由）
   - **確定タイミング**（いつ・どこで確定するか）
4. **open を grill で詰める（design-rules.md ルール5）**: open を独断列挙で終えず、コミット前に 1 つずつ詰める:
   1. **自己解決**: 各 open について「既存 ADR / 他 Issue / コードで決着済みでは？」を `Grep` / `Skill` の `knowledge` /（adr-keeper があれば）`adr` で確認する。決着済みなら open から決定事項へ移す（ユーザーに聞かない）
   2. **1 問ずつ確認**: 残った open を依存順（先行 open が後続の選択肢を変える順）に並べ、**AskUserQuestion で 1 問ずつ**確認する。各質問は「現時点の方向性」を推奨案として先頭に置き `(Recommended)` を付ける
   3. ユーザーが「おまかせ」なら推奨案で確定する。前の回答で後続 open が解消・変形したら畳み直す
   - **過剰質問を避ける**: open が 1〜2 個かつ方向性が明確なら、grill を 1 回の提示にまとめてよい
   - **effort 適応（grill の掘り下げ）**: 実行時 effort = `${CLAUDE_EFFORT}` に応じて grill の深さを調整する（1. の自己解決は effort によらず必ず行う）:

     | effort | grill の深さ |
     |--------|-------------|
     | low / medium | 9 セクションの充足確認と決定 / open の仕分けを中心に据え、残った open は依存順の 1 問ずつ確認をせず 1 回の提示にまとめる（周回しない・速度優先） |
     | high | 残った open を依存順に 1 問ずつ確認する（上記 2. のフローどおり） |
     | xhigh / max | 1 問ずつの確認に加え、回答で open が解消・変形するたびに畳み直して問い直す周回を増やし、「決定事項」側も根拠を書き切れているかを再点検して怪しいものは open に差し戻して詰める |
5. 依存は **双方向**（先行 + 後続）で書き、Issue が孤立しないようにする
6. **design doc への昇格判断（design-doc 連携・opt-in）**: open がタスク 1 件の作業設計を超えている兆候があれば、設計部分の design doc 切り出しを提案する。兆候の例:
   - 複数 Issue にまたがる方式選定（アーキテクチャ・データフロー・移行戦略）が open に含まれる
   - 選択肢の比較（トレードオフ表が要る規模）が Issue 本文では持ちきれない
   1. インストール判定（check-deps.sh と同方式）:
      ```bash
      if grep -q '"design-doc@' "$HOME/.claude/settings.json" 2>/dev/null; then DESIGN_DOC=1; else DESIGN_DOC=0; fi
      ```
      `DESIGN_DOC=0` または兆候なし → 何もしない（従来どおり grill で詰める）
   2. `DESIGN_DOC=1` かつ兆候あり → **AskUserQuestion** で確認:
      - question: 「この open はタスク単位を超えた設計判断を含みます。design doc に切り出しますか？」
      - options: 「design doc に切り出す (Recommended)」/「Issue 内で grill を続ける」
   3. 切り出す場合: `design-doc:design-doc` スキル（new）で設計を詰め、生成された doc のリポジトリ内パス（`.claude/designs/<id>.md`）を Issue の「参考資料」に記録する。該当 open は「確定タイミング: design doc <id> で確定」に書き換える（Issue 側に議論を重複させない）
   4. fallback: design-doc 呼び出しが失敗したら warning を出し、従来どおり Issue 内の grill で続行する

### Phase 3: Linear 記法の適用

1. `references/linear-syntax.md` を Read する
2. 補助セクション（依存・参考資料）は `+++` collapsible で畳む（閉じ忘れに注意）
3. 他 Issue 参照は `<issue id>` リンクで繋ぐ（双方向依存を可視化）
4. open の pros/cons はインライン圧縮形式で書く
5. 重複表現を除去して一望性を高める

### Phase 3.5: writing-polish 連携（本文添削・必須）

Phase 1〜3 で設計した 9 セクション本文の散文部分は、ユーザー提示（Phase 4）の直前に writing-polish へ渡して推敲する（冗長削減・曖昧語の具体化・トーン統一・AI っぽさ除去）。`writing-polish` がインストールされていれば**必ず**通す。未インストール時のみ skip（プラグイン独立性のため。後方互換）。

1. インストール判定（check-deps.sh と同方式）:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
     WRITING_POLISH=1
   else
     WRITING_POLISH=0
   fi
   ```
   `WRITING_POLISH=0` → 本 Phase を skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を `--embed --tone issue` で呼び、本文の散文部分を渡す。
3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは本文に含めない）を本文の代わりに使う。ただし **9 セクション構造・Linear collapsible（`+++`）・Issue リンクは変更しない（各セクション内の散文のみ推敲）。構造を壊す結果は破棄し元案を使う**。変更があれば何を変えたか一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で従来どおり完了する。

> 対象は human 層の散文。Phase 0.5（bdd-spec bilayer）で生成する AI 層 spec.md は添削対象外。

### Phase 4: ユーザー承認 → 反映

1. 設計した本文をユーザーに提示する
2. 承認を得てから反映する:
   - 既存 Issue ファイルのリライト → Write で更新
   - 新規本文のみ設計した場合 → 本文を提示し、ファイル化が必要なら issue-create に案内する
3. リライトで削った情報がある場合は「何を削ったか」を一言添える（ノイズ削減であって情報損失でないことを示す）

---

## 設計原則

- **本スキルは規範の適用に専念する**: 9 セクション定義と判断ルールの正本は references にある。本文を変えるときは references を読んで適用する
- **redundancy を増やさない**: リライト時は情報を減らすのではなくノイズを減らす
- **プロジェクト固有ルールは持ち込まない**: 特定チームの命名規約や独自記法はこのスキルに書かず、リポジトリの CLAUDE.md 等に委ねる
