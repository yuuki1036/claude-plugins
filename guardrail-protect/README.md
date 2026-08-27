# guardrail-protect

lint / hook / static check の「骨抜き」変更と `git commit --no-verify` を PreToolUse hook で機械的にブロックする単機能 plugin。

AI agent が「赤を消すために linter を緩める」「hook がうるさいから `--no-verify` する」逃げ道を構造的に塞ぐ。

## 機能

### 1. 設定ファイル保護 (Edit / Write / MultiEdit)

`Edit|Write|MultiEdit` ツールでの編集対象 basename が `protected_basenames` に含まれていれば `exit 2` でブロックする。

### 2. git hook 迂回ブロック (Bash on git commit)

`git commit` 実行時、git hook を迂回する以下のパターンを `exit 2` でブロックする（常時有効・opt-in 不要）:

- `--no-verify` / `-n` と、その **git 省略形**（`--no-ver`, `--no-veri`, ...）
- **`-n` を含む短フラグクラスタ**（`-nm`, `-anm` など、結合フラグ。`-m` 等の値を取る短オプションで打ち切るため `-amend` タイポや `-am` は誤爆しない）
- **引用符付きフラグ**（`git commit '--no-verify'`, `$'-n'`）
- **`core.hooksPath` 上書き**: `git -c core.hooksPath=...`（裸・引用符付き）と `GIT_CONFIG_KEY_*=core.hooksPath` 等の **env 変数**経由
- **`bash -c '...'` / `sh -xc "..."` / `eval "..."` 等に埋め込まれたスクリプト**（再帰解析）
- **バックスラッシュ改行継続**で分割された迂回

検出器（`detect-commit-bypass.pl`）はコマンドを**シェル準拠でトークン化**（引用符を除去）し、pipeline/list セグメントに分割して **git commit セグメントだけ**を git の引数モデルで検査する。そのため:

- commit message / justify 説明に `--no-verify` や `core.hooksPath` の文字列を含むだけのケースは誤検知しない（`-m` の値としてスキップ）
- 複合コマンドの他コマンドの `-n`（例: `git commit -m x && git log -n 5`）は誤爆しない

`guardrail-protect.json` 自体を Bash（リダイレクト / `sed -i` / `tee` / `cp` / `mv` / `rm` 等）で改変する試みもブロックする（Edit/Write 経路は `pre-config-guard.sh` の自己保護でカバー）。

`jq` / `perl` が無い環境では**無言で無効化せず** stderr に通知する（fail-loud）。

## opt-in セットアップ

デフォルトでは **保護対象ゼロ**（誤爆防止）。プロジェクトが明示的に opt-in する。

### 1. 設定ファイル作成

`<project>/.claude/guardrail-protect.json`:

```json
{
  "protected_basenames": [
    ".golangci.yml",
    "lefthook.yml",
    ".eslintrc.json",
    "redocly.yaml"
  ]
}
```

推奨デフォルトリストは [references/protected-files-default.md](references/protected-files-default.md) を参照。

### 2. プラグインインストール

```
/plugin install guardrail-protect@yuuki1036-claude-plugins
```

セッション開始時から hook が有効になる。

## 動作確認

### 設定ファイル保護のテスト

```
# Edit ツールで .golangci.yml を触ろうとする
→ "Refusing to edit guardrail config file: .golangci.yml" で exit 2
```

### git hook 迂回ブロックのテスト

```
git commit --no-verify -m "msg"          → exit 2（--no-verify flag）
git commit -nm "msg"                      → exit 2（-n short flag）
git -c core.hooksPath=/dev/null commit    → exit 2（core.hooksPath override）
bash -c 'git commit -n'                   → exit 2（-c スクリプト内も検査）

git commit -m 'fix: explain --no-verify ban'   → PASS（message 内の文字列は剥がす）
git commit -m "fix" && git log -n 5            → PASS（他コマンドの -n は誤爆しない）
```

## 例外運用（commit body での justify）

設計上どうしても弱体化が必要な場合は、**hook を bypass する代わりに以下のフローを取る**:

1. `.claude/guardrail-protect.json` から該当 basename を一時的に削除
2. 変更を実施し、commit body に justify を 3 要素で明記:
   - **Why**: なぜ既存ルールが阻害するか（具体的に）
   - **Verification**: 代替の検証手段
   - **Recovery**: 恒久的な弱体化なら ADR を別途起票、一時的なら復旧予定
3. commit 後、`.claude/guardrail-protect.json` に basename を戻す

詳細なメタルール本文は [references/meta-rule.md](references/meta-rule.md) を参照。

## アンインストール時の挙動

プラグインを無効化すれば hook は呼ばれなくなる。プロジェクトの `.claude/guardrail-protect.json` は残るが、hook がないと no-op。

## 関連プラグイン

- **code-review** の `specialist-guardrail-bypass`: hook で防げなかった diff レベルの骨抜きを reviewer が検出
- **claude-meta:claude-md-improver**: CLAUDE.md に「ガードレール骨抜き禁止」セクションを suggest

## 制限事項

- 保護対象 (`protected_basenames`) は basename マッチのみ（パス全体ではない）。同名ファイルがリポジトリ内に複数ある場合は全て対象になる
- `MultiEdit` での編集も `tool_input.file_path` を見るのでブロックされる
- **保護対象 config への `Bash` 経由の編集**（`sed` / `awk` / リダイレクト等）はブロックしない。`Bash` matcher の hook（`pre-commit-guard.sh`）自体は存在するが、その前段フィルタが `git commit` 系と guardrail 設定ファイル自体に関わるコマンドだけを通すため。これは意図的な制限（Bash の編集系コマンドを全部マッチさせると誤爆が爆発するため）。**ただし `guardrail-protect.json` 自体への Bash 書き込み**（リダイレクト / `sed -i` / `tee` / `cp` / `mv` / `rm`）は自己保護として検出しブロックする
- git hook 迂回の検出は `git commit` コマンド自体に埋め込まれたパターンが対象。以下の**別コマンドによる無効化**は検出しない（既知の穴。必要なら該当ファイル/コマンドを permissions 側で塞ぐ）:
  - `git config core.hooksPath ...`（commit と別コマンドで hooksPath を変更）
  - `rm .git/hooks/*` / `chmod -x .git/hooks/*`（hook スクリプトの削除・無効化）
- **config 自己保護**: `guardrail-protect.json` 自体は Edit/Write/MultiEdit（`pre-config-guard.sh`）と Bash 書き込み（`detect-commit-bypass.pl`）の両経路で常にブロック対象。保護スコープを変える場合は Claude 外で人間が編集する

## CHANGELOG

[CHANGELOG.md](CHANGELOG.md) 参照。
