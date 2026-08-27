# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.8.3] - 2026-08-28

### Fixed

- **doc と実装の乖離を掃引した**（GitHub issue #185）。旧 linear-workflow / indie-workflow の
  死んだ参照の張り替え、README が実装と食い違っていた記述（欠落していた表の行・設定キー・
  引数・エラー文言）の訂正が主な内容。挙動の変更は無い

## [1.8.2] - 2026-08-17

### Changed
- 削除された `linear-workflow` / `indie-workflow` への参照を `issue-workflow` に張り替えた（旧 2 プラグインは統合後継への移行完了に伴いリポジトリから削除）

## [1.8.1] - 2026-07-23

### Fixed
- **SessionStart 通知が「後継の直接 install」を勧めて併存禁止状態に誘導し得た穴を修正**。インストール済み deprecated の後継プラグインは通常の「/plugin install」提案から分離し、「/update-all を実行（自動移行が走る）」への誘導として通知する
- check-missing-plugins.sh: bash 3.2 の `set -u` で空配列 `"${arr[@]}"` 展開が unbound variable になり state 記録が落ちるバグを修正（`${arr[@]+...}` ガード）

## [1.8.0] - 2026-07-23

### Added
- **update-all に deprecated プラグインの自動移行（auto-migrate）を追加**。marketplace エントリの `_superseded_by`（機械可読な後継宣言）を検出したら、更新の代わりに「同一後継を持つ deprecated 群を全て uninstall → 後継を install」を原子的に実行する（併存禁止プラグインの同時 install を構造的に回避）。後継が既に install 済みなら deprecated の uninstall のみ。後継の install 失敗時は旧プラグインを再 install してロールバック。`~/.claude/plugin-manager/config.json` の `auto_migrate: false` で無効化可能
- Phase 4.7 の未インストール検出と SessionStart hook（check-missing-plugins.sh）が `_superseded_by` 付き（= deprecated）プラグインを提案から除外するようになった（deprecated の新規 install を勧めない）

## [1.7.3]## [1.7.3] - 2026-07-22

### Fixed
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [1.7.2] - 2026-07-02

### Fixed

- `commands/update-all.md` Phase 4.7 の jq フィルタに `// empty` null ガードを追加（`name` 欠落時に `null@marketplace` を生成していた問題を修正。hook 側 `check-missing-plugins.sh` と表現を統一）
- SessionStart hook `check-missing-plugins.sh` の timeout を 5 秒から 10 秒に引き上げ（marketplace × plugin ごとの jq 多重 spawn で marketplace 数が多い環境の 5 秒到達を回避）

### Changed

- `README.md` を現行実装（v1.5.0 のデフォルト=自作のみ / `--all` で全件、v1.6.0 の SessionStart 通知 hook、`~/.claude/plugin-manager/config.json` 設定）に更新（2 バージョン遅れの解消）

## [1.7.1] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [1.7.0] - 2026-06-03

### Added
- `update-all` 実行時に「未インストールの自作プラグイン」を検出・警告する Phase 4.7 を追加（#63）。自作マーケットプレイスに登録済みだが未インストールのプラグインを `name@marketplace` 単位で報告し、`claude plugin install` コマンドを併記する
- SessionStart hook（`check-missing-plugins.sh`）と挙動を揃え、`config.json` の `ignore_plugins` / `ignore_marketplaces` を尊重（cooldown / install_ratio 閾値は明示実行のため適用しない）
- 警告のみで自動インストールはしない（`update-all`=更新 / `install`=新規導入 の責務分離を維持）

## [1.6.0] - 2026-05-28

### Added
- SessionStart hook `check-missing-plugins.sh` を追加（#44）。`install_ratio` が閾値（既定 0.8）以上の marketplace について、未インストールプラグインを軽く通知する
- 設定ファイル `~/.claude/plugin-manager/config.json` で `notify_cooldown_days` / `install_ratio_threshold` / `ignore_plugins` / `ignore_marketplaces` を調整可能
- 通知 state `~/.claude/plugin-manager/state.json` で cooldown 管理（同一プラグインの再通知最短間隔、既定 7 日）

## [1.5.0] - 2026-05-25

### Added
- 更新対象を自作プラグインのみに絞る Phase 0 を追加（plugin-manager 自身のマーケットプレイスを自作の出所として判定）
- `--all` 引数で従来通り全プラグインを更新可能

### Changed
- デフォルト挙動を「全プラグイン更新」から「自作プラグインのみ更新」に変更

## [1.4.0] - 2026-03-25

### Added
- 更新済みプラグインの CHANGELOG エントリを結果レポートに表示

## [1.3.0] - 2026-03-23

### Added
- 結果テーブルに Before/After バージョンを表示（#6）
- バージョンが変わらない場合は「変更なし」と表示

### Fixed
- uninstall スコープ不整合エラーに対する段階的フォールバック追加（#5）
  - `--scope user` → `--scope project` → `installed_plugins.json` 手動削除の3段階

## [1.2.1] - 2026-03-23

### Fixed
- marketplace update 前にローカルキャッシュを削除するステップを追加（古いキャッシュが残り install 時に反映されない問題を修正）

## [1.2.0] - 2026-03-22

### Changed
- update-all の更新方式を `claude plugin update` から `uninstall` → `install` に変更（CLI バグ回避）
- マーケットプレイスキャッシュ更新ステップを追加

## [1.1.0] - 2026-03-21

### Added
- 初期リリース（v1.1.0 統一バンプ）

## [1.0.0] - 2026-03-20

### Added
- plugin-manager プラグインを新規作成
- プラグイン一括更新コマンド
