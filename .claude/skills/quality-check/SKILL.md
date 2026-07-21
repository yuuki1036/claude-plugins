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
  - Skill
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

全 hook スクリプト `{plugin}/hooks/scripts/*.sh` に対して:

- `safe-hook.sh` を source し `safe_hook_init` を呼んでいるか確認（これが stdin 消費を担保する）
- 生の `cat > /dev/null` だけで終わっている旧式スクリプトは Warning（段階移行期間のため）
- `source` も `cat > /dev/null` もなければ Critical（ハング確定）

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

**14b. 未使用ツール検出（決定的スクリプトに委譲）**

中核は `validate_plugin_quality.py` の `check_allowed_tools_minimality()` が決定的に実行する（非ブロッキング warning として出力。exit code には影響しない）。`/quality-check` 実行時はこのスクリプト出力を読み、`要確認` 項目のみ LLM/人手で最終判断する。

- frontmatter で宣言されたツール名が、ファイル本文で一度も言及されていない場合に warning
- 検出方法（スクリプトが実装）:
  1. frontmatter を YAML / カンマ区切りの両形式でパース（`parse_tools()` 流用）
  2. 本文（frontmatter を除いた部分）を単語境界でリテラルマッチ
  3. マッチしないツールを未使用候補として報告
- 対象は **SKILL.md と agents/\*.md のみ**。`commands/*.md` は除外する（command のツールはペア一致ルールで skill にミラーされる宣言であり、スタブ的なコマンド本文に対する未使用判定は構造的に偽陽性になるため）
- 偽陽性の段階分け:
  - `Bash`: 本文にシェルコマンドの痕跡（fence 言語 / `$(` / 代表的コマンド先頭）があれば使用とみなす → なければ `要確認`（`rm`/`mv` 等が「削除」など日本語で記述される場合があるため断定しない）
  - `Read` / `Write` / `Edit` / `Glob` / `Grep` 等のファイル操作系: 日本語表現の可能性があるため `要確認`（断定しない）
  - MCP ツール（`mcp__...`）: 記述的言及の可能性があるため `要確認`
  - その他（`Agent` / `Task` / `WebFetch` / `WebSearch` / `TodoWrite` / `AskUserQuestion` 等）: `未使用候補`（高確度）
- 未使用候補は「削除候補」として列挙するのみ。自動削除はしない

**正規化ルール**:
- YAML リスト形式（`- Read`）とカンマ区切り形式（`Read, Glob, Grep`）の両方をサポート
- ツール名の前後空白をトリム

### 15. safe-hook.sh 同期チェック（Critical）

hook 共通ラッパーの正本と複製が byte-identical であることを検証する。

**対象**:

- 正本: `.claude-plugin/lib/safe-hook.sh`
- 複製: 各プラグインの `{plugin}/hooks/lib/safe-hook.sh`（hooks/ を持つプラグインのみ）

**チェック**:

- 正本ファイルが存在するか
- hooks/ を持つ全プラグインに `hooks/lib/safe-hook.sh` が存在するか
- 複製が正本と byte-identical か（`diff` または `md5`/`sha256` で比較）

**不一致は hook の挙動が予測不能になるため Critical。** 正本を修正したら全複製を同期する。

### 15b. routing-axes 同期チェック（Critical）

spec ルーティング 3 軸コア（WHAT→bdd-spec / HOW→design-doc / WHY→adr-keeper）の正本と消費サイトの delimiter 区間が一致することを検証する。中核は `validate_plugin_quality.py` の `check_routing_axes_sync()` が決定的に実行する。

**対象**:

- 正本: `.claude-plugin/lib/routing-axes.md`
- 消費サイト: `spec-advisor/skills/spec-advise/references/routing-rubric.md` / `linear-workflow/skills/issue-create/SKILL.md`（Phase 5）/ `indie-workflow/skills/indie-issue-create/SKILL.md`（Phase 8）

**チェック**:

- 各ファイルに `<!-- ROUTING-AXES:START -->` / `<!-- ROUTING-AXES:END -->` マーカーが**各1回**存在するか
- マーカー区間の内容が **dedent 後に**正本と一致するか（消費サイトはリスト内などで一様なインデントを付けてよい。それ以外の差分は fail）

**不一致は軸→プラグイン対応のサイレントなドリフトを生むため Critical。** 区間を編集するときは正本と全消費サイトを同時更新する。区間外の type 別判定・拡張軸は各サイトの文脈特化で比較対象外（設計判断: `.claude/designs/20260708-spec-routing-ssot.md`）。

### 15c. linear/indie ミラー対称性チェック（Warning）

linear-workflow と indie-workflow はミラー構造（共通機能は片方の変更を必ず他方へ対称反映する規約）。片側だけに skill が追加・削除される「取り残し」を機械検出する。中核は `validate_plugin_quality.py` の `check_mirror_symmetry()` が決定的に実行する（非ブロッキング warning）。

**対応表（正本はスクリプト内）**:

- `MIRROR_SKILL_PAIRS`: 命名が異なるミラーペア（linear skill 名 → indie skill 名。例 `issue-create` → `indie-issue-create` / `session-start` → `indie-start`）
- `MIRROR_INTENTIONAL_LINEAR_ONLY`: linear のみの意図的非対称（`dashboard` = indie-start が兼務）
- `MIRROR_INTENTIONAL_INDIE_ONLY`: indie のみの意図的非対称（`indie-issue-discover` / `retrospective`）

**検出内容**:

- **ペアの片側欠落**: 対応表にあるのに一方の SKILL.md が存在しない（取り残し疑い）
- **未分類 skill**: 対応表にも except にも載らない skill（新規に片側だけ追加された疑い）→ 対称実装するか対応表/except に登録
- **対応表/except の stale**: 登録されているが実在しない skill（掃除対象）

**対象範囲**: skill の存在・分類の対称性に絞る。構造差分（Phase 構成・dormant 連携・frontmatter フィールド）は偽陽性が多いため対象外で人手判断に残す（段階導入の余地）。片方のプラグインが未導入なら検証しない（後方互換・プラグイン独立性）。

### 16. 変更差分のセルフレビュー（条件付き）

静的整合性チェック（項目 0〜15）は frontmatter・同期・構造を検証するが、**変更したコード/スクリプトの実質的な品質（バグ・退行・設計判断・サイレント失敗）は別軸**。**未レビューの差分**がある場合は `code-review:self-review` を呼んでレビューし、結果を本レポートに統合する。

**実行条件**:

1. レビュー対象を求める。**working tree だけでなく未 push コミットも含める**:
   ```bash
   REVIEW_BASE=""
   # 未 push コミット（コミット済み = working tree はクリーンでもレビュー未実施でありうる）
   if git rev-parse --verify -q "@{upstream}" >/dev/null 2>&1 \
     && [ -n "$(git log --oneline @{upstream}..HEAD)" ]; then
     REVIEW_BASE="@{upstream}"
   fi
   DIRTY="$(git status --porcelain)"
   ```
2. `REVIEW_BASE` が空 かつ `DIRTY` が空なら skip（レビュー対象なし）。どちらかがあれば実行し、**self-review には `REVIEW_BASE` を引数で渡す**（未 push 分を差分に含めるため。空なら引数なしで自動検出）

> **working tree だけを見ないこと。** 旧実装は `git status --porcelain` のみで判定していたため、**コミット済み・未 push・未レビューの差分が丸ごと対象外**になっていた。2026-07-21 に実際にこれを踏み、5 コミット（+652/-193）が未レビューのまま push 待ちで残っていたのを手動で気づいて拾った。push 前ゲートとして使うなら未 push 分こそ主対象。
3. `code-review` プラグインの有効性を判定（後方互換・プラグイン独立性のため）。**キー存在だけを見ると無効化（`":false"`）でも文字列が残り誤検知し、project-scoped 有効化を取りこぼす**（#74 と同根）。グローバル + プロジェクトローカルの settings を見て、`":true"` を明示マッチする:
   ```bash
   HAS_REVIEW=0
   for f in "$HOME/.claude/settings.json" "$PWD/.claude/settings.json" "$PWD/.claude/settings.local.json"; do
     grep -Eq '"code-review@[^"]*"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null && HAS_REVIEW=1
   done
   ```
   `HAS_REVIEW=0` の場合は warning（「code-review 未インストール / 無効のためセルフレビューを skip」）を出して skip する

**実行方法**:

- `Skill` tool で `code-review:self-review` を起動する（引数なし＝ベースブランチ自動検出。静的チェックの後に実行し、結果が出揃ってからレポートを集約する）
- self-review は diff ベースの読み取り専用レビュー。severity × confidence でフィルタした指摘のみ返る
- 返ってきた指摘を本レポートの「セルフレビュー」節に転記する。**Critical / High の指摘があれば quality-check 全体の判定も「要対処」**とする（静的チェックが全 PASS でも、コード品質の指摘が残れば PASS としない）

> このチェックは静的バリデーションではなくランタイムのコードレビュー委譲。self-review 自体は読み取り専用なので、quality-check の「読み取り専用」原則と整合する。

---

## 実行フロー

```
1. 対象プラグインの一覧を確定
2. チェック0: 全プラグインに `claude plugin validate` を実行（Bash で一括）
3. marketplace.json を Read で読み込み
4. 各プラグインに対して並列で Agent を起動（各 Agent call に `run_in_background: false` を明示。CC 2.1.198 で既定が background になり、省略すると step 6 が agent 結果を欠いたまま集約し偽 PASS を出す）:
   a. plugin.json を Read
   b. 全コマンド・全スキルの frontmatter を Read
   c. hooks スクリプトを Read
   d. チェック項目1〜13を順に実行
5. チェック16: working tree に変更があり code-review がインストール済みなら
   `code-review:self-review` を起動して差分をレビュー（変更なし or 未インストールなら skip）
6. チェック0〜15 + Agent + セルフレビューの結果を集約してレポート出力
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

### セルフレビュー（チェック16・working tree に変更がある場合）

```md
## セルフレビュー（code-review:self-review）

対象: working tree の差分（{変更ファイル数} files）

| Severity | Confidence | ファイル:行 | 指摘 |
|----------|-----------|------------|------|
| High | 90 | foo/bar.sh:42 | {要約} |

→ Critical / High が 1 件以上あれば全体判定は「要対処」
（変更なし: 「セルフレビュー: 対象なし（skip）」 / code-review 未インストール: 「skip（warning）」）
```

---

## 注意事項

- このスキルは**読み取り専用**。問題を検出して報告するだけで、自動修正はしない（委譲する self-review も diff ベースの読み取り専用）
- 修正が必要な場合は、レポートの各項目に対して個別に対処を案内する
- 静的チェックの Critical 指摘が0件、**かつ**セルフレビュー（実行された場合）に Critical / High 指摘が0件で初めて「PASS」とする

---

## 関連: eval-runner（スキル起動の回帰テスト）

品質チェックが静的検証（ファイル・frontmatter）であるのに対し、`evals/runner.py`（または `claude-meta:eval-runner` スキル）はランタイム検証を担当する。

- スキルの description / トリガーフレーズを変更した後は eval-runner で pass^k=3 の回帰テストを推奨
- `/quality-check` 自体では eval は自動実行しない（時間・API コストのため）
- Critical/Warning が 0 件 かつ eval 全 PASS で「実効 PASS」とみなす運用を推奨

### 条件付きサジェスト（実行フロー末尾で判定）

`/quality-check` のレポート出力直前に、以下を判定してサジェスト文を追加する:

**frontmatter 区間（先頭 `---` 〜 次の `---`）に差分があるか**で判定する。行の書式では判定しないこと。

```bash
# 未 push コミット + working tree を対象にする（base は origin/main、無ければ HEAD）
base="$(git rev-parse --verify -q origin/main >/dev/null && echo origin/main || echo HEAD)"
for f in $(git diff --name-only "$base" -- '*SKILL.md'; git diff --name-only -- '*SKILL.md'); do
  # frontmatter の行範囲を求め、その範囲に触れる hunk があるかを見る
  end=$(awk 'NR>1 && /^---$/{print NR; exit}' "$f")
  [ -n "$end" ] || continue
  if git diff -U0 "$base" -- "$f"; git diff -U0 -- "$f"; then :; fi \
    | grep -oE '^@@ -[0-9]+(,[0-9]+)? \+([0-9]+)' | grep -oE '[0-9]+$' \
    | awk -v e="$end" '$1<=e{found=1} END{exit !found}' && echo "$f"
done
```

> **書式マッチにしないこと。** 旧実装は `^\+(description:|\s*トリガー:|\s*- 「)` で判定していたが、**48 skill 中 41 が `description: >` の折り返しブロック形式**で、継続行の変更（`+  集計前に transcript を…`）が `description:` でも `- 「` でも始まらないため検出できなかった。実際に 2026-07-21 の failure-journal 0.2.0 で description とトリガーを両方変更したのに検出 0 件だった。

出力があれば（= description / トリガーフレーズを含む frontmatter の変更が存在）、レポート末尾に以下を追加:

```md
## 推奨: eval-runner 実行

description / トリガーフレーズの変更を検出しました。回帰の有無を確認するため、
`python3 evals/runner.py --k 1 --report evals/reports/$(date +%Y%m%d-%H%M).md`
の実行を推奨します。
```

上の判定は未 push コミット（`origin/main..HEAD`）と working tree の両方を見る。`origin/main` が無い環境では `HEAD`（= working tree のみ）にフォールバックする。

### 手動呼び出し例

```bash
python3 evals/runner.py --k 1 --report evals/reports/smoke.md       # スモーク
python3 evals/runner.py --report evals/reports/$(date +%Y%m%d).md   # 本番
```
