# Story Naming（ディレクトリ命名規約）

user story ディレクトリの命名規約と短縮モードの定義。

## デフォルト: 日本語フルパス

```
features/Userは、{role}として、{want}したい/
```

例:
```
features/Userは、契約管理者として、契約書を一括承認したい/
features/Userは、営業担当として、見積もりをPDFで出力したい/
```

### 利点

- **`ls features/` で全機能カタログ**: ディレクトリ名を読むだけで概念が伝わる
- **LLM agent が読み違えにくい**: user story 文がそのまま path に出るため、Scenario との対応が崩れにくい
- **新規参入者が辿りやすい**: 仕様の入口が「読める」

### 欠点

- **Windows MAX_PATH（260 文字）に注意**: 長い user story + 深いネストで超過する可能性
- **一部 CI / Docker 環境で日本語パスがエスケープ問題**: GitHub Actions windows-latest 等で稀に発生
- **タブ補完で苦労する**: ターミナル操作で `cd features/U` まで打ってもインクリメンタル絞り込みが効きづらい

## 短縮モード: `{role}-{verb}-{object}`

`.claude/bdd-spec.json` で `shortPath: true` に設定すると短縮モードに切り替わる。

```
features/{role}-{verb}-{object}/
```

例:
```
features/contract-admin-approve-contracts/
features/sales-export-quotes-pdf/
```

### 命名規則（短縮モード）

| 要素 | 例 | 規則 |
|---|---|---|
| `{role}` | `contract-admin` / `sales` / `viewer` | kebab-case、英語、3 単語以内 |
| `{verb}` | `approve` / `create` / `list` / `export` / `update` | 英語動詞原形 |
| `{object}` | `contracts` / `reports` / `quotes-pdf` | 複数形、対象を明示 |

### 利点

- **Windows / CI 完全互換**
- **タブ補完が効く**
- **ファイル名が ASCII 完結**

### 欠点

- **`ls` だけでは何の機能か分かりにくい**: `contract-admin-approve-contracts` を見ても user story 全文は補完が必要
- **role / verb / object の語彙が揺れる**: `update` vs `edit`、`list` vs `index` など
- **同義語による衝突リスク**: `approve-contracts` と `approve-contract` のような表記揺れ

## 短縮モード採用時の補完規約

短縮モード（`shortPath: true`）採用時は **spec.md 冒頭に user story 全文を併記**する:

```markdown
<!-- spec.md 冒頭 -->
# Feature: 契約書を一括承認する

> User story: Userは、契約管理者として、契約書を一括承認したい

## Background

...
```

これにより、ディレクトリ名が短縮されていても spec.md を開けば user story 全文が読める。

## 衝突解消ルール

同名ディレクトリが既に存在する場合（Phase 2 で検出）:

1. **別名で作成**: サフィックス `-v2` / `-v3` を付加
2. **上書き**: 既存 epic.md / spec.md を上書き（事前承認必須）
3. **中止**: scaffold を中止

> 自動上書きはしない。常に AskUserQuestion で承認を取る。

## NG パターン

❌ **大文字始まりの英語 + 日本語混在**:
```
features/ContractAdminは、契約書を一括承認したい/   # NG: 半分英語
features/contractAdminは、契約書を承認したい/       # NG: 同上
```

→ 日本語フルパスなら全部日本語、短縮モードなら全部英語で統一する。

❌ **want 部分が動詞句で完結しない**:
```
features/Userは、管理者として、ダッシュボード/   # NG: 動詞欠落
```

→ 必ず「〜したい」「〜する」など動詞句で締める。

❌ **shortPath で {verb} が形容詞**:
```
features/admin-bulk-contracts/   # NG: bulk は形容詞
features/admin-approve-bulk-contracts/   # OK: approve が動詞
```

## 設計判断

- **日本語をデフォルトにした理由**: 観察事例で日本語 user story がそのまま path になっている運用が「`ls` で機能カタログ」「LLM 読み違いが少ない」と評価されたため。互換性を取る場合のみ短縮モードを使う
- **`Userは、〜したい` の固定句にした理由**: 全 story が同じ語頭で揃うと `ls` の視認性が高い。`As a 〜 I want to 〜` 英語版も検討したが、日本語プロジェクトでは混在のメリット薄
- **shortPath での `{verb}-{object}` 順**: 英語の SVO 順に従い、`role` の次は動詞、最後に目的語。`{object}-{verb}` は英語として違和感がある
