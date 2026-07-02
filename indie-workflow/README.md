# indie-workflow

個人開発向けローカル Issue 管理ワークフロー。

Linear 等の外部ツールに依存せず、ローカルファイルのみで Issue 管理を完結させる。放置検知、スコープ管理、技術的負債トラッキング、振り返りまで一貫サポート。

> **注意**: `linear-workflow` プラグインと排他的な関係。同一プロジェクトでは `.claude/indie/` または `.claude/linear/` のどちらか一方のみ使用すること。

## セットアップ

```bash
claude plugin install indie-workflow@yuuki1036-claude-plugins
```

プロジェクトで初めて使う場合は `/indie-init` を実行してディレクトリを初期化する。

## ディレクトリ構造

```
.claude/indie/{project}/
├── project.md              # プロジェクト概要
├── counter.txt             # 次の Issue 番号
├── backlog.md              # 軽量アイデアリスト
├── issues/
│   └── {PROJECT-N}.md      # Issue ファイル
├── follow-ups/
│   └── {YYYYMMDD}-{slug}.md # 開発中に切り出した follow-up メモ
└── knowledge/
    ├── index.md            # 知見インデックス
    ├── {topic}.md          # 個別知見（source）
    └── concepts/
        └── {concept}.md    # 概念ページ（横断統合 = concept）
```

> 振り返りレポートは `.claude/indie/retrospectives/YYYY-MM-DD.md` に保存される（プロジェクト横断）。

## スキル

| スキル | 用途 | トリガー |
|--------|------|----------|
| indie-init | プロジェクトの初期セットアップ | 新規プロジェクト開始時 |
| indie-start | セッション開始時の作業準備・ダッシュボード・放置警告 | 新しいセッション開始時 |
| indie-issue-create | Issue ファイルの新規作成 + ブランチ自動作成 + feature-dev 連携 | 新規タスク開始時 |
| indie-issue-maintain | Issue ファイルの品質整理・knowledge 切り出し | セッション終了前 |
| indie-maintain | 全プロジェクトの棚卸し・放置/debt 管理 | 定期的（週1程度） |
| indie-issue-discover | AI が課題を多観点で発見して issue を自動起票 | 「次に何やる？」を AI に任せたい時 |
| indie-follow-up | follow-up タスクの記録・一覧・Issue 昇格 | 開発中に別タスクを思いついた時 |
| issue-design | Issue 本文を 9 セクションテンプレで設計・構造化・リライト | Issue 本文を設計・整形したい時 |
| knowledge | 蓄積した知見の検索・参照（読み取り専用） | 過去の知見を探したい時 |
| knowledge-lint | knowledge グラフの健全性チェック（broken link / 孤立 / 鮮度） | knowledge を点検・修復したい時 |
| retrospective | 振り返り・見積もり精度分析 | 週次/月次 |

## コマンド

| コマンド | 引数 | 説明 |
|---------|------|------|
| `/indie-init` | `[PROJECT-SLUG]` | プロジェクト初期セットアップ |
| `/indie-start` | - | セッション開始の作業準備（main ブランチではダッシュボードモード） |
| `/indie-issue-create` | `[PROJECT-SLUG]` | Issue ファイル新規作成（ブランチ自動作成 + feature-dev 連携） |
| `/indie-issue-maintain` | - | Issue ファイルの整理 |
| `/indie-maintain` | `[project-slug]` | プロジェクト棚卸し |
| `/indie-issue-discover` | `[PROJECT-SLUG]` | 課題を多観点で発見して issue を自動起票 |
| `/indie-follow-up` | `[new\|list\|promote [FILE]]` | follow-up の記録・一覧・Issue 昇格 |
| `/issue-design` | `[ISSUE-ID \| リライト対象]` | Issue 本文の設計・構造化・リライト |
| `/knowledge` | `[search KEYWORD \| related]` | 知見の検索・参照 |
| `/knowledge-lint` | `[slug]` | knowledge グラフの点検・修復 |
| `/retrospective` | `[期間: 2w, 1m]` | 振り返り |

## Issue テンプレート

| タイプ | 用途 |
|--------|------|
| feature | 新機能の実装 |
| bugfix | バグ修正 |
| investigation | 調査・検証 |
| debt | 技術的負債の解消 |

## 個人開発向け機能

### 放置検知
- `last_active` フィールドで最終作業日を追跡
- SessionStart hook で 7日以上放置された in-progress Issue を自動警告

### スコープ管理
- Issue 作成時に `scope_size`（small/medium/large）を宣言
- タスク数が閾値を超えると警告（small: 3, medium: 7, large: 15）

### frozen ステータス
- 「今じゃないけど捨てたくない」Issue を明示的に凍結
- 30日以上の凍結 Issue は `/indie-maintain` で再評価を促す

### 技術的負債トラッキング
- `debt` タイプの Issue で負債を可視化
- `/indie-maintain` で件数・経過日数をサマリー表示

### 振り返り
- `/retrospective` で完了 Issue の分析、見積もり精度確認、学び抽出
- Good / Problem / Try フレームで対話的に振り返り

## SessionStart hook

`.claude/indie/` ディレクトリが存在するプロジェクトで自動発火し、プロジェクト管理ルールを注入する。放置 Issue の検知も同時に行う。

## ブランチ命名規則

```
{type}/{PROJECT-N}-{description}
```

例: `feat/MYAPP-3-add-auth`, `fix/BLOG-2-typo`
