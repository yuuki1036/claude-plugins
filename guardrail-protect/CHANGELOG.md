# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.8.0] - 2026-10-01

### Added

- **branch-drift-guard を追加**（PreToolUse / Bash + PostToolUse / Bash / #270）。共有チェックアウトで別のセッションがブランチを切り替えた後に、気づかず git の書き込み（commit / merge / push / pull / rebase / reset / cherry-pick / revert / am）を打つのを止める。実例では、別セッションが切り替えたブランチに自分の Issue ブランチのつもりで merge を打ち、未コミットの変更があったので中断して済んだ
  - 照合元は PostToolUse の `branch-drift-record.sh` がセッション（`session_id`）ごとに記録する「直前のコマンドの後のブランチ」。このセッション自身の checkout は直後に記録されるので止めない
  - `.claude/session-context.md` は照合元にしない（チェックアウト単位のファイルで最後に start したセッションの値になり、共有チェックアウトでは見逃しと誤検出の両方が起きる）
  - 記録が無い・git でない・`git -C` で別の作業ツリーを指すときは何もしない。止めたら記録を更新し、確かめたうえでの再実行は通す。案内に一時 worktree を添える

## [0.7.0] - 2026-09-28

### Added

- **zsh-trap-guard を追加**（PreToolUse / Bash / #254）。Bash tool のシェルが zsh のとき、bash の前提で書くと
  エラーになるか黙って別の値になる書き方を止める: 波括弧なしの展開の直後の `:` + 修飾子の文字
  （`"$sha:code-review/x"` の `:c`）/ `path`・`status` への代入 / 語頭の `=`（`[ a == b ]`・`echo =====`）/
  オプション値の引用なしグロブ（`--include=*.sh`・`find -name *.py`）。echo の引数のエスケープは止めず、
  コンテキストに警告だけ出す。修飾子として読まれる文字は zsh で総当たりして実測した。
  過去の transcript の Bash 呼び出し 22,307 回で 4 規則は計 410 回当たり（うちグロブ 296 回中 292 回は
  結果に no matches found）、目視で誤検出は 0 件。解析は public-leak-guard と同じ `public_leak_shell.py`
  - blocker: 既存の Bash hook 4 本はどれも別の責務を持ち、無関係なコマンドは冒頭で抜ける。zsh の罠は
    全コマンドが対象なので、同居させると責務と事前フィルタが混ざる
  - fallback: この hook が無い環境では従来どおり。壊れたコマンドは失敗するか黙って誤った値を返すので、
    結果を読む側で気づくしかない（fail-open を選んでいるのは、守るのが安全性ではなく結果の正しさだから）

## [0.6.2] - 2026-09-28

### Changed

- **`public_leak_shell.py` の `Part` の既定値 `quoted=False` に `# mutation-ok` を付けた**（挙動は変わらない / #260）。
  既定値に頼るのはプロセス置換と引用なしのバッククォートだけで、`Part.quoted` を読むのは lit 同士を結合する
  `add_lit` だけなので、既定値を反転しても結果が変わらない等価変異だった。あわせて nightly で生存していた
  残り 3 件（引用なし heredoc の展開判定 / 環境変数で指した場所の自己保護と事前フィルタ）に回帰テストを足した

## [0.6.1] - 2026-09-27

### Fixed

- **自己保護の対象に code-review の publish 設定 dir（`~/.config/claude-review/`）を足した**。
  中の `post-publish` は review の publish のたびに切り離して実行されるが、保護の対象外だったので、
  agent が Write や Bash で置くと以後の publish で黙って走った。`machine-label`・`salt`（計測に載る
  マシンの label を決める）と計測リポジトリの `forbid-terms.txt` も同じ dir にある。
  Edit / Write は `pre-config-guard.sh`、Bash は `detect-public-leak.py` と `detect-commit-bypass.pl`
  （`pre-commit-guard.sh` と `public-leak-guard.sh` の事前フィルタも拡張）で、dir の中への書き込みと
  dir そのものの置き換えを止める。場所を変える `CLAUDE_REVIEW_CONFIG_DIR`・`REVIEW_METRICS_CONFIG_DIR` は、
  hook の環境にあれば指した先も守り、シェル設定・settings への書き込みは止める。読むだけの操作と、
  テストの隔離でコマンドの前に `CLAUDE_REVIEW_CONFIG_DIR=<使い捨て dir>` を置く実行は止めない
- **`業務 PR-3` のような PR 番号の呼び名がチーム形式の ID として確認に回っていた**のを直した。
  組み込みの許可リストに `PR` を足した。公開 issue の置き換えで使う固定の呼び名が、推奨設定でも
  止まっていた。止めたときの置き換え例にもこの呼び名を足した

### Changed

- README に、チーム形式の ID の組み込みの許可リスト（`allowed_id_prefixes` は組み込みに足され、
  置き換えない）、推奨設定（`YAT` と置き換え用の架空接頭辞 `TEAM`〜`TEAME`）、辞書・設定の有無による
  挙動の表（読めないときは private 宛の書き込みも止まる）を足した。設定例の `allowed_id_prefixes` を
  既定値（空）に揃えた

## [0.6.0] - 2026-09-27

### Added

- **公開リポジトリ・gist への業務情報の送信を止める PreToolUse ガード `public-leak-guard` を足した**
  （`hooks/scripts/public-leak-guard.sh` → `detect-public-leak.py` → `public_leak_shell.py`）。
  公開 issue・コメントに業務リポジトリ名・製品名・会社 PC のホスト名が繰り返し載った事故の再発防止。
  辞書の語とこのマシンのホスト名（`hostname -s`。辞書に無くても常に対象）に当たれば exit 2 で止める。
  辞書は `$GUARDRAIL_SENSITIVE_DICT` → `~/.config/guardrail-protect/sensitive-terms.txt`
  （1 行 1 語・`#` コメント・`w:` は語境界・3 文字未満は無視）で、リポジトリには入れない。

  **宛先は owner ではなく visibility で判定する**（`gh api repos/<o>/<r>` を
  `~/.cache/guardrail-protect/` に TTL 付きで保持）。owner で絞ると第三者の公開リポジトリへの
  投稿を見逃す。private と確定した宛先だけ素通しし、`GH_REPO` / `gh repo set-default` /
  upstream 優先の暗黙解決は cwd の GitHub remote 全部を候補にして全部 private のときだけ通す。
  gist・graphql の mutation・`/repositories/<id>`・リポジトリ外の cwd・visibility を取得できない宛先は
  公開先として検査する。

  **対象**: Bash の gh（issue / pr の書き込み系、`pr merge`、release、gist、label、project、
  `issue transfer`、`repo create --public --source --push`、`repo edit --visibility public`（常に止める）、
  `repo sync --source`、`gh api` の書き込み系）と gh alias・`env` / `command` / 絶対パス / 引用符で
  割った gh・`xargs` / `find -exec`・`bash -c` / `eval` / `$(…)`、`git push`（`--tags` /
  `--follow-tags` / `--mirror`、git alias。rev-list 範囲の追加行・commit メッセージ・作者・
  ファイル名・ブランチ名・annotated tag）と `gh pr create` の head push、GitHub MCP の書き込み系全部、
  `mcp__terminal__run_in_terminal`。ブラウザ操作の入力は opt-in（`browser_input`）。

  **本文の取り方**: 直書き・`--body-file`（hook 入力の cwd とコマンド内の `cd` で解決）・
  `$(cat f)` / `$(< f)` / heredoc・標準入力（heredoc / here-string / `<` / パイプ）・
  `gh api` の `-f` / `-F` / `@file` / `--input`。同じコマンド内で heredoc から書いてから
  `--body-file` で読むファイルは**ディスクではなくコマンドの heredoc を読む**（TOCTOU 対策）。
  解決できない本文（変数展開・任意のコマンド置換・標準入力）と、`git commit && git push` のように
  push の前段で履歴が変わりうるものは、公開先なら止めて書き出し方を案内する。

  **汎用パターン**（許可リスト外のチーム形式 ID・`/Users/<name>/`・`<別リポジトリ名> PR #N`）・
  添付・「非公開で別 owner のリポジトリで作業中のセッションから公開先へ書く」文脈は**確認**扱い。
  公式 docs では `permissionDecision: "ask"` は非対話（`-p`・auto・dontAsk・bypassPermissions・
  subagent）で defer に落ちて通りうるうえ、`-p` は hook 入力から見分けられないので、
  **既定は止める**（`confirm_action: "block"`）。`ask` にしても非対話と分かる入力では止める。

  **fail-closed**: safe-hook.sh の縮退（exit 0）は流用せず、内部エラー・python3 不在・検出器の異常終了・
  辞書 / 設定の読み込み失敗・壊れた入力・時間切れ（既定 7 秒で自分で打ち切る。hook の timeout は
  10 秒で、timeout すると止めずに通るため）・push 走査の上限超過は、公開につながる入力なら止める。
  辞書が無いときは既定で公開先宛てを止める（`on_missing_dict: "warn"` で警告に変えられる）。

  出力には語そのものを出さず、辞書の行番号・本文の行番号・置き換え例だけを出す（語を含むパスは伏せ字）。
  `GUARDRAIL_*` 変数の前置き・`export` / `env` / `unset` / `launchctl setenv`・シェル設定への書き込み、
  辞書・設定・visibility キャッシュの Bash での書き換えは、宛先に関係なく止める。

- **公開リポジトリ用の git pre-push `git-hooks/pre-push.sh` を同梱した**。同じ検出器を呼び、
  人の手の push や他のツールの push も止める。公開リポジトリごとに手で入れる（global の
  `core.hooksPath` は使わない。手順は README）。`detect-public-leak.py` には人が使う
  `scan-git` / `scan-text` モードもある

- 回帰テスト `test_guardrail_protect_public_leak.py` を足した（語はダミーのみ）。反証レビューで
  見つかった突破パターンごとに止まること、private 宛・読み取り系・無関係なコマンドが素通しになること、
  出力に語が出ないことを見る

### Changed

- **自己保護の対象に public-leak-guard の辞書・設定・visibility キャッシュを足した**
  （`~/.config/guardrail-protect/`・`~/.cache/guardrail-protect/`・`public-leak-guard.json`・
  `$GUARDRAIL_SENSITIVE_DICT` / `$GUARDRAIL_PUBLIC_LEAK_CONFIG` の指す先）。Edit / Write は
  `pre-config-guard.sh`、Bash は `detect-commit-bypass.pl`（`pre-commit-guard.sh` の事前フィルタも拡張）。
  `pre-config-guard.sh` はシェル設定・settings に `GUARDRAIL_*` を書き込む編集も止める。
  Bash 経由の検出理由の文言は `guardrail-protect.json self-modification` から
  `guardrail config self-modification` に変えた

## [0.5.2] - 2026-09-10

### Fixed

- `detect-unisolated-hook-run.py` の docstring が、dev-workflow の `gh --attach` 移行で削除された
  `upload-screenshots.sh` を「hook でない唯一のユーティリティ」の現存例として名指ししたまま
  stale 化していたのを修正。実測（issue #194 時点）の記録である旨と削除済みである旨を明記した。
  判定ロジック・挙動は不変

## [0.5.1] - 2026-08-31

### Changed

- **判定器の fail-open が 3 ケースであることを docstring に明記した**（GitHub issue #197）。
  「開けるが読めないファイル（権限・I/O エラー）を通す」という選択だけが文書化されておらず、
  nightly の変異テストで `except OSError` 節を fail-closed に倒す変異が生存した
  ＝ この選択を**何も検証していなかった**。回帰テスト 2 本を足して固定した
  （実物の権限で踏む 1 本 + 権限が効かない環境でも走る in-process の 1 本）

## [0.5.0] - 2026-08-30

### Added

- **隔離なしの hook スクリプト実行をブロックする PreToolUse (Bash) ガードを足した**
  （GitHub issue #194）。`hook-isolation-guard.sh` + 判定器 `detect-unisolated-hook-run.py`。

  検証・デバッグのために hook の entry point を実プロジェクトのまま走らせ、
  `.claude/events.jsonl` に本物と区別できない行が混入する事故が**実測 2 件**あった。
  2 件目は「隔離せよ」と prompt に明記した並列 agent の一部が守らなかったもので、
  **指示ベースの隔離が守られない**ことは実測済み。通すには同一コマンドに値つきの
  `CLAUDE_PROJECT_DIR=<使い捨て dir>` を前置きする。

  **判定はパスの glob ではなく中身で行う。** リポジトリ実測で `*/hooks/scripts/*.sh` は
  27 本あり、26 本が `safe_hook_init` を呼ぶ真の entry point、1 本
  （`dev-workflow` の `upload-screenshots.sh`）は skill から意図的に Bash で叩かれる
  ユーティリティだった。**パスで切るとこの 1 本が偽陽性**になる。`safe_hook_init` を
  持つものだけを対象にすると、既存リポジトリでの偽陽性は 0 件。

  **実行位置だけを見る。** パスが現れただけでは検出しない — `cat` / `grep` / `wc` /
  `shellcheck` のような読むだけの操作を止めるとガードがただの邪魔になる。セグメントの
  コマンド位置（env 代入を除いた先頭）か、インタプリタの最初の非フラグ引数にあるものだけを
  実行と見なす（`bash -x x.sh` も拾う）。

  **隔離の判定はセグメント単位。** `CLAUDE_PROJECT_DIR=/tmp/x bash a.sh && bash b.sh` の
  b.sh は隔離されていない。**空値は隔離と見なさない**（`CLAUDE_PROJECT_DIR=` だけだと
  `${VAR:-$PWD}` の `:-` が効いて $PWD に倒れる）。**読めないものは通す** — 未展開の変数を
  含むパスとトークン化できないコマンドは判定材料が無いので fail-open に倒す（読めないことを
  理由に止めると偽陽性 0 の水準を自分で壊す）。

  回帰テスト 20 本追加（判定器 13 / hook 7）。**黙る条件を厚く**書いてある（読むだけの操作・
  事前フィルタ・非 Bash ツール・不正 JSON）。実装を 4 通りに壊して全部でテストが落ちることを
  確認済み。

  **新規スクリプトにした理由**（`claude-meta:component-addition-advisor` の退路確保）:
  既存 3 本はいずれも事前フィルタと失敗メッセージが別の関心事に固定されており
  （`*git*commit*` / `*gh*` / Edit 系 matcher）、実行の書き込み先という軸を混ぜると
  是正先が誤読される。`_requirements` への記録は見送った — advisor が示す object 形式は
  `validate_ssot.py` が要求する array 形式（依存宣言用）と食い違い、従うと検証が落ちる。

## [0.4.2] - 2026-08-29

### Added

- nightly の変異テストが検出した**生存 2 件**を回帰テストで塞いだ（GitHub issue #189）。
  どちらも等価変異ではなく**実際の穴**だったことを、変異を当てた実行で確認している:
  - **位置引数を持たない書き込みが検査ごとスキップされる**。prefilter は `gh` の後ろの
    非フラグトークンで `<issue|pr> <write>` を判定するが、`--body-file=x.md --title=t` の
    ように `=` 形式だけだと判定材料がちょうど 2 個になる。境界を 1 つ狭めると素通りした
    （v0.4.1 で `=` 形式を足したときに、この組み合わせのテストが無かった）
  - **`--body-file` / `-F` の直後以外のトークンをファイルとして読むと誤ブロックする**。
    たまたま実在するファイル名がどこかに現れただけで中身が検査対象に入り、本文が
    きれいでも exit 2 になる

## [0.4.1] - 2026-08-28

### Fixed

- **設定ファイル自己保護の誤検出を直した。** 判定が `$cmd` 全体への正規表現で、
  **引用符を一切見ずに**「破壊的な語 → 設定ファイル名」の並びを探していたため、
  ファイル名を**文字列として書いただけ**のコマンドがブロックされていた:

  ```
  echo 'rm は危険。設定は .claude/<config>.json にある'   → exit 2
  ```

  区切り（`|` `;` `&`）が間に無ければ距離を問わず一致するため、doc を書く・説明する・
  ログに残すといった無害な操作が止まる。**実際に README へ当のファイル名を書こうとして
  作業がブロックされた**（`gh-ref-guard` の実装中）。

  判定をトークナイザの出力（引用符を除去済みの word 列）に対して行うようにした。
  リダイレクト先・破壊的コマンドの引数・`sed -i` / `perl -i` の対象が設定ファイルの
  ときだけ検出する。`sh -c` / `eval` 内は従来どおり再帰解析で届く。
  **自己保護は弱めていない** — 実際に書き換える 24 形（`>` `>>` `>|` の各形・引用符付き
  パス・`command` / `\` / env 代入 / フルパス前置・ネストシェル）が引き続き検出される
- **`>|`（clobber 強制リダイレクト）を pipe として分割していた**。トークナイザが `|` を
  無条件にセグメント区切りとして扱うため、`echo x >| <config>` のリダイレクト先が
  次セグメントへ落ちて**自己保護をすり抜けていた**（上記の修正過程で発見）。
  直前の word がリダイレクト演算子なら区切らないようにした

### Added

- 設定ファイル自己保護の回帰テスト 4 本（言及・読み取り 9 形は黙る / 引用符内の
  破壊的な語は黙る / 実際の書き換え 24 形は検出する / ネストシェル内も検出する）。
  旧実装へ戻すと 18 件が落ちることを確認済み

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
