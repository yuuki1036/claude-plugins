# issue-workflow

Issue 管理ワークフロープラグイン。旧 linear-workflow / indie-workflow の統合後継で、backend（local / linear）をデータディレクトリから自動判定して単一のスキル群で両方を扱う。

## backend の考え方

| backend | データディレクトリ | 用途 |
|---------|-------------------|------|
| local | `.claude/indie/{slug}/` | ローカル完結の Issue 管理（外部サービス不要） |
| linear | `.claude/linear/{slug}/` | Linear 連携の Issue 管理（Linear MCP と同期） |

- 全スキルは起動時にデータディレクトリの存在で backend を自動判定する（設定ファイルなし）
- 判定条件は「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」。両方有効な場合はエラー停止して片寄せを案内する
- ディレクトリ名（`indie` / `linear`)は旧プラグインのデータをそのまま引き継ぐ（移行コストゼロ）

## スキル

| スキル | 説明 |
|--------|------|
| init | プロジェクト初期セットアップ（backend 選択 + ディレクトリ作成） |
| start | セッション開始。main ではダッシュボード、feature ブランチでは Issue コンテキスト読み込み |
| issue-create | Issue 作成 + ブランチ自動作成 |
| issue-design | Issue 本文を 9 セクションテンプレと設計判断ルールで設計・リライト |
| issue-maintain | Issue ファイルのセッション内容反映・品質整理・knowledge 切り出し |
| follow-up | Follow-up タスクの作成・一覧・Issue 昇格 |
| knowledge | 蓄積された知見の検索・参照 |
| knowledge-lint | knowledge グラフの健全性チェック |
| maintain | 全プロジェクトの棚卸し（放置 Issue・frozen・負債・クリーンアップ） |
| discover | AI が多観点スキャンで課題を発見して issue を自動起票 |
| retrospective | 振り返り・見積もり精度分析 |
| dashboard | Linear プロジェクトのダッシュボード表示（linear backend 専用） |
| linear-maintain | Linear MCP と同期してローカル管理ファイルを最新化（linear backend 専用） |

## agents

スキルから起動される内包 agent（単体では起動しない）。

| agent | 役割 |
|--------|------|
| code-context | Issue が言及するソースの現状と Git ブランチの作業状態を収集 |
| doc-resolver | Issue の参照リンクを辿って関連ドキュメントを読み込む |
| discover-verifier | discover の起票候補を、発見者の推論を渡さず独立にコードから検証する |
| linear-sync | Linear API から最新情報を取得しローカル Issue との差分を検出（linear backend 専用） |

## hooks

| イベント | スクリプト | 動作 |
|---|---|---|
| SessionStart / PostCompact | `inject-rules.sh` | backend を判定し、プロジェクト管理ルール・knowledge インデックス・**7 日以上更新の無い in-progress Issue** を注入する（backend 衝突時は解消手順のみ） |
| UserPromptSubmit（once） | `set-session-title.sh` | feature ブランチ名から Issue ID を拾い、セッション名を `<ID>: <title>` にする |
| PostToolUse | `check-scope-size.sh` | Issue 編集時にチェックリスト数が `scope_size` 上限を超えたら警告 |
| FileChanged | `on-issue-change.sh` / `on-knowledge-change.sh` | 外部変更を通知し、status が completed に遷移したら `issue:completed` を publish |
| SessionStart | `check-deps.sh` | 依存（Linear MCP 等）の充足を確認 |

## 主な機能

- 放置 Issue 検知・スコープ管理（`scope_size`: small 3 / medium 7 / large 15。超過はリアルタイム警告）
- 技術的負債トラッキングと定期棚卸し
- knowledge の蓄積（source / concept / rejected の 3 種 + wikilink）と健全性 lint。rejected（却下記録）は「対応しない」と決めた提案を理由付きで永続化し、discover の再提案を機械的に抑止する
- AI 主導の課題発見（discover。起票前に外部オラクル + 独立検証 agent で誤検知を抑制）
- 振り返り（retrospective。完了実績・見積もり精度・反復テーマの concept 化提案）
- issue 作業の全散文成果物に writing-polish 推敲を必須連携（未インストール時は skip）

## 旧プラグインからの移行

旧 linear-workflow / indie-workflow は 2026-08-17 にリポジトリから削除した。まだ旧プラグインが入っているマシンでは:

1. 旧プラグインを uninstall する（`claude plugin uninstall linear-workflow@<marketplace>`）
2. issue-workflow を install する（新旧の同時 install は禁止。hook の二重発火とトリガー衝突が起きる）
3. データディレクトリはそのまま使える（rename 不要）
