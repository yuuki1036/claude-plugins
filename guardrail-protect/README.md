# guardrail-protect

lint / hook / static check の「骨抜き」変更と `git commit --no-verify` を PreToolUse hook で機械的にブロックする単機能 plugin。

AI agent が「赤を消すために linter を緩める」「hook がうるさいから `--no-verify` する」逃げ道を構造的に塞ぐ。

## 機能

### 1. 設定ファイル保護 (Edit / Write / MultiEdit)

`Edit|Write|MultiEdit` ツールでの編集対象 basename が `protected_basenames` に含まれていれば `exit 2` でブロックする。

### 2. `--no-verify` ブロック (Bash on git commit)

`git commit` 実行時、`--no-verify` / `-n` フラグの使用を `exit 2` でブロックする。

検出ロジックは heredoc body / quoted string を剥がしてから境界マッチするため、commit message 内に `--no-verify` という文字列を含むだけのケース（justify 説明など）は誤検知しない。

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

### `--no-verify` ブロックのテスト

```
git commit --no-verify -m "msg"
→ "Refusing to bypass git hooks" で exit 2

git commit -m 'fix: explain --no-verify ban'
→ PASS（commit message 内の文字列は剥がしてから検査）
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

- basename マッチのみ（パス全体ではない）。同名ファイルがリポジトリ内に複数ある場合は全て対象になる
- `MultiEdit` での編集も `tool_input.file_path` を見るのでブロックされる
- `Bash` 経由の `sed` / `awk` / リダイレクトでの編集はブロックできない（matcher の対象外）。これは意図的な制限（Bash の編集系コマンドを全部マッチさせると誤爆が爆発するため）

## CHANGELOG

[CHANGELOG.md](CHANGELOG.md) 参照。
