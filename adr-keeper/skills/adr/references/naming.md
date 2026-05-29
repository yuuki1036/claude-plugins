# 命名規約（ファイル名・id）

ADR ファイルの命名と id の生成規約。

## ファイル名フォーマット

```
.claude/adr/<timestamp>-<kebab-case-title>.md
```

例:
```
.claude/adr/20260529143012-api-versioning-strategy.md
.claude/adr/20260520091500-auth-method-selection.md
```

| 要素 | 例 | 規則 |
|---|---|---|
| `<timestamp>` | `20260529143012` | `YYYYMMDDhhmmss`（秒精度）。Bash `date +%Y%m%d%H%M%S` で取得 |
| `<kebab-case-title>` | `api-versioning-strategy` | 小文字 kebab-case、英語の要約 slug。語間ハイフン |

## id

frontmatter の `id` は **ファイル名のタイムスタンプ部分をそのまま**使う。

```yaml
id: 20260529143012
```

> Issue #46 の表記例では `20260529T...` のように `T` 区切りも示されているが、ファイル名と id は **同一値**にする（相互参照のキーになるため）。実装ではファイル名の timestamp と frontmatter の `id` を必ず一致させる。

## タイムスタンプは必ず Bash で取得

Claude が擬似乱数 / 現在時刻を勝手に生成しない。必ず Bash で実時刻を取る:

```bash
date +%Y%m%d%H%M%S    # ファイル名・id 用
date +%Y-%m-%d        # last-validated 用
```

### なぜ秒精度か（衝突回避）

- 日付のみ（`YYYYMMDD`）だと、同日に複数 ADR を作ると衝突する
- 分精度（`YYYYMMDDhhmm`）でも、立て続けの記録で衝突しうる
- **秒精度**なら 1 秒以内に 2 件作らない限り衝突しない。ADR は人手で 1 件ずつ記録するため、秒精度で実用上十分
- 連番（ADR-0001 形式）も検討したが、**既存最大番号の探索が必要**でブランチ並行作業時に衝突しやすい。タイムスタンプは探索不要かつ並行作業に強い

### 衝突時のフォールバック

万一同一秒で衝突した場合（Glob で同名検出）、末尾に `-2` 等のサフィックスを付ける。通常運用では発生しない。

## kebab タイトルの作り方

- ADR のタイトル（日本語でも可）から **英語の要約 slug** を作る
- romaji 化はしない（`ninsho-hoshiki` ではなく `auth-method` のように英語化）
- 3〜5 語程度に収める。長すぎる slug はファイル名の可読性を下げる
- frontmatter / 本文見出しの `{TITLE}` には**原文タイトル**（日本語可）をそのまま残す。kebab 化はファイル名だけ

例:
| タイトル（原文） | kebab slug | ファイル名 |
|---|---|---|
| API バージョニング方針 | `api-versioning-strategy` | `20260529143012-api-versioning-strategy.md` |
| 認証方式の選定 | `auth-method-selection` | `20260520091500-auth-method-selection.md` |
