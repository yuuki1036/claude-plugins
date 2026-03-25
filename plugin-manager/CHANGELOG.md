# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
