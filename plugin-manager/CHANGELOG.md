# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
