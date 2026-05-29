# adr-keeper

設計判断 (Architecture Decision Record, ADR) を **append-only** で蓄積するプラグイン。設計判断の **WHY** を残し、supersede 時の整合を機械的に担保する。

## 使い方

```
/adr                              # ADR 一覧（id 降順）
/adr list                         # 同上
/adr new <title>                  # 新規 ADR を作成（status は既定 accepted）
/adr supersede <old-id> <new-title>  # 新 ADR 作成 + 旧 ADR を superseded に更新
```

## 保存先・命名

- ディレクトリ: `.claude/adr/`（プロジェクトローカル・committed 前提）
- ファイル名: `YYYYMMDDhhmmss-kebab-case-title.md`（秒精度で衝突回避）
- タイムスタンプは Bash `date +%Y%m%d%H%M%S` で取得（擬似時刻を作らない）

## frontmatter 規約

```yaml
---
id: 20260529143012        # = ファイル名のタイムスタンプ
status: accepted          # proposed | accepted | superseded
phase: current            # current | target | superseded
last-validated: 2026-05-29
supersedes: []            # この ADR が置き換える ADR の id 配列
superseded-by: null       # この ADR を置き換えた ADR の id（superseded 時のみ）
tags: []
---
```

`last-validated` / `phase` は doc-freshness と互換。

## 本文セクション（必須）

1. `# ADR-<id>: <title>`
2. `## ステータス`
3. `## コンテキスト / 背景`
4. `## 決定`
5. `## 影響 (Consequences)`（良い影響・悪い影響・トレードオフ）
6. `## 適用方法 (Enforcement)` ← **必須**。lint / test / hook で機械強制できないかを必ず検討して残す欄。死に文書化の予防が目的
7. `## 検討した代替案`
8. `## 関連`（関連 ADR / Issue / knowledge へのリンク・wikilink）

## サブコマンド挙動

| サブコマンド | 挙動 |
|---|---|
| `list` | `.claude/adr/*.md` を Glob → frontmatter 解析 → id / title / status / phase / last-validated の表を id 降順で表示。0 件なら「ADR がまだありません」 |
| `new <title>` | timestamp 取得 → kebab タイトル生成 → `.claude/adr/`（無ければ作成）に template から Write。status 既定 `accepted` |
| `supersede <old-id> <new-title>` | 新 ADR 作成（`supersedes: [<old-id>]`）+ 旧 ADR を Edit（`status` / `phase` / `superseded-by` / `last-validated`）+ 両方を Read で相互参照確認 |

## doc-freshness との住み分け

adr-keeper は ADR の **作成・命名・supersede 整合**のみ担当する。鮮度 lint（`last-validated` の stale 判定）は **doc-freshness** が `.claude/adr/` を走査して担う。両者は frontmatter（`last-validated` / `phase`）を共通化しているので連携できる。

| 担当 | adr-keeper | doc-freshness |
|---|---|---|
| ADR 作成 / 命名 | ✅ | - |
| supersede 整合 | ✅ | - |
| 鮮度 lint（stale 判定） | - | ✅ |

## install

```bash
# マーケットプレイスから
claude plugin install adr-keeper@yuuki1036-claude-plugins

# ローカルから
claude plugin install /path/to/claude-plugins/adr-keeper
```

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/adr` | ADR の list / new / supersede |
| スキル | `adr` | 作成・命名・supersede 整合のロジック |
