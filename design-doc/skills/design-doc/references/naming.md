# 命名規約・改訂 vs supersede の判断基準

design doc のファイル命名と、既存 doc に変更を加えるときの「改訂 / supersede / 別 doc」の境界。

## ファイル名フォーマット

```
.claude/designs/<YYYYMMDD>-<kebab-case-slug>.md
```

例:
```
.claude/designs/20260611-payment-retry-architecture.md
.claude/designs/20260603-knowledge-graph-storage.md
```

| 要素 | 例 | 規則 |
|---|---|---|
| `<YYYYMMDD>` | `20260611` | 日付精度。Bash `date +%Y%m%d` で取得 |
| `<kebab-case-slug>` | `payment-retry-architecture` | 小文字 kebab-case、英語の要約 slug。3〜5 語程度 |

## id

frontmatter の `id` は **ファイル名から `.md` を除いた値をそのまま**使う（相互参照のキーになるため必ず一致させる）。

```yaml
id: 20260611-payment-retry-architecture
```

## なぜ日付精度か（ADR の秒精度と変える理由）

- ADR は「1 日に複数件あり得る点の記録」なので秒精度（`YYYYMMDDhhmmss`）で衝突を回避している
- design doc は「機能名・テーマ名で参照される面の記録」なので、**可読な slug を主キー**にし、日付は作成時期の手がかりに留める
- 同日同 slug の衝突（実用上ほぼ発生しない）は Glob で検出し、末尾に `-2` サフィックスを付ける

## kebab slug の作り方

- タイトル（日本語可）から **英語の要約 slug** を作る。romaji 化はしない（`kessai-retry` ではなく `payment-retry`）
- frontmatter `title` / 本文見出しには**原文タイトル**をそのまま残す。kebab 化はファイル名と id だけ

## 日付は必ず Bash で取得

```bash
date +%Y%m%d    # ファイル名・id 用
date +%Y-%m-%d  # last-validated 用
```

Claude が擬似日付を作らない（adr-keeper と同じ規律）。

---

## 改訂 vs supersede vs 別 doc の判断基準

既存 doc に手を入れるときは、変更の性質で 3 つを使い分ける。

| 操作 | いつ | やること |
|---|---|---|
| **改訂** | 採用方式は変わらず、詳細化・追記・誤り修正をする | 既存 doc を Edit + `last-validated` を更新。新ファイルは作らない |
| **supersede** | 採用方式そのものを転換する（旧設計が無効になる） | 新 doc 作成（`supersedes` 記入）+ 旧 doc の 4 箇所更新（status / phase / superseded-by / last-validated）。旧 doc は削除しない |
| **別 doc** | スコープが別物（同じ領域の別テーマ） | 独立した doc を新規作成。「関連」セクションで相互リンク |

### 判断の問い

1. 「旧 doc の採用案に従って実装したら間違いになるか？」
   - YES → **supersede**（旧設計はもう従ってはいけない）
   - NO → 改訂 or 別 doc
2. 「変更後も doc のゴールは同じか？」
   - YES → **改訂**
   - NO → **別 doc**

### `phase: target` の間は生きた文書

design doc は ADR と違い、設計中（`phase: target`）は本文編集が前提の「生きた文書」。append-only 原則が禁じるのは「supersede 時の旧 doc 削除」であって日常の編集ではない。

- `phase: target`（未実装）: 自由に改訂してよい。改訂のたびに `last-validated` を更新
- `phase: current`（実装済）: as-built 記録。実装と乖離する編集は改訂ではなく supersede を検討
- `phase: superseded`: 編集禁止（履歴）。active doc から参照しない（doc-freshness が検出）

## status と phase の対応

| status | 意味 | 典型的な phase |
|---|---|---|
| `draft` | 設計中・合意前 | `target` |
| `approved` | 設計合意済み（実装待ち or 実装済み） | `target`（実装前）→ `current`（実装後） |
| `superseded` | 方式転換で無効化 | `superseded` |

status（合意状態）と phase（実装ライフサイクル）は別次元。「approved だが未実装」は `status: approved` + `phase: target`。
