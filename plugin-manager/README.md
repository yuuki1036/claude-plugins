# plugin-manager

インストール済みプラグインの管理ユーティリティ。一括更新と、後から追加された自作プラグインの取りこぼし通知を行う。

## コマンド

| コマンド | 説明 |
|---------|------|
| `/update-all` | **自作プラグインのみ**を最新版に一括更新（デフォルト） |
| `/update-all --all` | インストール済みの全プラグインを更新 |

`/update-all` は「自作マーケットプレイス」（このコマンドが属するマーケットプレイス）に絞って更新する。全件更新したい場合のみ `--all` を付ける。更新後は Before/After バージョンと更新済みプラグインの CHANGELOG 抜粋を結果テーブルで報告する。

更新実行時、自作マーケットプレイスに登録済みだが未インストールのプラグインがあれば併せて通知する（後発追加の取りこぼし防止。`update-all` は更新専用のため自動導入はしない）。

## SessionStart 通知

セッション開始時に `check-missing-plugins.sh` hook が「ほぼ全部 install しているマーケットプレイス」の未インストールプラグインを軽く通知する。`install_ratio`（そのマーケットプレイスの install 済み割合）が閾値（既定 0.8）以上のマーケットプレイスのみ監視対象とし、一部しか install していない巨大マーケットプレイスからの通知爆発を防ぐ。

## 設定（任意）

`~/.claude/plugin-manager/config.json` で挙動を調整できる:

```json
{
  "notify_cooldown_days": 7,
  "install_ratio_threshold": 0.8,
  "ignore_plugins": [],
  "ignore_marketplaces": []
}
```

| キー | 既定 | 説明 |
|------|------|------|
| `notify_cooldown_days` | 7 | 同一プラグインの再通知最短間隔（SessionStart 通知のみ） |
| `install_ratio_threshold` | 0.8 | 監視対象マーケットプレイスの install 済み割合の閾値（SessionStart 通知のみ） |
| `ignore_plugins` | `[]` | 個別プラグイン無視リスト（`name@marketplace`） |
| `ignore_marketplaces` | `[]` | マーケットプレイスごと無視リスト |

`ignore_plugins` / `ignore_marketplaces` は SessionStart 通知と `/update-all` の未インストール検出の両方で尊重される。`notify_cooldown_days` / `install_ratio_threshold` は SessionStart 通知のみに適用され、明示実行の `/update-all` では毎回検出する。

通知の cooldown 管理 state は `~/.claude/plugin-manager/state.json` に自動生成される。

## インストール

```bash
claude plugin install plugin-manager@yuuki1036-claude-plugins
```
