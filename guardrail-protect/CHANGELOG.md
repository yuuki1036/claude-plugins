# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.4.0] - 2026-08-28

### Fixed

- **セルフレビューで見つかった偽陽性 5 系統を修正した。** 出荷前の実装は設計要件
  「偽陽性 0」を満たしておらず、実 md 297 件の実在見出し 3396 件のうち **87 件を
  誤ってブロック**していた（修正後は 3401 件で 0 件）:
  - **行頭のインラインコードスパン / 未終端フェンス** — `in_fence` の単純トグルが
    ``` ``` `x` ``` ``` 行で反転し、以降の実在見出しが消えていた。**引き金は本プラグイン
    自身の README の記法**で、`README.md ## 制限事項` への参照が exit 2 になっていた。
    開始記号の種類と長さで対応を取り、未終端は判定不能として黙るようにした
  - **H4 以上の見出し** — `ANCHOR_RE` の `#{1,3}` が 4 個目の `#` を anchor 側に漏らし、
    正しい参照が必ず不一致になっていた（repo に H4 が 115 個）。`#{1,6}` に広げた
  - **複合参照** — `` `f.md ## 6 / ## 8` `` の anchor が見出しになりえない文字列になる。
    この書き方は `code-review/CHANGELOG.md` に実在する。判定対象から外した
  - **`gh` を呼ばないコマンドのブロック** — 事前フィルタの部分文字列 glob が
    `hi(gh)light ... issue ... create` に一致していた。`shlex` トークンで
    `gh <issue|pr> <write>` を判定するようにした
  - **GitHub の anchor slug 形式** — `` `README.md#installation` `` が `## Installation` と
    大小文字違いで一致しなかった。slug 正規化して突合する
- **検出器の失敗が無音の fail-open になっていた**。`2>/dev/null || true` が exit code と
  stderr の両方を握り潰し、`detect-stale-refs.py` を消しても **rc=0 / 出力 0 バイト**で
  ガードが黙って無効化された（既存 `pre-commit-guard.sh` は同条件で `Unexpected` を出す）。
  ファイル自身が宣言する fail-loud 方針と矛盾していた。`&& rc=0 || rc=$?` で受けて
  `safe_hook_error Unexpected` に倒す（`VAR="$(...)"; RC=$?` は `set -e` で死ぬ / CLAUDE.md Gotchas）
- **`git ls-files` のパース**。既定の `core.quotePath=true` で非 ASCII パスがエスケープされ、
  **日本語ファイル名の doc は永久に解決できず黙って無検査**になっていた。空白入りパスは
  `split()` で 2 つに割れ、無関係な参照の検出まで殺していた。`-c core.quotePath=false` +
  NUL 区切りにした
- **`--body-file` の取りこぼし**。`--body-file=path` の `=` 形式を拾えていなかった。
  `-F -`（stdin）は検査不能として明示的に除外した
- ブロックメッセージが案内していた「Claude Code の permissions で無効化」は**実在しない操作**
  （permissions は tool の allow/deny で hook を制御しない）。実際の手段に書き換えた

### Changed

- **doc の主張を測定範囲に閉じた**。「偽陽性 0 件**で成立する**」という現在形の一般命題は、
  母集団（導入前の issue 本文）を超えた一般化だった。過去形に直し、既知の制限を README に
  列挙した。`detect-stale-refs.py` の「真の検出 **7** 件」と他 4 箇所の「**8** 件」の
  食い違い（書いた当時の tree で判定するか現 HEAD で判定するかの差）も解消した
- **測定の一次記録を `docs/session-reports/2026-08-28-gh-ref-guard-measurement.md` に置いた**。
  従来は 5 箇所が互いの複製で、再現手順も母集団の切り出し条件も repo に無かった
  （この hook が防ごうとしている `claimed-fact-without-source` を doc 自身が犯していた）。
  スクリプトの docstring からは数値を落とし、正本パスだけを残す

### Added

- **実データ回帰テスト** `RealRepositoryRegressionTest`。このリポジトリの全 md から実在見出しを
  集めて参照形に組み立て、**偽陽性 0 を assert する**。上記 5 系統はすべて「参照先 doc の形」に
  起因し、参照テキスト側の合成 fixture をいくら増やしても再現しない型だった。doc の記法が
  増えるたび母数が自動で増える
- 5 系統と fail-loud 契約・prefilter・非 ASCII / 空白入りパスの回帰テスト（計 67 件）
- `mutation-ok` マーカーを外した。「等価変異」という理由は誤りで（早期 return の反転は
  下の分岐に到達しない）、完全一致分岐が未テストのまま検出信号だけが消えていた


### Added

- **`gh` の外向き書き込みで「実在しない見出しへの参照」をブロックする**
  （GitHub issue #162）。`gh issue create|comment|edit|close` / `gh pr create|comment|edit|review`
  の本文に ``` `<file>.md ## <見出し>` ``` があり、**ファイルは実在するのにその見出しが無い**
  場合に exit 2 で止める。`failure-journal` の `claimed-fact-without-source`（全期間 13 回・
  30 日窓 6 回で最多 tag）のうち、公開後の訂正が必要になった型に掛かる。
  既存の `Bash` matcher に追加する形で、新しい matcher もプラグインも足していない
- 判定本体を `detect-stale-refs.py` に分離（`detect-commit-bypass.pl` と同じ構成）。
  `--body` / `-b` / heredoc はコマンド文字列をそのまま検査して取りこぼさず、
  `--body-file` / `-F` はファイル内容を読み足す

### Changed

- **パス実在検証は入れないと決めた**（issue #162 の必須要件から範囲を狭めた）。
  過去 issue 188 件 + コメント 213 件を母集団に実測したところ、パス実在検証は
  **真の検出 0 件・偽陽性 41 件**（正当なプラグインルート相対参照 / placeholder /
  他リポジトリのパス / 実行時生成ファイル / `React/Next.js` のような非パス）だった。
  `claimed-fact-without-source` の実例 13 件を 1 件ずつ当たっても、パス実在検証で
  止まるものは 0 件だった。同じ母集団で見出し実在の検証は真の検出 8 件・偽陽性 0 件
  （CLAUDE.md「初回実行で偽陽性が出る warning は入れない方がまし」の適用）。
  **測定の一次記録**: `docs/session-reports/2026-08-28-gh-ref-guard-measurement.md`

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
