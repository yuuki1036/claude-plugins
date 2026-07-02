# claude-meta

Claude Code 自体の設定管理・改善を支援するプラグイン。コードベース分析によるセットアップ推奨、CLAUDE.md の品質監査・改善、CC アップデート追従、新コンポーネント追加前の判断、eval 回帰テスト、セッション学習の反映を行う。

## コマンド

### catch-up

Claude Code の最新アップデートからプラグイン開発に関連する新機能を抽出し、開発中の全プラグインへの改善を提案・適用する。`cc-catch-up` スキルとペアで、引数でバージョン範囲を指定できる（例: `/catch-up 2.1.80-2.1.86`。省略時は前回キャッチアップ以降の差分が対象）。

**トリガー例**: `/catch-up`、「キャッチアップ」「CC更新確認」「新機能を取り込む」

### revise-claude-md

セッション中の学習内容を CLAUDE.md に反映するスラッシュコマンド。セッションで発見したコマンド、コードスタイル、テスト手法、設定の注意点などを簡潔にまとめ、ユーザーの承認を得て CLAUDE.md を更新する。

**トリガー例**: `/revise-claude-md`

## スキル

### cc-catch-up

Claude Code の最新アップデートをキャッチアップし、既存プラグインへの改善を提案・適用する。`references/plugin-features.md`（プラグイン関連機能カタログ）と `references/improvement-patterns.md`（機能 → 改善のデシジョンツリー）を参照し、`${CLAUDE_PROJECT_DIR:-$HOME}/.claude/claude-meta/cc-catch-up-state.json` で前回キャッチアップ状態を追跡する（プラグイン本体には置かず、marketplace 更新で消えない場所に保存）。`catch-up` コマンドとペア。

**トリガー例**: 「キャッチアップ」「CC更新確認」「プラグイン改善」「新機能適用」「リリースノート確認」

### claude-code-setup

コードベースを分析し、ユーザーレイヤー（`~/.claude/`）の既存設定を考慮した上で Claude Code オートメーション（Hooks, Skills, MCP Servers, Subagents, Plugins）を推奨する。読み取り専用で、分析と推奨のみ行う。新規スキル提案より公式同等品の利用を優先する判定フローを含む。

**トリガー例**: 「セットアップ推奨」「オートメーション推奨」「どんなhookを使うべき?」「recommend automations」

### claude-md-improver

リポジトリ内の CLAUDE.md ファイルを検出し、品質基準に基づいて評価・改善する。品質レポートを出力した後、ユーザーの承認を得て改善を適用する。運用パターン 6 セクション診断（ガードレール骨抜き禁止 / 三段防御 / 階層 AGENTS.md / 優先度規約 / 静的検査優先）や Diátaxis 補助観点を含む。

**トリガー例**: 「CLAUDE.md監査」「CLAUDE.md改善」「CLAUDE.mdの品質確認」「audit CLAUDE.md」

### component-addition-advisor

プラグインに新 skill / agent / hook / command を追加する前の「退路確保」判断をガイドする。既存拡張で解けないかを最初に検証し、ブロッカーが出た場合のみ新規追加する。`_requirements` にフォールバック手順を書く規約を案内する。

**トリガー例**: 「新しいskill追加」「skill追加判断」「退路確保」「追加前チェック」「skill 分割すべき?」

### eval-runner

`evals/` 配下の YAML ケースを実行し、トリガーフレーズ → 期待スキル起動の回帰テストを pass^k 基準で検証する。トリガーフレーズや description を変更した後のスキル選択デグレ検出に使う。

**トリガー例**: 「eval実行」「スキル回帰テスト」「トリガーフレーズ検証」（引数: `[--plugin NAME] [--case ID] [--k N] [--dry-run]`）

## 使い方

1. プラグインをインストールする
2. スキルは会話中に自動的にトリガーされるか、スラッシュコマンドで呼び出せる
3. `/catch-up` で CC アップデートを追従し、`/revise-claude-md` でセッションの学習内容を CLAUDE.md に反映できる
