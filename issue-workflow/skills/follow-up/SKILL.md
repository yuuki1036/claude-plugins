---
name: follow-up
description: >
  開発中に発生した follow-up タスクの記録・一覧・Issue昇格を管理する。
  トリガー: 「follow-up」「後でやる」「別タスク」「切り出し」「todo メモ」
  「フォローアップ記録」「/follow-up」「/follow-up list」「/follow-up promote」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - Skill
  - AskUserQuestion
---

# Follow-up タスク管理

## 概要

開発中に発生した follow-up タスクを低摩擦で記録し、後から Issue に昇格できる仕組み。
follow-up ファイルは `{DATA_DIR}/{slug}/follow-ups/` に配置する。

## Phase 0: backend 検出（全スキル共通）

1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/follow-up` | 新規 follow-up を作成 |
| `/follow-up new` | 新規 follow-up を作成 |
| `/follow-up list` | open な follow-up 一覧を表示 |
| `/follow-up promote [FILE]` | 指定した follow-up を Issue に昇格 |

---

## ファイルフォーマット

### 配置先

`{DATA_DIR}/{slug}/follow-ups/{YYYYMMDD}-{kebab-slug}.md`

ファイル名の `{kebab-slug}` はタイトルの kebab-case 短縮（例: `20260403-fix-null-pointer.md`）。
同日に同名ファイルが存在する場合は `-2`, `-3` のサフィックスを付加する。

### フロントマター

```yaml
---
shared_state_type: follow-up
producer: issue-workflow
consumers: [issue-workflow]
schema_version: 1
last_updated: {ISO 8601}
title: "タイトル"
status: open              # open / promoted / backlog / dismissed
type: bug                 # bug / feature / debt / investigation / idea
priority: medium          # high / medium / low
source_issue: MYAPP-3     # 元 Issue（必須）
created: YYYY-MM-DD
---
```

> Shared State 規約（CLAUDE.md 参照）に従い、shared_state_type / producer / consumers / schema_version / last_updated を付与する。consumers は dashboard / issue-maintain など同 plugin 内の skill から参照される想定（plugin 名で記述）。既存ファイルは frontmatter 不在のままでも読める後方互換を保つ。

### 本文構造

```markdown
## 内容

{問題・アイデア・やることの説明}

## 発生コンテキスト

{どんな作業中に気づいたか。コード箇所への参照があれば記載}

## 対応メモ

{対応方針の検討メモ。空欄でもよい}
```

---

## Phase 0: サブコマンド判定

1. 引数を確認する
2. `new` または引数なし → **Phase N** へ
3. `list` → **Phase L** へ
4. `promote [ファイル名]` → **Phase P** へ
5. 引数が不明な場合 → AskUserQuestion でサブコマンドを選択:
   - question: "どの操作を実行しますか？"
   - header: "Follow-up 操作"
   - options:
     1. label: "new" / description: "新規 follow-up を作成"
     2. label: "list" / description: "未処理の follow-up 一覧を表示"
     3. label: "promote" / description: "follow-up を Issue に昇格"

---

## Phase N: New（follow-up 作成）

### N1: コンテキスト特定

1. `git branch --show-current` でブランチ名を取得する（Bash）
2. ブランチ名から Issue ID を抽出する（正規表現: `[A-Z]+-\d+`）
3. Issue ID が取れない場合はユーザーに `source_issue` を入力させる
4. Issue ID プレフィックスを小文字化して slug を特定する
5. `{DATA_DIR}/{slug}/` の存在を確認。存在しない場合は `/init` への誘導で中断

### N2: 内容ヒアリング

1. ユーザーが既に説明している場合はそれを使う（重複して聞かない）
2. タイトルを確認する
3. type を自動判定し、確信が低い場合のみ AskUserQuestion:
   - question: "このタスクのタイプは？"
   - header: "タイプ"
   - options: bug / feature / debt / investigation / idea

### N3: priority 確認

- 会話から明らかな場合はスキップ
- 不明な場合は AskUserQuestion:
  - question: "優先度は？"
  - header: "優先度"
  - options: high / medium / low

### N4: ファイル生成

1. ファイル名を生成: `{YYYYMMDD}-{kebab-slug}.md`
2. 同名ファイルの衝突チェック: Glob で `{DATA_DIR}/{slug}/follow-ups/{YYYYMMDD}-{kebab-slug}*.md` を確認
3. 衝突がある場合はサフィックスを付加
4. frontmatter + 本文を生成
5. **writing-polish 連携（本文添削・必須）**: 本文を確定する前に writing-polish へ渡して推敲する。`writing-polish` がインストールされていれば**必ず**実行する。未インストール時のみ skip（プラグイン独立性のため。後方互換）。
   - インストール判定（check-deps.sh と同方式）:
     ```bash
     if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
       WRITING_POLISH=1
     else
       WRITING_POLISH=0
     fi
     ```
     `WRITING_POLISH=0` → 本ステップを skip。
   - `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を `--embed --tone issue` で呼び、本文の散文部分を渡す。
   - 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは本文に含めない）を本文の代わりに使う。ただし **frontmatter・見出し構造（内容 / 発生コンテキスト / 対応メモ）・コード箇所への参照リンクは変更しない（構造を壊す結果は破棄し元案を使う）**。変更があれば何を変えたか一言添える。
   - fallback: 呼び出し失敗時は warning を出し、添削前の本文で完了する。
6. ユーザーに内容を提示して承認を得る
7. Write でファイルを書き込む

### N5: 完了報告

- ファイルパスを報告
- 「`/follow-up list` で一覧確認、`/follow-up promote {filename}` で Issue 昇格できます」と案内

---

## Phase L: List（一覧表示）

1. `git branch --show-current` でブランチ名を取得する（Bash）
2. ブランチ名から slug を特定する。特定できない場合は全プロジェクトをスキャン
3. `{DATA_DIR}/{slug}/follow-ups/*.md` を Glob で列挙
   - slug 不明時は `{DATA_DIR}/*/follow-ups/*.md`
4. 各ファイルを Read し frontmatter を取得
5. `status: open` の follow-up を priority 降順、created 降順でソート
6. 表示形式:
   ```
   **Follow-up 一覧（{N}件）**

   | ファイル | タイトル | type | priority | source | 作成日 |
   |--------|---------|------|----------|--------|--------|
   | 20260402-fix-null.md | null チェック漏れ | bug | high | MYAPP-3 | 2026-04-02 |
   ```
7. `status: promoted` / `status: backlog` / `status: dismissed` の件数をフッターに表示
8. 件数が0の場合は「open な follow-up はありません」と表示

---

## Phase P: Promote（Issue 昇格）

### P1: 対象ファイルの特定

1. 引数でファイル名が指定されていればそれを使う
2. 未指定の場合は Phase L の一覧を表示して AskUserQuestion で選択させる

### P2: 対象ファイルの読み込み

1. Read で内容を確認し、ユーザーに表示する

### P3: テンプレート選択

1. follow-up の `type` から Issue テンプレートを推定する:
   - bug → bugfix
   - feature → feature
   - debt → debt
   - investigation → investigation
   - idea → feature
2. 確信が低い場合のみ AskUserQuestion

### P4: Issue 情報の確認

1. follow-up の「内容」と「対応メモ」を元に Issue の概要を生成
2. ユーザーに提示して承認を得る

### P4.5: 関連 Knowledge の検索

1. `{DATA_DIR}/{slug}/knowledge/index.md` の存在を確認（Read）
2. 存在する場合: follow-up のタイトル・内容からキーワードを抽出し、index.md の tags と照合
3. 関連する knowledge があれば Issue ファイル生成時に「関連 Knowledge」として参照を含める

### P5: Issue 作成の実行

1. `{DATA_DIR}/{slug}/counter.txt` を Read し、現在の番号を取得する
2. Issue ID を生成: `{SLUG大文字}-{番号}`
3. **先に `counter.txt` を +1 して Write（採番を確定）**。issue ファイル Write より前に確定することで、途中中断時に同じ番号が再採番されてファイルを上書きするのを防ぐ（issue-create / discover と同一方式）
4. P3 で選択したテンプレート（`${CLAUDE_SKILL_DIR}/../issue-create/references/{type}.md`）を Read する
5. follow-up の「内容」を概要セクション、「対応メモ」を計画セクションに反映して Issue ファイルを生成
6. 配置先: `{DATA_DIR}/{slug}/issues/{ISSUE-ID}.md`
7. ユーザーに Issue ファイル内容を提示し、承認を得てから Write（counter は step 3 で確定済みのため、ここでは触らない）
8. ブランチ作成を AskUserQuestion で確認:
   - question: "ブランチ `{type-prefix}/{ISSUE-ID}-{kebab-title}` を作成しますか？"
   - header: "ブランチ作成"
   - options:
     1. label: "作成する" / description: "ブランチを作成してチェックアウト"
     2. label: "スキップ" / description: "ブランチは自分で作る"
   - type-prefix: bugfix → `fix`、feature → `feat`、investigation → `investigate`、debt → `chore`、idea → `feat`

### P6: follow-up ファイルの更新

1. `status: promoted` に更新
2. frontmatter に昇格先を追記:
   ```yaml
   promoted_to: MYAPP-5
   promoted_date: YYYY-MM-DD
   ```

### P7: 完了報告

- 作成した Issue ファイルのパスと Issue ID を報告

---

## backlog.md との棲み分け

| | follow-up ファイル | backlog.md |
|--|--|--|
| 粒度 | ファイル1つ = メモ1つ（構造化） | 行1つ = アイデア1つ（非構造化） |
| 記録タイミング | 開発中に気づいた具体的なタスク | 思いついたアイデア・将来やりたいこと |
| Issue との関係 | 元 Issue への参照が必須 | Issue との関係は任意 |
| promote フロー | `/follow-up promote` | `/maintain` の backlog.md 整理 |

## 注意事項

- follow-up は軽量なメモ。Issue のような厳密な構造は求めない
- follow-up は `counter.txt` を使わない。Issue 昇格時に初めて採番する
- follow-ups/ ディレクトリは初回 Write 時に自動作成される
