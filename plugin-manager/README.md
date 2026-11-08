# plugin-manager

インストール済みプラグインの管理ユーティリティ。一括更新と、後から追加された自作プラグインの取りこぼし通知、動いているセッションへの更新通知（読んだ skill より新しい版が入ったら SKILL.md の読み直しを促す）を行う。

## コマンド

| コマンド | 説明 |
|---------|------|
| `/update-all` | **自作プラグインのみ**を最新版に一括更新（デフォルト） |
| `/update-all --all` | インストール済みの全プラグインを更新 |

`/update-all` は「自作マーケットプレイス」（このコマンドが属するマーケットプレイス）に絞って更新する。全件更新したい場合のみ `--all` を付ける。更新後は Before/After バージョンと更新済みプラグインの CHANGELOG 抜粋を結果テーブルで報告する。

**mods が有効な環境（Claude Code 2.1.287 以降）では、モデルを呼ばずにその場で実行する**（`hooks/update-all.ts`）。手順は同じで、トークンを使わず、手順の取り違えも起きない。実行中は状態行に進み具合が出る。mods が無効な環境・`claude` CLI を呼べない環境では、今までどおりモデルが手順を実行する。

更新実行時、自作マーケットプレイスに登録済みだが未インストールのプラグインがあれば併せて通知する（後発追加の取りこぼし防止。deprecated（`_superseded_by` 付き）は提案から除外。`update-all` は更新専用のため自動導入はしない）。

## deprecated プラグインの自動移行（auto-migrate）

marketplace エントリに `_superseded_by: "<後継名>"` を持つ deprecated プラグインがインストールされている場合、`/update-all` は更新の代わりに**自動移行**する:

1. 同一後継を持つ deprecated 群を全て uninstall
2. 後継プラグインを install（既に install 済みなら uninstall のみ = 併存解消）
3. 後継の install 失敗時は旧プラグインを再 install してロールバック

併存が禁止されているプラグイン群（hook 二重発火・トリガー衝突）を中間状態なしで入れ替えるための機構。`~/.claude/plugin-manager/config.json` の `auto_migrate: false` で無効化できる（既定は有効）。

## SessionStart 通知

セッション開始時に `check-missing-plugins.sh` hook が「ほぼ全部 install しているマーケットプレイス」の未インストールプラグインを軽く通知する。`install_ratio`（そのマーケットプレイスの install 済み割合）が閾値（既定 0.8）以上のマーケットプレイスのみ監視対象とし、一部しか install していない巨大マーケットプレイスからの通知爆発を防ぐ。

## 動いているセッションへの更新通知

1 つのセッションを何日も動かし続けると、プラグインを更新した後も、最初に Read した版の SKILL.md の手順で進み続ける（`/update-all` の後も再起動しない限り、会話の中の手順は古いまま）。`stale-skill.sh` hook がこれを知らせる:

1. **記録**（PostToolUse の Read / Skill）: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` の下のファイルを Read したら、その版を記録する（`skills/<name>/SKILL.md` なら skill ごとに）。Skill で呼んだ skill は、呼んだ時点のインストール済みの版を記録する（Read で記録した版は上書きしない）
2. **通知**（UserPromptSubmit・PostCompact・SessionStart の resume / compact）: 記録した版と `installed_plugins.json` の版が違えば、新しい版の SKILL.md のパスと、旧版より新しい CHANGELOG の見出し（最大 5 行）を注入する。読み直したら、新しい版で足された手順のうち今の作業に効くものは利用者に確かめずに済ませ、後から戻しにくい変更だけ聞くよう添える（常設のセッションが自分で追従できるように）
3. 同じプラグインの同じ新版は 1 回だけ知らせる。compaction の後は通知も会話から消えるので、もう一度出す。新しい版の SKILL.md を Read すれば記録が新しくなり、通知は止まる

黙る条件: このセッションでプラグインのファイルを読んでいない・版が同じ・アンインストール済み・`installed_plugins.json` が無いか壊れている・状態ファイルが壊れているか形式（`schema_version`）が違う（次の Read で記録し直す）・`python3` が無い。新しいセッション（SessionStart の startup / clear）では知らせない。

状態は `${CLAUDE_CONFIG_DIR:-~/.claude}/plugin-manager/sessions/<session_id>.json`。発言のたびに更新し、14 日以上触れられていないもの（書きかけの一時ファイルを含む）は SessionStart で消す。ただし resume したセッション自身の記録は、通知を出す前には消さない。この版を入れる前から動いているセッションには、記録が無いので届かない。resume で session_id が変わる環境では記録を引き継げず、通知は出ない。

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
