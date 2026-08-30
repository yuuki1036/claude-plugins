# guardrail-protect

lint / hook / static check の「骨抜き」変更、`git commit --no-verify`、そして **`gh` で公開する本文の裏取り漏れ**を PreToolUse hook で機械的にブロックする単機能 plugin。

AI agent が「赤を消すために linter を緩める」「hook がうるさいから `--no-verify` する」「典拠を確認せずに公開文書へ書く」逃げ道を構造的に塞ぐ。

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

### 3. 実在しない見出しへの参照ブロック (Bash on gh write)

`gh issue create|comment|edit|close` / `gh pr create|comment|edit|review` の本文に
``` `<file>.md ## <見出し>` ``` 形式の参照があり、**ファイルは実在するのにその見出しが無い**
場合に `exit 2` でブロックする（常時有効・opt-in 不要）。

節番号の取り違え（分冊で番号が引き継がれている / 節が増減した）が典型で、公開後の訂正コストが高い。

- 本文の取り出しはコマンド文字列をそのまま検査する方式（参照はバッククォート付きで現れるため
  `--body` / `-b` / heredoc を覆う）。`--body-file` / `-F` はファイル内容を読み足す。
  **コマンド置換 `--body "$(cat x.md)"`・変数展開・`-F -`（stdin）で渡された本文は検査されない**
- ファイルの解決は**末尾一致も許容**する（`references/orchestration-guide.md` で
  `code-review/references/orchestration-guide.md` を指すプラグインルート相対の慣習に対応）
- **判定できない条件では必ず黙る**: ファイル名が複数に一致する / repo 内に見つからない /
  git 管理下でない
- `jq` / `python3` が無い環境では**無言で無効化せず** stderr に通知する（fail-loud）

**パスの実在は検証しない。** 過去 issue 188 件 + コメント 213 件を母集団に実測したところ、
パス実在検証は**真の検出 0 件・偽陽性 41 件**（正当なプラグインルート相対参照 / placeholder /
他リポジトリのパス / 実行時生成ファイル / `React/Next.js` のような非パス）**だった**。
同じ母集団で見出し実在の検証は**真の検出 8 件・偽陽性 0 件だった**。

**この数値は導入前の issue 本文に閉じた観測であって、検出器の性質ではない。** 実際に hook が
掛かる入力（今後書く本文・リポジトリ内 md の引用）では 5 系統の偽陽性が見つかり、いずれも修正した
（下記「制限事項」）。現在は**このリポジトリの実 md 297 件・実在見出し 3401 件で偽陽性 0**
（回帰テスト `RealRepositoryRegressionTest` が毎回検証する）。
測定の一次記録: `docs/session-reports/2026-08-28-gh-ref-guard-measurement.md`

### 4. 隔離なしの hook スクリプト実行ブロック (Bash)

hook の entry point を**隔離せずに直接実行**しようとしたら `exit 2` でブロックする（常時有効・opt-in 不要）。

hook スクリプトは書き込み先を `${CLAUDE_PROJECT_DIR:-$PWD}` から導出するため、検証やデバッグの
つもりで実プロジェクトのまま走らせると `.claude/events.jsonl` などに**本物と区別できない行**が
混入する（計測の母集団が静かに汚れる）。実測 2 件あり、うち 1 件は「隔離せよ」と prompt に
明記した並列 agent の一部が守らなかったもの — **指示ベースの隔離は守られない**。

通し方は、同一コマンドに値つきの `CLAUDE_PROJECT_DIR=<使い捨て dir>` を前置きすること:

```bash
CLAUDE_PROJECT_DIR=/tmp/scratch-repo bash path/to/hooks/scripts/x.sh < payload.json
```

**判定はパスの glob ではなく中身で行う。** リポジトリ実測で `*/hooks/scripts/*.sh` は 27 本あり、
26 本が `safe_hook_init` を呼ぶ真の entry point、1 本は skill から意図的に Bash で叩かれる
ユーティリティだった。パスで切るとその 1 本が偽陽性になるため、`safe_hook_init` を持つものだけを
対象にしている（この基準での偽陽性は実測 0 件）。

**実行位置だけを見る。** パスが現れただけでは止めない — `cat` / `grep` / `wc` / `shellcheck`
のような読むだけの操作は通す。セグメントのコマンド位置か、インタプリタの最初の非フラグ引数に
あるものだけを実行と見なす。隔離の判定もセグメント単位で、`CLAUDE_PROJECT_DIR=/tmp/x bash a.sh
&& bash b.sh` の `b.sh` は隔離されていないと判定する。

**読めないものは通す**（fail-open を明示的に選んでいる箇所）: 未展開の変数を含んで解決できない
パス、トークン化できないコマンド。読めないことを理由に止めると、偽陽性 0 の水準を自分で壊す。

`jq` / `python3` が無い環境では**無言で無効化せず** stderr に通知する（fail-loud）。


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
- **見出し参照の検証はバッククォートで囲まれた ``` `<file>.md ## <見出し>` ``` だけが対象**。散文中の参照・URL の fragment・`.md` 以外のファイルは見ない。また**数値主張（「N 件」「X%」）の検算は行わない** — 数値を含むだけで鳴らすと偽陽性が常態化するため、規約側の領分として分けている
- **意図的に判定しないもの**（黙って通す）: 複数節をまとめて指す参照（`` `f.md ## 6 / ## 8` ``）／ファイル名が repo 内の複数ファイルに一致する／repo 内に見つからない／閉じないコードフェンスを含む doc（見出し一覧が壊れるため判定不能とする）／git 管理下でない／`git ls-files` が空
- **検査されない渡し方**: コマンド置換（`--body "$(cat x.md)"`）・変数展開・`-F -`（stdin）。`gh api` / `gh release` / `gh gist` も対象外
- **ブロックされたときの回避**: 参照の書き方を変えるか、guardrail-protect を無効化する（**プラグイン単位**。commit 迂回ガードも同時に外れる）。`.claude/guardrail-protect.json` はこの hook を制御しない（設定ファイル保護のみ）
- **config 自己保護**: `guardrail-protect.json` 自体は Edit/Write/MultiEdit（`pre-config-guard.sh`）と Bash 書き込み（`detect-commit-bypass.pl`）の両経路で常にブロック対象。保護スコープを変える場合は Claude 外で人間が編集する

## CHANGELOG

[CHANGELOG.md](CHANGELOG.md) 参照。
