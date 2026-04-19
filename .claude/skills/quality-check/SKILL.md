---
name: quality-check
description: >
  マーケットプレイス内の全プラグインを対象にした品質チェック。
  marketplace.json 同期、allowed-tools 一致、hooks 安全性、
  ディレクトリ構造、CLAUDE.md 整合性を検証する。
  トリガー: 「品質チェック」「バリデーション」「lint」「/quality-check」
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
---

# プラグイン品質チェック

## 概要

マーケットプレイスリポジトリ内の全プラグインに対して、一貫した品質基準でバリデーションを実行する。

## 対象の特定

1. 引数でプラグイン名が指定されていればそのプラグインのみ対象
2. 未指定なら `.claude-plugin/marketplace.json` の `plugins[].name` を読み取り、全プラグインを対象

---

## チェック項目

### 0. plugin.json スキーマバリデーション（Critical）

`claude plugin validate {plugin-dir}` を各プラグインに対して実行し、スキーマエラーがないか確認。

- CLI のビルトインバリデーターが plugin.json のスキーマ整合性を検証する
- `_requirements` の "Unrecognized key" 警告は無視する（自前の拡張フィールドのため）
- それ以外のエラーがあればインストール不可のため Critical
- **このチェックで失敗したプラグインは後続チェックも実行するが、スキーマ修正が最優先**

### 1. marketplace.json 同期チェック（Critical）

各プラグインの `{plugin}/.claude-plugin/plugin.json` と `.claude-plugin/marketplace.json` の対応エントリを比較:

- `name` が一致するか
- `version` が一致するか
- `description` が一致するか

**不一致はリリース時に古い情報が配布される原因になるため Critical。**

### 2. allowed-tools 存在チェック（Critical）

全スキル `{plugin}/skills/*/SKILL.md` の frontmatter に `allowed-tools` が定義されているか確認。

- frontmatter を YAML パースし、`allowed-tools` キーの存在を確認
- 未定義の場合、ツール制限が効かないため Critical

### 3. allowed-tools 一致チェック（Critical）

コマンドとそれが参照するスキルの `allowed-tools` が完全一致するか確認。

**対応の特定方法:**
- コマンドファイル名とスキルディレクトリ名が一致するものをペアとする
- コマンド本文に別のスキル名が記載されている場合はそちらを優先

**比較方法:**
- 両方の `allowed-tools` をソートして比較
- フォーマット（リスト / カンマ区切り / JSON 配列）の違いは正規化して比較

### 4. allowed-tools フォーマット統一チェック（Warning）

`allowed-tools` の記法が YAML リスト形式になっているか確認:

```yaml
# OK: YAML リスト形式
allowed-tools:
  - Read
  - Write

# NG: カンマ区切り文字列
allowed-tools: Read, Write, Glob

# NG: JSON 配列
allowed-tools: ["Read", "Write"]
```

全コマンド・全スキルのフロントマターを走査する。

### 5. hooks 安全性チェック（Critical）

全 hook スクリプト `{plugin}/hooks/**/*.sh` に対して:

- `cat > /dev/null` による stdin 消費が含まれているか確認
- stdin を消費しないとハングする

### 6. hooks ディレクトリ構造チェック（Warning）

hook スクリプトが `hooks/scripts/` サブディレクトリ配下に配置されているか確認。

- CLAUDE.md のリポジトリ構造定義: `hooks/` 配下に `hooks.json + scripts/`
- `hooks/` 直下に `.sh` ファイルがある場合は Warning

### 7. 必須ファイル存在チェック（Critical）

各プラグインに以下が存在するか:

| ファイル | 必須 |
|---------|------|
| `.claude-plugin/plugin.json` | Critical |
| `README.md` | Critical |

### 8. スキル description トリガーフレーズチェック（Warning）

全スキル SKILL.md の `description` に「トリガー:」が含まれているか確認。

- CLAUDE.md ルール: 「スキルの description にはトリガーフレーズを含める」

### 9. references 参照整合性チェック（Warning）

各スキルの SKILL.md 本文で `${CLAUDE_PLUGIN_ROOT}` を含むパスが参照されている場合、そのファイルが実際に存在するか確認。

- `${CLAUDE_PLUGIN_ROOT}` をプラグインのルートディレクトリに置換して存在チェック

### 10. プロジェクト固有情報の混入チェック（Critical）

全プラグインファイルに以下のパターンが含まれていないか Grep:

- 実在する会社名・チーム名
- 実際の Issue ID（`CFP-`, `CPL-`, `EDH-`, `CPLFE-` など既知のプレフィックス）
- 実際のユーザー名やメールアドレス

### 11. CLAUDE.md プラグイン一覧整合性チェック（Warning）

リポジトリルートの `CLAUDE.md` のプラグイン一覧テーブルと実際のプラグイン構成を比較:

- コマンド数: `{plugin}/commands/*.md` のファイル数と一致するか
- スキル数: `{plugin}/skills/*/SKILL.md` のディレクトリ数と一致するか
- hooks: `{plugin}/hooks/hooks.json` が存在するか

### 12. _requirements 整合性チェック（Warning）

各プラグインの `plugin.json` に `_requirements` が定義されている場合:

- 各要素に `name`, `type`, `required`, `description` が存在すること
- `type` が `mcp_server` | `cli_tool` | `plugin` のいずれかであること
- `required` が boolean であること
- `name` と `description` が空でないこと
- `_requirements` が定義されている場合、対応する `hooks/scripts/check-deps.sh` が存在すること
- `check-deps.sh` が存在する場合、`cat > /dev/null` による stdin 消費が含まれていること
- `check-deps.sh` 内のチェック対象が `_requirements` の宣言と一致していること（宣言されているのにチェックされていない、またはその逆がないこと）

### 13. CLAUDE.md 品質チェック（Warning）

リポジトリルートの `CLAUDE.md` の品質を簡易評価する:

- **構造の正確性**: リポジトリ構造セクションが実際のディレクトリ構成と一致しているか
- **Gotchas の網羅性**: 既知の落とし穴が Gotchas セクションに記載されているか
- **簡潔性**: 冗長な記述や重複がないか
- **最新性**: プラグイン一覧テーブルのコマンド/スキル数が実態と一致しているか（チェック項目11と重複する部分はスキップ）
- **セクション漏れ**: 必須セクション（リポジトリ構造、プラグイン一覧、コミット規約、開発ルール、Gotchas、バージョニング）が存在するか

### 14. allowed-tools 最小性チェック（Warning）

Permission Pruning の原則に基づき、宣言されているツールが必要最小限かを検証する。過剰なツール宣言は Claude の判断精度を下げる傾向がある（Vercel / Shulex のハーネス研究を参照）。

**対象**:
- skills: `{plugin}/skills/*/SKILL.md` の `allowed-tools`
- commands: `{plugin}/commands/*.md` の `allowed-tools`
- agents: `{plugin}/agents/*.md` の `tools`

**サブチェック**:

**14a. 件数上限チェック**

- tools の件数が閾値（デフォルト `7`）を超えた場合に Warning
- 閾値はあくまで目安。正当な理由がある場合は無視可

**14b. 未使用ツール検出**

- frontmatter で宣言されたツール名が、ファイル本文で一度も言及されていない場合に Warning
- 検出方法:
  1. frontmatter を YAML / カンマ区切りの両形式でパース
  2. 本文（frontmatter を除いた部分）を Grep で単語境界マッチ
  3. マッチしないツールを未使用候補として報告
- ただし以下は偽陽性として除外:
  - `Bash`: 本文に具体的なシェルコマンドが含まれていれば使用とみなす
  - `Read` / `Write` / `Edit` / `Glob` / `Grep`: 「ファイルを読む」等の日本語表現を含む場合は人手確認を促す警告に留める
- 未使用候補は「削除候補」として列挙するのみ。自動削除はしない

**正規化ルール**:
- YAML リスト形式（`- Read`）とカンマ区切り形式（`Read, Glob, Grep`）の両方をサポート
- ツール名の前後空白をトリム

---

## 実行フロー

```
1. 対象プラグインの一覧を確定
2. チェック0: 全プラグインに `claude plugin validate` を実行（Bash で一括）
3. marketplace.json を Read で読み込み
4. 各プラグインに対して並列で Agent を起動:
   a. plugin.json を Read
   b. 全コマンド・全スキルの frontmatter を Read
   c. hooks スクリプトを Read
   d. チェック項目1〜13を順に実行
5. チェック0の結果 + Agent の結果を集約してレポート出力
```

**並列化**: 独立した3プラグイン程度ずつ Agent で並列チェック可能。ただしプラグイン数が少ない（6個）場合は直列でもよい。

---

## レポート形式

```md
# Plugin Quality Report

## サマリー
| プラグイン | Critical | Warning | Pass |
|-----------|----------|---------|------|

## 詳細

### {plugin-name}

#### Critical
- [ ] スキーマバリデーション: {結果}
- [ ] marketplace.json 同期: {結果}
- [ ] allowed-tools 存在: {結果}
- [ ] allowed-tools 一致: {結果}
- [ ] hooks stdin 消費: {結果}
- [ ] 必須ファイル: {結果}
- [ ] 固有情報混入: {結果}

#### Warning
- [ ] allowed-tools フォーマット: {結果}
- [ ] hooks ディレクトリ構造: {結果}
- [ ] トリガーフレーズ: {結果}
- [ ] references 整合性: {結果}
- [ ] CLAUDE.md 整合性: {結果}
- [ ] _requirements 整合性: {結果}
- [ ] CLAUDE.md 品質: {結果}
- [ ] allowed-tools 最小性（件数 / 未使用）: {結果}
```

---

## 注意事項

- このスキルは**読み取り専用**。問題を検出して報告するだけで、自動修正はしない
- 修正が必要な場合は、レポートの各項目に対して個別に対処を案内する
- Critical 指摘が0件で初めて「PASS」とする
