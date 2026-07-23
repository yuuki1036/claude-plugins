---
name: adr
description: >
  Architecture Decision Record (ADR) を append-only で蓄積し、設計判断の WHY を記録する。
  YYYYMMDDhhmmss 秒精度のファイル名で命名し、適用方法 (Enforcement) セクションを必須化して死に文書化を防ぐ。
  supersede 時は新規作成 + 旧 ADR の 4 フィールド更新（status / phase / superseded-by / last-validated）を機械的に踏ませて整合漏れを防ぐ。
  トリガー: 「ADR作成」「設計判断記録」「アーキテクチャ決定記録」「ADR supersede」「ADR一覧」
  「決定の理由を残す」「/adr」「architecture decision record」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

# ADR

Architecture Decision Record (ADR) を append-only で蓄積するスキル。設計判断の **WHY** を記録し、supersede 時の整合を機械的に担保する。

詳細は `references/` を参照:

- `references/template.md` — ADR 本文テンプレ + frontmatter 雛形（プレースホルダ方式）
- `references/naming.md` — 命名規約（秒精度 timestamp / kebab / 衝突回避の理由）
- `references/examples.md` — 良い ADR の記入例

---

## Phase 0: 保存先確認

1. `.claude/adr/` の存在を確認（Glob または Bash の `test -d`）
2. 不在なら Bash で作成:
   ```bash
   mkdir -p .claude/adr
   ```
3. ADR は **committed 前提**（プロジェクトローカルに永続化）

---

## Phase 1: サブコマンド判定

引数を解析して 3 つのモードに振り分ける:

| サブコマンド | 引数 | 遷移先 |
|---|---|---|
| `list`（または未指定） | - | Phase 2 |
| `new` | `<title>` | Phase 3 |
| `supersede` | `<old-id> <new-title>` | Phase 4 |

`new` / `supersede` で title が未指定なら、会話文脈から決定を推定し、確定できなければユーザーに 1 度だけ確認する。

---

## Phase 2: list（一覧表示）

1. `.claude/adr/*.md` を Glob
2. **0 件** → 「ADR がまだありません」と報告して終了
3. 各ファイルの frontmatter を Read で解析し、`id` / `title` / `status` / `phase` / `last-validated` を抽出
4. **id 降順**（新しい順）で表に整形:

```
## ADR 一覧（N 件）

| id | title | status | phase | last-validated |
|----|-------|--------|-------|----------------|
| 20260529143012 | API バージョニング方針 | accepted | current | 2026-05-29 |
| 20260520091500 | 認証方式の選定 | superseded | superseded | 2026-05-29 |
```

> id は `YYYYMMDDhhmmss`（T 区切りなし）。ファイル名の timestamp と同一値にする（`references/naming.md`）。

> title は `# ADR-<id>: <title>` の見出しから取得してもよい（frontmatter に title が無い場合）。

---

## Phase 3: new（新規作成）

1. **タイムスタンプ取得**（必ず Bash で取る。擬似時刻を作らない）:
   ```bash
   date +%Y%m%d%H%M%S
   ```
2. **kebab タイトル生成**: `<title>` を小文字 kebab-case に変換（日本語タイトルは romaji 化せず、英語の要約 slug をユーザー意図から作る。語間はハイフン）
3. **ファイル名**: `<timestamp>-<kebab-title>.md`（保存先 `.claude/adr/`）
4. **id**: frontmatter の `id` は `<timestamp>` をそのまま使う（命名規約は `references/naming.md`）
5. **status 確定**: 会話文脈から決定済み（accepted）か検討中（proposed）かが自明ならそれを使う。曖昧なら **AskUserQuestion** で確認する:
   - question: "この ADR は決定済みですか、まだ検討中（提案）ですか？"
   - header: "ADR status"
   - options:
     1. label: "accepted（決定済み）" / description: "既に採用が決まった判断を記録する（既定。phase: current）"
     2. label: "proposed（提案）" / description: "まだ決定していない案を記録する（phase: current のまま、後で accepted に更新）"
6. `references/template.md` を Read し、以下を置換して Write:
   - `{ID}` → `<timestamp>`
   - `{TITLE}` → `<title>`（原文ママ）
   - `{STATUS}` → 上記で確定した `accepted` / `proposed`
   - `{PHASE}` → `current`
   - `{TODAY}` → `date +%Y-%m-%d` の結果
   - `{SUPERSEDES}` → `[]`
   - `{SUPERSEDED_BY}` → `null`
   - `append_only: true` はテンプレの固定値（置換不要）。doc-freshness に stale 判定を免除させるマーカーとして必ず残す
7. **適用方法 (Enforcement) セクションは必ず埋めるよう促す**: 「この決定を lint / test / hook で機械強制できないか」を検討した結果を本文に残す（できない場合はその理由）

---

## Phase 4: supersede（置き換え）

旧 ADR を新 ADR で置き換える。「新規作成 + 旧 ADR の 4 フィールド更新（status / phase / superseded-by / last-validated）」を機械的に踏ませて漏れを防ぐのが核心。

1. **旧 ADR 特定**: `.claude/adr/*<old-id>*.md` を Glob。見つからなければ error として中止
2. **最終確認（AskUserQuestion）**: supersede は旧 ADR を superseded に落とす後戻りしにくい操作。誤った old-id 指定による別 ADR の巻き込みを防ぐため、特定した旧 ADR の id / title / 現 status を提示して実行可否を確認する:
   - question: 「ADR-<old-id>「<title>」（現 status: <status>）を superseded にして新 ADR で置き換えますか？」
   - header: 「supersede 確認」
   - options:
     1. label: 「supersede 実行 (Recommended)」 / description: 「旧 ADR を superseded に更新し、新 ADR を作成する」
     2. label: 「中止」 / description: 「何も変更しない（旧 ADR はそのまま残す）」
   - 「中止」が選ばれたら一切変更せず終了する
3. **新 ADR 作成**（Phase 3 と同手順）。ただし frontmatter の `supersedes` に `<old-id>` を入れる:
   - `{SUPERSEDES}` → `["<old-id>"]`
4. **旧 ADR を Edit**（4 箇所）:
   - `status:` → `superseded`
   - `phase:` → `superseded`
   - `superseded-by:` → `<new-id>`（新 ADR の timestamp）
   - `last-validated:` → 本日（`date +%Y-%m-%d`）
5. **両方を Read で確認**: 新 ADR の `supersedes` と旧 ADR の `superseded-by` が相互参照になっていることを検証
6. 結果を報告（例: 「旧 ADR-20260520091500 を superseded、新 ADR-20260529143012 を作成」）

> supersede は append-only 原則を守る: 旧 ADR は **削除しない**。履歴として残し、phase/status のみ更新する。

---

## Phase 5: 完了報告

```
✅ ADR <id> を作成しました

📄 .claude/adr/<timestamp>-<kebab-title>.md
  id: <timestamp>
  status: accepted
  phase: current

次のアクション:
- 「## 適用方法 (Enforcement)」を埋める（lint / test / hook 強制の可否を検討）
- 「## 検討した代替案」「## 関連」を必要に応じて補完
```

supersede 時は旧 ADR の更新結果も併記する。

---

## 処理フロー

```
1. Phase 0: .claude/adr/ 存在確認（無ければ mkdir）
2. Phase 1: サブコマンド判定（list / new / supersede）
3. Phase 2: list → frontmatter 解析 → id 降順の表
4. Phase 3: new → date +%Y%m%d%H%M%S → kebab → template Write
5. Phase 4: supersede → 新 ADR 作成 + 旧 ADR 4 フィールド更新 + 相互参照確認
6. Phase 5: 完了報告
```

---

## 注意事項

- **タイムスタンプは必ず Bash で取得**: Claude が擬似乱数 / 時刻を作らず `date +%Y%m%d%H%M%S` を実行する。秒精度でファイル名衝突を回避（`references/naming.md`）
- **適用方法 (Enforcement) セクション必須**: ADR の死に文書化を防ぐため、「lint / test / hook で機械強制できないか」を必ず検討させる欄を設ける。決定的検証で守れる決定はそちらに昇格させる
- **append-only 原則**: supersede 時も旧 ADR を削除しない。status / phase を `superseded` に更新して履歴として残す
- **doc-freshness との住み分け**: adr-keeper は ADR の作成・命名・supersede 整合のみ担当。鮮度 lint（last-validated stale 判定）は doc-freshness が `.claude/adr/` を走査して担う。frontmatter（`last-validated` / `phase`）を共通化しているので連携可能。ただし ADR は append-only 履歴文書のため `phase: current` の stale 閾値を当てると閾値経過後から恒常 stale になる。これを避けるためテンプレに `append_only: true` を付け、doc-freshness 側で stale 判定を免除させる（doc-freshness v0.2.0+）
- **status と phase の対応**: `accepted` → `phase: current`、`superseded` → `phase: superseded`。`proposed`（未決定）も許容するが、ADR は通常「決定済み」を記録するため既定は `accepted`
