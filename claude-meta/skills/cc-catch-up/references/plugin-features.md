# Claude Code プラグイン関連機能カタログ

CC Catch-Up スキルが Gap 分析で使用する、プラグイン開発に関連する Claude Code 機能の構造化リスト。
各機能には導入バージョン、適用可能性のシグナル、プラグインでの活用方法を記載する。

> **メンテナンス**: CC の新バージョンリリース時にこのファイルを更新する。
> キャッチアップ実行時に新機能が発見された場合、Phase 7 でこのカタログにも追記する。

---

## 1. Hook System

### 1.1 Hook Events

| イベント | Since | フェーズ | 説明 | 適用シグナル |
|---------|-------|---------|------|------------|
| `PreToolUse` | 初期 | ツール実行前 | ツール呼び出しをブロック/修正 | 危険操作の防止が必要なプラグイン |
| `PostToolUse` | 初期 | ツール実行後 | 結果に基づくフィードバック注入 | 自動フォーマット、lint |
| `Stop` | 初期 | ターン終了時 | セッション終了時の処理 | 学習・レビュー系プラグイン |
| `SessionStart` | 初期 | セッション開始時 | 依存チェック、ルール注入 | 外部依存があるプラグイン |
| `PostCompact` | v2.1.76 | コンパクション後 | コンテキスト再注入 | ルール/状態をコンテキストに保持するプラグイン |
| `StopFailure` | v2.1.78 | APIエラー終了時 | エラーハンドリング | エラーリカバリが必要なワークフロー |
| `CwdChanged` | v2.1.83 | CWD変更時 | 環境切り替え | プロジェクトコンテキスト依存のプラグイン |
| `FileChanged` | v2.1.83 | ファイル変更時 | 監視ファイルの変更検知 | 設定ファイル/コンテキストファイル監視 |
| `InstructionsLoaded` | v2.1.69 | CLAUDE.md読み込み時 | 指示の拡張/変換 | 動的ルール生成 |
| `ConfigChange` | v2.1.50 | 設定変更時 | 設定検証 | 設定管理プラグイン |
| `WorktreeCreate` | v2.1.50 | ワークツリー作成時 | 環境セットアップ | ワークツリー使用プラグイン |
| `WorktreeRemove` | v2.1.50 | ワークツリー削除時 | クリーンアップ | ワークツリー使用プラグイン |
| `TaskCreated` | v2.1.84 | タスク作成時 | タスクのバリデーション/拡張 | タスク管理プラグイン |
| `TaskCompleted` | v2.1.84 | タスク完了時 | 完了時処理 | ワークフロー管理プラグイン |
| `Elicitation` | v2.1.76 | MCP エリシテーション要求時 | エリシテーション制御 | MCP 連携プラグイン |
| `ElicitationResult` | v2.1.76 | エリシテーション応答後 | 応答処理 | MCP 連携プラグイン |
| `TeammateIdle` | v2.1.84+ | チームメイトアイドル前 | タスク割り当て | マルチエージェント系 |
| `PermissionDenied` | v2.1.89 | auto mode denial 後 | リトライ制御 | auto mode 活用プラグイン |
| `SessionEnd` | v2.1.74+ | セッション終了時 | クリーンアップ処理 | セッション終了時の後処理が必要なプラグイン |
| `SubagentStart` | v2.0.43 | サブエージェント起動時 | 初期化処理 | エージェントチーム構成時 |
| `SubagentStop` | v1.0.41+ | サブエージェント停止時 | 完了時処理 | エージェント完了後のクリーンアップ |
| `PermissionRequest` | v2.0.45+ | 権限リクエスト時 | カスタム承認フロー | 承認フロー制御プラグイン |

### 1.2 Hook Handler Types

| タイプ | Since | 説明 | 適用シグナル |
|-------|-------|------|------------|
| `command` | 初期 | シェルコマンド実行 | 汎用（デフォルト） |
| `prompt` | 初期 | LLM に yes/no 判定させる | 複雑な条件判定が必要な場合 |
| `agent` | v2.1.50+ | ツールアクセス付きサブエージェント検証 | 高度な検証ロジック |
| `http` | v2.1.63 | URL に POST JSON → レスポンスで制御 | 外部サービス連携 |

### 1.3 Hook Fields

| フィールド | Since | 説明 | 適用シグナル |
|-----------|-------|------|------------|
| `if` | v2.1.85 | パーミッション構文での条件絞り込み | PreToolUse/PostToolUse でツール名フィルタ |
| `once` | v2.1.80+ | セッション中1回のみ実行 | 依存チェック等の初回のみ処理 |
| `async` | v2.1.76+ | バックグラウンド非同期実行 | ブロック不要な通知/ログ系 |
| `matcher` | v2.1.83 | FileChanged イベントのファイル名パターン | 特定ファイル監視 |
| `timeout` | 初期 | タイムアウト(ms) | 外部コマンド実行 |

### 1.4 Hook Capabilities

| 機能 | Since | 説明 | 適用シグナル |
|------|-------|------|------------|
| `updatedInput` | v2.1.85 | PreToolUse で入力パラメータを書き換え | 危険コマンドの安全化 |
| `CLAUDE_ENV_FILE` | v2.1.78+ | SessionStart/CwdChanged/FileChanged で環境変数を永続化 | セッション変数の保持 |
| `last_assistant_message` | v2.1.47 | Stop/SubagentStop で最終アシスタントレスポンス参照 | トランスクリプト解析不要の応答取得 |
| `permissionDecision: "defer"` | v2.1.89 | PreToolUse で判断を保留し `-p --resume` で再評価 | ヘッドレス CI/CD パイプライン |
| AskUserQuestion 自動回答 | v2.1.85 | PreToolUse で `updatedInput` + `permissionDecision: "allow"` | ヘッドレス環境での自動応答 |
| 大容量出力のディスク保存 | v2.1.89 | 50K 文字超の hook 出力はファイルに保存 | 大量データ返却フック |

---

## 2. Agent System

### 2.1 Agent Frontmatter Fields

| フィールド | Since | 説明 | 適用シグナル |
|-----------|-------|------|------------|
| `name` | 初期 | エージェント名 | 必須 |
| `description` | 初期 | 説明 | 必須 |
| `model` | 初期 | モデル指定 | タスク複雑度に応じた選択 |
| `effort` | v2.1.80 | エフォートレベル | タスク複雑度に応じた設定 |
| `tools` | 初期 | 使用可能ツール | 最小権限原則 |
| `disallowedTools` | v2.1.80+ | 拒否ツールリスト | ツールの明示的ブロック |
| `maxTurns` | v2.1.78+ | 最大ターン数 | 暴走防止 |
| `background` | v2.1.80+ | バックグラウンド実行 | 並列処理、ノンブロッキング |
| `isolation` | v2.1.50 | `"worktree"` で分離実行 | 破壊的操作の分離 |
| `memory` | v2.1.80+ | `user`/`project`/`local` メモリスコープ | 永続的な学習 |
| `mcpServers` | v2.1.80+ | エージェント固有 MCP サーバー | 特定 API 連携 |
| `skills` | v2.1.80+ | プリロードスキル | スキル依存エージェント |
| `initialPrompt` | v2.1.83 | `--agent` 起動時の自動送信プロンプト | スタンドアロンエージェント |
| `permissionMode` | v2.0.43 | エージェントの権限モード指定 | エージェントの自律度制御 |
| `hooks` | v2.1.0 | エージェント固有フック定義（Stop → SubagentStop 自動変換） | エージェント固有の後処理 |

---

## 3. Skill System

### 3.1 Skill Frontmatter Fields

| フィールド | Since | 説明 | 適用シグナル |
|-----------|-------|------|------------|
| `name` | 初期 | スキル名 | 必須 |
| `description` | 初期 | 説明（トリガーフレーズ含む） | 必須 |
| `effort` | v2.1.80 | エフォートレベル | タスク複雑度設定 |
| `allowed-tools` | 初期 | 使用可能ツール | 最小権限 |
| `paths` | v2.1.84 | glob パターンで自動アクティベーション | ファイルタイプ依存スキル |
| `context` | v2.1.80+ | `fork` でサブエージェント分離実行 | メインコンテキスト保護 |
| `agent` | v2.1.80+ | `context: fork` 時のエージェントタイプ | フォーク実行のカスタマイズ |
| `hooks` | v2.1.80+ | スキルスコープのフック | スキル実行中のみ有効なフック |
| `shell` | v2.1.84 | `bash` / `powershell` 指定 | クロスプラットフォーム |

### 3.2 Skill 制約

| 制約 | Since | 説明 | 適用シグナル |
|------|-------|------|------------|
| description 250 文字上限 | v2.1.86 | description が 250 文字でキャップ | トリガーフレーズを優先的に含める |
| `disableSkillShellExecution` | v2.1.91 | インラインシェル実行を無効化する設定 | セキュリティ要件の厳しい環境 |

### 3.3 Skill Variables

| 変数 | Since | 説明 | 適用シグナル |
|------|-------|------|------------|
| `${CLAUDE_PLUGIN_ROOT}` | 初期 | プラグインルートパス | パス参照（必須） |
| `${CLAUDE_SKILL_DIR}` | v2.1.69 | SKILL.md のディレクトリパス | references/ への相対パス |
| `${CLAUDE_PLUGIN_DATA}` | v2.1.78 | プラグイン永続データディレクトリ | 状態保存・キャッシュ |
| `${CLAUDE_SESSION_ID}` | v2.1.69+ | 現在のセッション ID | セッション追跡 |
| `$ARGUMENTS` / `$N` | v2.1.69+ | コマンド引数 | 引数付きコマンド |

---

## 4. Command System

### 4.1 Command Frontmatter Fields

| フィールド | Since | 説明 | 適用シグナル |
|-----------|-------|------|------------|
| `description` | 初期 | コマンド説明 | 必須 |
| `allowed-tools` | 初期 | 使用可能ツール | 最小権限 |
| `argument-hint` | 初期 | 引数ヒント表示 | 引数付きコマンド |
| `shell` | v2.1.84 | シェル指定 | クロスプラットフォーム |

---

## 5. Plugin Manifest (plugin.json)

| フィールド | Since | 説明 | 適用シグナル |
|-----------|-------|------|------------|
| `name` | 初期 | プラグイン名 | 必須 |
| `version` | 初期 | セマンティックバージョン | 必須 |
| `description` | 初期 | プラグイン説明 | 必須 |
| `author` | 初期 | 作者情報 | 必須 |
| `agents` | v2.1.50+ | エージェント一覧 | agents/ ディレクトリ使用時 |
| `userConfig` | v2.1.69+ | ユーザー設定項目 | カスタマイズ可能なプラグイン |
| `channels` | v2.1.80+ | MCP メッセージチャンネル | リアルタイム通知 |
| `_requirements` | 慣習 | 依存情報（非公式） | 外部依存があるプラグイン |
| `bin/` | v2.1.91 | CLI ツール同梱ディレクトリ | Bash から直接呼び出せるツール配布 |
| `source: 'settings'` | v2.1.80 | settings.json 内インライン定義 | git 不要のプラグイン定義 |
| `git-subdir` | v2.1.84 | git リポジトリのサブディレクトリ指定 | モノレポ内プラグイン参照 |

### 5.1 userConfig

```json
{
  "userConfig": {
    "key_name": {
      "description": "説明",
      "required": true,
      "sensitive": false,
      "default": "値"
    }
  }
}
```

- `sensitive: true` でキーチェーン保存（API キー等）
- `${user_config.KEY}` でスキル/コマンド内から参照

---

## 6. MCP Integration

| 機能 | Since | 説明 | 適用シグナル |
|------|-------|------|------------|
| エリシテーション | v2.1.76 | MCP サーバーがインタラクティブ UI を要求 | MCP 連携プラグイン |
| エージェント固有 MCP | v2.1.80+ | エージェントフロントマターで MCP 定義 | エージェント専用の外部連携 |
| ツール説明 2KB 上限 | v2.1.84 | MCP ツール説明のサイズ制限 | MCP ツール提供プラグイン |
| サーバー重複排除 | v2.1.84 | ローカル/リモート設定の自動重複排除 | MCP 設定管理 |
| `CLAUDE_CODE_MCP_SERVER_NAME` | v2.1.85 | MCP サーバー名の環境変数 | MCP スクリプト内参照 |
| Tool result persistence | v2.1.91 | `_meta["anthropic/maxResultSizeChars"]` で最大 500K 保持 | 大規模 MCP 結果のトランケート防止 |

---

## 7. Runtime & CLI

| 機能 | Since | 説明 | 適用シグナル |
|------|-------|------|------------|
| `/reload-plugins` | v2.1.69 | セッション中プラグイン再読み込み | 開発時ホットリロード |
| `--worktree` (`-w`) | v2.1.49 | ワークツリー分離実行 | CI/並列実行 |
| `--bare` | v2.1.81 | 軽量モード | スクリプト用 |
| `claude agents` | v2.1.50 | エージェント一覧 CLI | エージェント管理 |
| Cron (`CronCreate` 等) | v2.1.71 | スケジュールタスク | 定期実行 |
| LSP サーバー (.lsp.json) | v2.1.80+ | 言語サーバー提供 | コード補完・診断プラグイン |
| `settings.json` 同梱 | v2.1.50 | プラグインに設定ファイルを同梱 | エージェント設定の配布 |

---

## 8. 環境変数

| 変数 | Since | 説明 | 適用シグナル |
|------|-------|------|------------|
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` | v2.1.78+ | サブプロセスから認証情報除去 | セキュリティ考慮 |
| `CLAUDE_STREAM_IDLE_TIMEOUT_MS` | v2.1.80+ | ストリーミングタイムアウト | 長時間処理 |
| `CLAUDE_CODE_DISABLE_CRON` | v2.1.71+ | スケジュール無効化 | Cron 制御 |
| `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` | v2.1.78 | 組み込みコミット/PR 指示を除去 | dev-workflow 等との競合防止 |
