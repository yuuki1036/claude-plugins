---
name: init
description: >
  Linear プロジェクトの初期セットアップ。ディレクトリ構造を作成し、
  Linear MCP からプロジェクト情報を取得してプロジェクト doc を生成する。
  トリガー: 「プロジェクト初期化」「init」「セットアップ」「新しいプロジェクト」「/init」
effort: low
allowed-tools:
  - mcp__linear__list_projects
  - mcp__linear__get_project
  - Read
  - Write
  - Glob
  - Bash
---

# Init

Linear プロジェクトの初期セットアップを行い、ディレクトリ構造を作成する。

## ワークフロー

### Phase 0: Linear MCP 利用可能性チェック

1. `mcp__linear__list_projects` の呼び出しを試みる（Phase 3 でも使うため兼用）
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行するとディレクトリ構造のみ作成されます（プロジェクト doc の生成はスキップ）。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "ディレクトリ構造のみ作成する（Linear 情報なし）"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Phase 3 の Linear 取得をスキップし、Phase 4 に直接進む
3. 正常に応答が返った場合: 結果を Phase 3 で再利用し、そのまま Phase 1 に進む

### Phase 1: プロジェクトスラッグの決定

1. 引数でプロジェクトスラッグが指定されている場合はそれを使用する
2. 指定がない場合はユーザーに確認する
   - スラッグは Issue ID のプレフィックスを小文字化したもの（例: `TEAM` → `team`）
3. スラッグは小文字英数字とハイフンのみ許可する

### Phase 2: 既存ディレクトリの確認

1. `.claude/linear/{slug}/` の存在を確認する（Glob）
2. 既に存在する場合:
   - 「`.claude/linear/{slug}/` は既に存在します。初期化済みのプロジェクトです。」とエラーを報告して終了する
   - 上書きや再初期化は行わない

### Phase 3: Linear プロジェクト情報の取得（任意）

1. Linear MCP `list_projects` でプロジェクト一覧を取得する
2. スラッグに対応するプロジェクトを特定する
   - チーム識別子（スラッグの大文字版）に関連するプロジェクトを探す
3. 対応するプロジェクトが見つかった場合:
   - `get_project` で詳細情報を取得する
4. 取得できなかった場合（MCP 未接続・プロジェクト未発見など）:
   - 「Linear からプロジェクト情報を取得できませんでした。ディレクトリ構造のみ作成します。」と通知する
   - Phase 4 に進む（プロジェクト doc 作成はスキップ）

### Phase 4: ディレクトリ構造の作成

1. 以下のディレクトリ・ファイルを作成する（Bash）:

```
.claude/linear/{slug}/
├── projects/          # プロジェクト doc 格納ディレクトリ
├── issues/            # Issue ファイル格納ディレクトリ
└── knowledge/         # 知見格納ディレクトリ
```

2. 各ディレクトリに `.gitkeep` を配置して空ディレクトリを保持する

### Phase 5: プロジェクト doc の生成

Phase 3 で Linear プロジェクト情報を取得できた場合のみ実行する:

1. テンプレートを読み込む（Read）
   - `${CLAUDE_SKILL_DIR}/../linear-maintain/references/project-doc-template.md`
2. テンプレートの形式に従ってプロジェクト doc を生成する
   - 配置先: `.claude/linear/{slug}/projects/{プロジェクト名のスラッグ}.md`
   - Linear から取得した情報（プロジェクト名、description、ステータス、リード、優先度）を反映する
   - 「関連 Issue」テーブルは空の状態にする
3. 生成した内容をユーザーに提示し、承認を得てから書き込む

### Phase 6: 完了報告

1. 作成したディレクトリ・ファイルの一覧を報告する
2. 次のアクションを案内する:
   - `/session-start` でセッション開始
   - `/issue-create {ISSUE-ID}` で Issue ファイル作成
