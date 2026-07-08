---
name: create-spec
description: >
  BDD spec 駆動の user story を scaffold する。
  user story dir + epic.md（Why/What 散文）+ spec.md（BDD Feature/Scenario/Examples + 同値分割表 + 状態遷移表（stateful のみ・任意））を生成する。
  プロジェクトに all_spec.md / common_spec.md が無ければそれらも初期化する。
  トリガー: 「BDD spec 作る」「user story scaffold」「Feature ファイル作る」「spec.md 作る」
  「BDD で書きたい」「Scenario テンプレ」「同値分割表 テンプレ」「/bdd-spec-create」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

# Create Spec

BDD spec 駆動 (Behavior Driven Development) の user story を scaffold するスキル。

詳細は `references/` を参照:

- `references/story-naming.md` — ディレクトリ命名規約 + 短縮モード
- `references/epic-template.md` — Why/What 散文テンプレ
- `references/spec-template.md` — BDD Feature/Scenario/Examples テンプレ
- `references/glossary-ssot.md` — 用語 SSoT（`all_spec.md`）と別名禁止メタルール
- `references/common-spec-template.md` — 共通仕様（`common_spec.md`）テンプレ

---

## Phase 0: 設定ロード

1. `.claude/bdd-spec.json` の存在を確認（Read、無ければデフォルトで続行）
2. 設定値:
   - `shortPath` (デフォルト `false`) — true で `{role}-{verb}-{object}` 短縮命名
   - `featuresDir` (デフォルト `features`) — story を置くルートディレクトリ
   - `language` (デフォルト `ja`) — テンプレートの言語

---

## Phase 1: ヒアリング

ユーザーから 3 要素を聞き出す:

1. `{role}` — ユーザー区分（例: 「契約管理者」「営業担当」）
2. `{want}` — 達成したいこと（例: 「契約書を一括承認」）
3. `{why}` — 動機（例: 「月末処理を半分の時間で終わらせたい」）

会話文脈で既に明示されていれば再ヒアリングしない。

**追加で `shortPath` 採用時は以下も:**
- `{verb}` — 動詞（例: 「approve」「create」「list」）
- `{object}` — 対象（例: 「contracts」「reports」）

---

## Phase 2: dir 名決定

1. `shortPath: false`（デフォルト）:
   - `dirname = "Userは、{role}として、{want}したい"`
   - 例: `Userは、契約管理者として、契約書を一括承認したい`
2. `shortPath: true`:
   - `dirname = "{role}-{verb}-{object}"`
   - 例: `contract-admin-approve-contracts`
3. **衝突チェック**: `{featuresDir}/{dirname}/` の存在を Glob で確認
4. 既存ディレクトリがあれば AskUserQuestion で確認:
   - question: "同名ディレクトリが既に存在します"
   - header: "衝突対応"
   - options:
     1. label: "別名で作成" / description: "サフィックス（-v2）を付加"
     2. label: "上書き" / description: "既存の epic.md / spec.md を上書き（バックアップは取らない）"
     3. label: "中止" / description: "scaffold を中止"

詳細命名規約は `references/story-naming.md`。

---

## Phase 3: プロジェクト共通ファイル初期化

`{featuresDir}/all_spec.md` と `{featuresDir}/common_spec.md` の存在を確認:

- 両方存在 → そのまま Phase 4 へ
- どちらか欠落 → AskUserQuestion で初期化承認:
  - question: "プロジェクト共通ファイルが未整備です。初期化しますか？"
  - header: "共通ファイル初期化"
  - options:
    1. label: "両方初期化" / description: "all_spec.md + common_spec.md をテンプレから生成"
    2. label: "story のみ作成" / description: "共通ファイルは後で手動作成"

承認時は `references/glossary-ssot.md` と `references/common-spec-template.md` の内容を Write する。

---

## Phase 4: epic.md 生成

まず **本日の日付を Bash で取得**する（擬似日付を作らない。姉妹プラグイン adr-keeper / design-doc と同じ規律）:

```bash
date +%Y-%m-%d   # {CREATED_DATE} 用。epic.md / spec.md の last-validated に入れる
```

`references/epic-template.md` を読み込み、以下のプレースホルダーを置換して Write:

- `{ROLE}` → `{role}`
- `{WANT}` → `{want}`
- `{WHY}` → `{why}`
- `{CREATED_DATE}` → 上記 `date +%Y-%m-%d` の結果

書き出し先: `{featuresDir}/{dirname}/epic.md`

---

## Phase 5: spec.md 生成

`references/spec-template.md` を読み込み、以下を反映:

- `{CREATED_DATE}` → Phase 4 で取得した `date +%Y-%m-%d` の結果（frontmatter の `last-validated`）
- `Feature:` 行は `{want}` から自動生成（例: `Feature: 契約書を一括承認する`）
- `Background:` は `common_spec.md` への参照
- `Scenario:` / `#### Examples` / 同値分割表 / 状態遷移表（stateful のみ・任意）は **空の骨格**として scaffold（ユーザーが後で埋める）。stateful なフィーチャーでは各 Scenario に「カバーする辺」注記も併せて埋めるよう案内する（`bdd-spec-evaluate` 観点 5 の双方向トレース用）

書き出し先: `{featuresDir}/{dirname}/spec.md`

> **doc-freshness との関係（scaffold 直後の stale 回避）**: epic.md / spec.md は `phase: current` で開始する。scaffold 直後は本文が未記入だが、doc-freshness の **grace period**（新規 doc 保護、デフォルト 7 日）が作成日から効くため、その間に `last-validated` を埋めれば stale error にならない。spec は「埋めて育てる生きた文書」なので ADR のような `append_only` 免除は付けない（grace period 経過後に未記入のまま放置されれば stale として検出されるのは正しい挙動）。

---

## Phase 6: 用語整合チェック

`all_spec.md` を Read し、`{role}` / `{want}` に含まれる名詞・動詞のうち、用語辞書に登録されていないものを抽出。

- 新規語が **1 件以上** → AskUserQuestion で「用語辞書に追加するか」確認
  - question: "新規用語を all_spec.md に追加しますか？"
  - header: "用語追加"
  - options:
    1. label: "追加" / description: "用語辞書に Edit で追記"
    2. label: "スキップ" / description: "用語辞書は変更しない"
- 別名の疑い（既存語の表記揺れ） → 提案のみ。自動置換しない

詳細は `references/glossary-ssot.md`。

---

## Phase 7: 完了報告

```
✅ user story scaffold 完了

📁 {featuresDir}/{dirname}/
  ├ epic.md  (Why/What を埋めてください)
  └ spec.md  (Scenario / Examples / 同値分割表を埋めてください)

次のアクション:
- epic.md の「成果物」「完了条件」を埋める
- spec.md の Scenario / Examples を埋める
- 用語追加があれば all_spec.md を更新
```

---

## 処理フロー

```
1. Phase 0: .claude/bdd-spec.json または default
2. Phase 1: {role} / {want} / {why} ヒアリング
3. Phase 2: dir 名決定 + 衝突チェック
4. Phase 3: all_spec.md / common_spec.md 初期化（必要なら）
5. Phase 4: 日付取得（date +%Y-%m-%d）→ epic.md 生成
6. Phase 5: spec.md 生成
7. Phase 6: 用語整合チェック
8. Phase 7: 完了報告
```

---

## API 安定保証（feature-dev 連携）

`feature-dev` からの `Skill bdd-spec:create-spec` 呼び出しを安定 API として扱う。

引数で渡せる値（Phase 1 ヒアリングをスキップ）:

| 引数キー | 必須 | 説明 |
|---|---|---|
| `role` | yes | ユーザー区分 |
| `want` | yes | 達成したいこと |
| `why` | no | 動機（無ければスキップ）|
| `shortPath` | no | 短縮モード強制（設定上書き） |
| `verb` | shortPath=true 時 yes | 動詞 |
| `object` | shortPath=true 時 yes | 対象 |

引数で全て埋まっていれば AskUserQuestion を発火せず非対話で実行する（feature-dev embed 用途）。

---

## 注意事項

- **読み取り中心、書き出しは Phase 4-6**: scaffold が主目的、評価は対象外（埋めた後の 5 観点評価は姉妹スキル `bdd-spec:evaluate-spec` の領分。Generator と Evaluator を分離している）
- **既存ファイル上書きは Phase 2 で明示承認**: epic.md / spec.md を勝手に上書きしない
- **用語整合は提案のみ**: 自動置換すると意図しないリネームを起こすため、ユーザー判断に委ねる
- **shortPath の trade-off**: 日本語フルパスは `ls` で機能カタログになる利点 vs Windows MAX_PATH / CI 互換性。`shortPath: true` で運用する場合は dir 名と user story 文を spec.md 冒頭に併記する規約
