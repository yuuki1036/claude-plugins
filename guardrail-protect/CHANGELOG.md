# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.3.0] - 2026-08-27

### Fixed

- **不正 payload での暗黙の fail-open を塞いだ**（GitHub issue #178）。`jq` の呼び出しに
  `|| true` が無く、切り詰められた JSON などで `jq` が exit 5 を返すと safe-hook の
  ERR trap を踏み、**ガードを通り抜けたことに誰も気づけないまま exit 0** していた
  （実測: 正常 payload の `git commit --no-verify` は rc=2 でブロックされるのに、
  同じコマンドを切り詰めた payload に入れると rc=0 で素通りした）。通す方向自体は
  従来どおり（壊れた入力で作業を止める方が高コスト）だが、**明示的に選んだ結果**として通す
- **`pre-config-guard.sh` が `tool_name` を判定に使うようにした**（同 issue）。以前は取得
  するだけでエラー文面にしか使っておらず、ブロック判定は `file_path` だけだった。
  hooks.json の matcher が唯一のツール種別フィルタになっており、matcher が評価されない
  環境（CLAUDE.md Gotchas に実測記録あり）では**保護対象ファイルの `Read` まで**
  「Refusing to edit」でブロックされていた。`tool_name` が無い payload では従来どおり
  検査する（載せない CC 版でガードごと無効化しないため）
- README の制限事項で「`Bash` 経由の編集はブロックしない（matcher の対象外）」としていた
  機構説明を訂正。`Bash` matcher の hook は存在し、通していたのは前段フィルタの働き

### Added

- `pre-config-guard.sh` の hook テストクラスを新設（従来はテストが 1 件も無かった）。
  「Read はブロックしない」「自己保護は Write だけ止める」「不正 payload で ERR trap に
  落ちない」を表明する

## [0.2.2] - 2026-08-07

### Fixed
- code-review の specialist-guardrail-bypass の参照先を `code-review/references/prompts/specialist/guardrail-bypass.md` に更新（分割で `reviewer-prompts.md` §5 が実体を持たなくなったため）

## [0.2.1] - 2026-07-22

### Fixed
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [0.2.0] - 2026-07-02

### Added
- `detect-commit-bypass.pl`（新規）: git hook 迂回の検出を**シェル準拠トークナイザ + git commit 引数モデル**で全面刷新。従来の「引用符=コミットメッセージ」という素朴前提を廃し、`'...'` / `"..."` / `$'...'` / バックスラッシュを正しく解釈してトークン化する。敵対的レビューで実証された以下のバイパスをすべて塞いだ:
  - 結合短フラグ（`-nm` / `-anm`）と `--no-verify` の git 省略形（`--no-ver` / `--no-veri` ...）
  - **引用符付きフラグ**（`git commit '--no-verify'` / `$'-n'`）
  - **`core.hooksPath` 上書きの全経路**: `git -c core.hooksPath=...`（裸・引用符付き両方）と `GIT_CONFIG_KEY_*=core.hooksPath` 等の **env 変数**経由
  - **`sh -c` / `bash -xc` / `zsh -ic` / `eval` に埋め込まれたスクリプト**（結合フラグ・再帰解析対応）
  - **バックスラッシュ改行継続**（`git commit \`↵`-n`）で分割された迂回
  - `command git` / `\git` / `builtin` 前置
  - タブ区切りフラグ
- `detect-commit-bypass.pl`: **config 自己改変の Bash 経路**を検出。`guardrail-protect.json` へのリダイレクト / `sed -i` / `tee` / `cp` / `mv` / `rm` 等を Bash matcher でブロックし、Edit/Write だけでなく Bash からの config 破壊も塞ぐ
- `pre-config-guard.sh`: **config 自己保護**（Edit/Write/MultiEdit 経路）を追加。`guardrail-protect.json` 自体を常時保護対象にする

### Changed
- 引数モデルにより誤爆を解消: メッセージ本文中の `--no-verify` / `core.hooksPath`（`git commit -m 'explain --no-verify ban'`）、値を取る短オプション（`-amn` の `n` は `-m` の値、`-amend` タイポ、`-S` / `-C HEAD`）、複合コマンドの他コマンドの `-n`（`git log -n 5`）をいずれも誤検知しない
- **bash 3.2 対応**: 検出ロジックを `pre-commit-guard.sh` のインライン heredoc から独立 perl ファイルに分離（bash 3.2 は `$()` 内 heredoc の引用符追跡でパースが壊れるため）
- **fail-loud 化**: `jq` / `perl` 不在時に `safe_hook_error Unexpected` で stderr 通知（従来は silent skip でガードが無言で無効化されていた。fail-closed 原則に整合）
- `hooks.json`: `pre-commit-guard` の `if: "Bash(git commit *)"` ゲートを撤去し、スクリプト側の判定に一本化（ゲートが複合コマンドで不発火する穴を解消）
- `references/protected-files-default.md`: basename マッチで効かない `.husky`（ディレクトリ）を推奨例から除外し注記追加。`pyproject.toml` / `tsconfig.json` の誤爆リスクを注記

## [0.1.1] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [0.1.0] - 2026-05-28

### Added
- 初期リリース（#45）
- PreToolUse hook `pre-config-guard.sh`: 保護対象 basename への Edit/Write/MultiEdit を `exit 2` でブロック
- PreToolUse hook `pre-commit-guard.sh`: `git commit --no-verify` / `-n` を heredoc/quoted string 剥がし後に検出してブロック（message 内文字列は誤検知しない）
- 設定ファイル `<project>/.claude/guardrail-protect.json` で `protected_basenames` を opt-in 宣言
- references: メタルール本文（骨抜き禁止）と推奨保護対象リスト
