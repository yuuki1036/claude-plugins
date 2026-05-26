---
name: issue-design
description: >
  Issue documentation の書き方ガイド。9 セクションテンプレと設計判断ルール（決定 vs open の
  境界、現時点の方向性マーカー、後続の双方向記述、確定タイミング明示）に沿って、Issue 本文を
  設計・構造化・リライトする。新規 Issue の起票は indie-issue-create、
  作成済み Issue の整理・圧縮・品質チェックは indie-issue-maintain に任せる
  （このスキルは設計判断の言語化と構造リライトに専念する）。
  トリガー: 「Issue 設計」「Issueの書き方」「Issueを設計し直す」「Issueリライト」「設計判断どう書く」「決定とopenの仕分け」「9セクション設計」「/issue-design」
effort: medium
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
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
| 新しい Issue を新規起票する（採番 + ブランチ作成） | `indie-issue-create` |
| 作成済み Issue の品質チェック・圧縮・knowledge 切り出し | `indie-issue-maintain` |

> 「Issue を作って」「新しいタスク」は indie-issue-create の領分。本スキルは **設計・書き方・リライト** に専念する。
> 意図が曖昧な場合（「Issue 書きたい」など）は AskUserQuestion で「新規起票（create）」か「設計・リライト（design）」かを確認する。

## 参照する規範（references）

設計時は以下を Read で読み込んで適用する。

- `${CLAUDE_SKILL_DIR}/references/template-9sections.md` — 9 セクションの定義・書き方・コピペ用雛形（普遍）
- `${CLAUDE_SKILL_DIR}/references/design-rules.md` — 決定 vs open の境界、現時点の方向性、双方向依存、確定タイミング（普遍）

---

## ワークフロー

### Phase 0: 対象の特定

1. 新規本文の設計か、既存 Issue のリライトかを判別する
2. 既存 Issue の場合: 対象ファイルを特定して Read する
   - ブランチ名から Issue ID を抽出し `.claude/indie/{slug}/issues/{ISSUE-ID}.md`
   - 特定できなければユーザーに対象を確認する
3. 意図が曖昧（新規起票なのか設計なのか不明）なら **AskUserQuestion** で確認:
   - question: 「Issue を新規起票しますか、既存の設計・リライトをしますか？」
   - options: 「新規起票（indie-issue-create に切替）」/「設計・リライト（このまま続行）」
   - 「新規起票」選択時は indie-issue-create に案内して終了する

### Phase 1: 9 セクション構造で設計

1. `references/template-9sections.md` を Read する
2. ユーザーの素材（メモ・箇条書き・既存 Issue 本文）を 9 セクションにマッピングする
   - Why / 成果物 / 対応内容 / 完了条件 / 依存・ブロッカー / 決定事項 / 判断ポイント(open) / 参考資料 / スコープ外
3. 各セクションのアンチパターン（What だけで Why が無い、主観的な完了条件など）を避ける

### Phase 2: 決定 vs open の仕分け

1. `references/design-rules.md` を Read する
2. 確定事項を「決定事項」、未確定を「判断ポイント (open)」に振り分ける
   - 仕分けの問い: 「今ここで根拠を書き切れるか？」YES→決定 / NO→open
3. 各 open には必ず以下を添える:
   - `(a)(b)(c)` の選択肢 + pros/cons
   - **現時点の方向性**（有力案 + 理由）
   - **確定タイミング**（いつ・どこで確定するか）
4. 依存は **双方向**（先行 + 後続）で書き、Issue が孤立しないようにする

### Phase 3: ローカル Markdown 記法の適用

indie-workflow の Issue は `.claude/indie/{slug}/issues/*.md` のローカル Markdown ファイル。標準 Markdown で書く。

1. 補助セクション（依存・参考資料）を畳みたい場合は `<details><summary>…</summary> … </details>` を使う
2. 他 Issue への参照は相対パス（`../issues/{ISSUE-ID}.md`）で繋ぎ、双方向依存を可視化する
3. open の pros/cons はインライン圧縮形式（`— Pros: … / Cons: …`）で書く
4. 重複表現を除去して一望性を高める

### Phase 4: ユーザー承認 → 反映

1. 設計した本文をユーザーに提示する
2. 承認を得てから反映する:
   - 既存 Issue ファイルのリライト → Write で更新
   - 新規本文のみ設計した場合 → 本文を提示し、ファイル化が必要なら indie-issue-create に案内する
3. リライトで削った情報がある場合は「何を削ったか」を一言添える（ノイズ削減であって情報損失でないことを示す）

---

## 設計原則

- **本スキルは規範の適用に専念する**: 9 セクション定義と判断ルールの正本は references にある。本文を変えるときは references を読んで適用する
- **redundancy を増やさない**: リライト時は情報を減らすのではなくノイズを減らす
- **プロジェクト固有ルールは持ち込まない**: 特定プロジェクトの命名規約や独自記法はこのスキルに書かず、リポジトリの CLAUDE.md 等に委ねる
