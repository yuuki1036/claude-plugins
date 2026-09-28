# guardrail-protect

lint / hook / static check の「骨抜き」変更、`git commit --no-verify`、**`gh` で公開する本文の裏取り漏れ**、そして**公開リポジトリへの業務情報の送信**を PreToolUse hook で機械的にブロックする plugin。

AI agent が「赤を消すために linter を緩める」「hook がうるさいから `--no-verify` する」「典拠を確認せずに公開文書へ書く」「業務の名前を実例として公開 issue に書く」逃げ道を構造的に塞ぐ。

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

### 5. 公開先への業務情報送信ブロック（public-leak-guard）

公開リポジトリ・gist へ書き込む操作の本文に、**辞書の語**（業務リポジトリ名・製品名など）や
**このマシンのホスト名**が入っていたら `exit 2` で止める（常時有効）。実装は
`hooks/scripts/public-leak-guard.sh`（入口）→ `detect-public-leak.py`（判定）→
`public_leak_shell.py`（bash の構文解析）。

**宛先の判定は owner ではなくリポジトリの visibility**。`gh api repos/<o>/<r>` の `.visibility` を
`~/.cache/guardrail-protect/visibility.json` に TTL 付き（既定 1 時間）で持ち、**private と確定した
宛先だけ素通し**する。第三者の公開リポジトリ（上流 OSS への issue など）も検査対象になる。

宛先を決められないものは公開先として検査する:

| 渡し方 | 扱い |
|---|---|
| `-R` / `--repo`、issue / PR の URL 引数、`GH_REPO`（コマンドの前置き・hook の環境） | その宛先の visibility |
| 暗黙の解決（`gh repo set-default`、remote の優先順で upstream が origin に勝つ、`{owner}/{repo}` プレースホルダ） | cwd の repo の **GitHub remote 全部**（と `gh-resolved` の値）を候補にし、全部 private のときだけ素通し |
| gist（secret も URL で読める）、`gh api graphql` の mutation（node ID）、`/repositories/<id>`、Project、git リポジトリ外の cwd、visibility を取得できない（404・未認証・時間切れ） | 公開先として検査 |
| ssh の Host 別名（`git@github-work:org/repo`） | `ssh -G` で実ホストを引いて github.com なら visibility を見る |
| ローカルパスの remote | 検査しない |

**対象の操作**:

- Bash の `gh`: issue / pr の create・comment・edit・close / reopen の `--comment`・review、
  `pr merge` の `--subject` / `--body`、`release create / edit / upload`、`gist create / edit / rename`、
  `label create / edit`、`project` の書き込み系、`issue transfer`（非公開→公開の移動は止める）、
  `repo create`（`--public` と `--source` / `--push` なら push される履歴全体を走査）、
  `repo edit --visibility public` と `gh api` での公開化（**常に止める**。人が履歴を確認して手で切り替える）、
  `repo sync --source <非公開>`、`gh api` の POST / PUT / PATCH
- `gh` の呼び方: `gh alias`（`!` のシェル alias も展開）、`env` / `command` / `exec` / `nohup` / `timeout` /
  `sudo` / `nice` の前置き、絶対パスの gh、`\gh`・`"g"h` のような引用符での分割、`xargs` / `find -exec`、
  `bash -c` / `eval` / `bash <<EOF`、`$(…)` の中で実行される gh、コマンド名が変数の呼び出し
- `git push`（`--tags` / `--follow-tags` / `--mirror` / `tag <name>`、`git -C`、git alias）と `gh pr create`
  （head ブランチを push しうる）: `git rev-list <ref> --not --remotes=<remote>` の範囲の
  **追加行・commit メッセージ・作者とコミッター・ファイル名・ブランチ名・annotated tag の名前とメッセージ**
- GitHub MCP（server 名に github を含む）の書き込み系すべて（`get_` / `list_` / `search_` 等の読み取り以外。
  `create_issue`・`add_issue_comment`・`update_issue`・`create_pull_request`・`create_pull_request_review`・
  `merge_pull_request`・`push_files`・`create_or_update_file`・`create_repository`・`create_branch` を含む）
- `mcp__terminal__run_in_terminal`（コマンド文字列を Bash と同じ判定に通す。`cwd` 引数も見る）
- ブラウザ操作（`browser_input: "block"` のときだけ。入力値を辞書とホスト名で照合する。既定は off）

**本文の取り方**:

- `--body` / `--title` などの直書き、`--body-file` / `-F`（相対パスは hook 入力の `cwd` と同じコマンド内の
  `cd` で解決）、`$(cat f)`・`$(< f)`・`<(cat f)`、`-F -` / `--input -` の標準入力（heredoc・here-string・
  `< file`・`cat f |` / `echo … |` のパイプ）、`gh api` の `-f` / `-F` / `--field` / `--raw-field` / `@file` / `--input`
- **同じコマンド内で書いてから読むファイル**（`cat > b.md <<'EOF' … EOF && gh … --body-file b.md`）は
  ディスクではなくコマンドの heredoc を読む（TOCTOU を避ける）。前段に中身を変えうるコマンド
  （`cat` / `echo` / `printf` / `tee` / `cp` / `mv` 以外）があれば解決できない扱い
- 同じコマンド内の変数代入（`B='…'; gh … --body "$B"`）は追う
- **解決できない本文**（変数展開・任意のコマンド置換・何もつながっていない標準入力・インライン
  スクリプトからの gh 呼び出し）は、公開先なら止めて「Write ツールで本文をファイルに書き出し、
  別の Bash 呼び出しで `--body-file <絶対パス>` を渡す」よう案内する
- `git commit … && git push` のように **push の前段で履歴が変わりうる**なら止める（push を別の
  Bash 呼び出しに分ける）

**照合**:

| 種類 | 扱い |
|---|---|
| 辞書の語（1 行 1 語・`#` コメント・`w:` 接頭辞は語境界・3 文字未満は無視・大小文字と全角半角は区別しない） | 止める |
| このマシンのホスト名（`hostname -s`。辞書に書かなくても常に対象） | 止める |
| 許可リスト外のチーム形式の ID（`[A-Z]{2,6}-数字`。組み込みの許可リストと `allowed_id_prefixes` の接頭辞は除外。下の「許可リスト」） | 確認 |
| `/Users/<name>/` のパス（`/Users/Shared/` と `<name>` のような例示は除外） | 確認 |
| `<別リポジトリ名> PR #N`（宛先と同名は除外） | 確認 |
| 画像・動画の添付（`--attach`）、バイナリのリリースアセット | 確認 |
| 非公開で**別 owner** のリポジトリで作業中のセッションから公開先へ書く（辞書に載らない識別子・略称・ドメイン説明を拾えないので、内容に関係なく匿名化を確認させる） | 確認 |

汎用パターンは prose（本文・commit メッセージ・ref 名・tag メッセージ）にだけ当てる。push の
追加行（コード）・ファイル名・作者には辞書とホスト名だけを当てる。照合の前に SRI の integrity 値・
長い base64・16 進ハッシュを消す（3 文字の語が `sha512-…` に偶然入って push が止まる誤検知の対策）。

**チーム形式の ID の許可リスト**: 次の 2 つを合わせたものに当たる接頭辞は確認に回さない。
設定の `allowed_id_prefixes` は組み込みに**足す**（置き換えない。組み込みを外す設定は無い）。
照合は接頭辞全体の一致で、`TEAM` を許しても `TEAMB-1` は許さない。

- 組み込み（規格名・例示語。設定が無くても効く）: `ADR` `UTF` `SHA` `ISO` `RFC` `CVE` `CWE` `GHSA`
  `HTTP` `TLS` `SSL` `IPV` `ES` `ECMA` `GPT` `AES` `RSA` `PEP` `WCAG` `JSR` `JEP` `KEP` `MD` `ARM`
  `TEAM` `PROJ` `ABC` `XXX` `FOO` `BAR` `MYAPP` `EXAMPLE` `ISSUE` `ID` `PR`
  （`PR` は `業務 PR-3` のように PR 番号を伏せた呼び名のため）
- 設定の `allowed_id_prefixes`（既定は空）: 自分のチームの接頭辞と、公開 issue で業務の ID を
  置き換えるのに使う架空の接頭辞。**入れないと自分の commit メッセージやブランチ名の `YAT-83` でも止まる**
  （推奨設定は下の「セットアップ 2」）

**「確認」は既定で止める（`confirm_action: "block"`）**。公式 docs（hooks の PreToolUse decision control）
によると `permissionDecision: "ask"` は、対話ユーザーがいないとき（`-p`、auto mode、dontAsk、
bypassPermissions、subagent / background agent）に `"defer"` へ落ちて通常の権限フローに任される
＝**止まらずに通りうる**。hook 入力の `permission_mode` と `agent_id` で auto / dontAsk / bypassPermissions /
subagent は見分けられるが、**`-p` は見分けられない**。`confirm_action: "ask"` にすると
`permission_mode` が default / acceptEdits / plan で `agent_id` が無いときだけ ask を返し、それ以外は止める。

**fail-closed**: safe-hook.sh の縮退（すべて exit 0）は流用しない。PreToolUse の hook は exit 2 以外の
非ゼロでも timeout でも止めずに通る（公式 docs）ので、次の場合は公開につながる入力なら exit 2 にする:
内部エラー、python3 が無い、検出器が壊れている、辞書・設定が読めない、hook 入力が壊れている、
自分で決めた時間（既定 7 秒。hook の timeout は 10 秒）を超えた、push の走査が上限
（既定 300 commit / 4MB）を超えた。

**出力には語そのものを出さない**。辞書の行番号・本文の行番号・置き換え例（「業務リポジトリ A」
「TEAM-123」「m2」など）だけを出す。語を含むパス・ファイル名は `<伏せ字 sha=…>` にする。

**迂回の防止**（宛先に関係なく止める）: `GUARDRAIL_*` 変数の前置き・`export`・`env`・`env -u`・`unset`・
`launchctl setenv`、シェル設定・settings への書き込み、辞書・設定・visibility キャッシュ
（`~/.config/guardrail-protect/`・`~/.cache/guardrail-protect/`・環境変数で指した先）の Bash での書き換え
（`cd` してからの相対パスも解決する）。Edit / Write 経路は `pre-config-guard.sh`、Bash 経路は
`detect-commit-bypass.pl` の自己保護にも同じ対象を足した。

**code-review の publish 設定 dir（`~/.config/claude-review/`）も同じ扱い**。中の `post-publish` は
review の publish のたびに切り離して実行されるので、agent が置くと以後の publish で黙って走る。
`machine-label`・`salt` は計測に載るマシンの label を決める（計測リポジトリの `forbid-terms.txt` も
この dir にある）。dir の中への Edit / Write と Bash での書き換え、dir そのものの置き換え、
場所を変える変数（`CLAUDE_REVIEW_CONFIG_DIR`・`REVIEW_METRICS_CONFIG_DIR`）をシェル設定・settings に
書き込む操作を止める。hook の環境でその変数が設定されていれば、指した先も守る。読むだけの操作
（`cat`・`ls`）と、テストの隔離のためにコマンドの前に `CLAUDE_REVIEW_CONFIG_DIR=<使い捨て dir>` を
置く実行は止めない。これらのファイルは人が Claude の外で置く（手順は code-review と計測リポジトリの README）。

### 6. zsh で壊れる書き方のブロック（zsh-trap-guard）

Bash tool のシェルが zsh のとき（`CLAUDE_CODE_SHELL`、無ければ `SHELL` で判定）、bash の前提で書くと
エラーになるか黙って別の値になる書き方を `exit 2` で止める（常時有効・opt-in 不要）。シェルが zsh で
なければ何もしない。

| 規則 | 例 | zsh で起きること |
|---|---|---|
| 波括弧なしの展開の直後の `:` + 修飾子の文字 | `git show "$sha:code-review/x"` | `:c` が修飾子として食われ、別のパスになる（空出力で黙る） |
| `path` / `status` への代入 | `while read -r path; do git …` / `status=$(…)` | `path` は PATH と連動し以降が command not found、`status` は読み取り専用 |
| 語頭の `=` | `[ "$a" == b ]` / `echo =====` | `=cmd` 展開で `= not found` |
| オプション値の引用なしグロブ | `grep --include=*.sh` / `find -name *.py` | 一致しないグロブがエラー（`no matches found`） |
| echo の引数のエスケープ（**止めずに警告だけ**） | `echo "a\nb"` | zsh の echo は `\n` などを解釈する |

止めたときは箇所と書き直し方（`${VAR}` で囲む・引用する・別の名前にする）を stderr に出す。過去の
transcript の Bash 呼び出し 22,307 回で測ると、上の 4 規則は計 410 回当たり、目視で誤検出は 0 件だった。
echo だけは 3 回・実害を確認できなかったので止めていない。zsh が字面どおりに読む形（`"${sha}:code"`・
`"$sha":code`・`$h:8080`・`[[ a == b ]]`・`ls *.md` のようなファイルのグロブ）は止めない。
解析できないコマンドも通す。


## public-leak-guard のセットアップ

**導入した直後は公開先への書き込みが止まる**（辞書が無いと止める既定）。次の 2 ファイルを
**リポジトリの外に**置く。どちらも Claude からは編集できない（自己保護）ので、人がエディタで作る。

### 1. 辞書 `~/.config/guardrail-protect/sensitive-terms.txt`

```text
# 業務リポジトリ名・製品名・社内の略称など（1 行 1 語。辞書そのものは絶対に commit しない）
AcmeCorp
ProjectFalcon
# w: を付けると語境界で照合する（短い語の誤検知を減らす）
w:acm
```

- 探索順は `$GUARDRAIL_SENSITIVE_DICT` → `~/.config/guardrail-protect/sensitive-terms.txt`
- 辞書が無い・有効な語が 0 件のときは、公開先宛てを止める（`on_missing_dict: "warn"` なら警告して通す）
- ホスト名は辞書に書かなくても常に対象

辞書と設定の有無による挙動（「書き込み」は上の「対象の操作」。読み取り系の gh（`issue view`・
`api` の GET など）、送信しない git（`status`・`log`・`commit` など）、gh / git を含まないコマンドは、
どの状態でも止めない）:

| 状態 | 公開先への書き込み | private と確定した宛先への書き込み |
|---|---|---|
| 辞書あり | 語・ホスト名に当たれば止める。汎用パターンは確認（既定は止める） | 通す |
| 辞書が無い・有効な語が 0 件（既定の `on_missing_dict: "block"`） | 本文が清潔でも止め、辞書の置き場所を案内する | 通す |
| 同上で `on_missing_dict: "warn"` | 警告（`systemMessage`）を付けて通す。ホスト名と汎用パターンは引き続き見る | 通す |
| 設定ファイルが無い | 下の「すべてのキーと既定値」で動く（`allowed_id_prefixes` は空なので組み込みの許可リストだけ） | 通す |
| 辞書・設定を読めない（壊れた JSON・ディレクトリ・権限） | 止める | **止める**（宛先を判定する前に止める） |

### 2. 設定 `~/.config/guardrail-protect/public-leak-guard.json`（任意）

推奨設定（このリポジトリの持ち主の例）。書くのは既定から変えるキーだけでよい:

```json
{
  "allowed_id_prefixes": ["YAT", "TEAM", "TEAMB", "TEAMC", "TEAMD", "TEAME"]
}
```

- `YAT`: 自分のプロジェクトの Linear の接頭辞。commit メッセージ・ブランチ名・PR 本文に `YAT-83` を書ける
- `TEAM`〜`TEAME`: 公開 issue で業務チームの ID を置き換えるときの架空の接頭辞（`TEAM-123`・`TEAMB-45`）。
  `TEAM` は組み込みにもあるが、置き換え用の組として並べておく。業務チームの本物の接頭辞は**入れない**
- `業務 PR-3` のような PR 番号の呼び名は組み込みの `PR` で通る。`m2.jsonl`・`~/<work>/` のような
  置き換え済みの表記はどのパターンにも当たらない

すべてのキーと既定値:

```json
{
  "allowed_id_prefixes": [],
  "confirm_action": "block",
  "on_missing_dict": "block",
  "pass_visibilities": ["private"],
  "visibility_ttl_seconds": 3600,
  "max_push_commits": 300,
  "max_push_bytes": 4000000,
  "browser_input": "off",
  "deadline_seconds": 7
}
```

| キー | 意味 |
|---|---|
| `allowed_id_prefixes` | 確認に回さないチーム形式の ID の接頭辞。組み込みの許可リスト（上の「照合」）に足される。入れないと commit メッセージやブランチ名の `YAT-83` でも止まる |
| `confirm_action` | 確認の扱い。`block`（既定）/ `ask`（対話セッションでだけ ask。上の注意を参照） |
| `on_missing_dict` | 辞書が無いとき `block`（既定）/ `warn` |
| `pass_visibilities` | 素通しする visibility。組織の `internal` を素通ししたいなら足す |
| `visibility_ttl_seconds` | visibility キャッシュの有効秒数 |
| `max_push_commits` / `max_push_bytes` | push の走査上限。超えたら止める |
| `browser_input` | ブラウザ操作の入力を辞書で照合するか（`off` / `block`）。業務でブラウザを使う機械では off のまま |
| `deadline_seconds` | 自分で打ち切るまでの秒数（0.5〜8） |
| 場所 | `$GUARDRAIL_PUBLIC_LEAK_CONFIG` → `~/.config/guardrail-protect/public-leak-guard.json` |

visibility を引くので、**その機械の `gh` が宛先を見られること**（`gh auth status`、org の SSO 承認）。
見られない private リポジトリは公開先として検査され、業務のコードに辞書の語が入っていれば push が止まる。

### 3. 公開リポジトリの pre-push（人の push・他のツールの push も止める）

PreToolUse は Claude が打つコマンドしか見ない。**公開リポジトリごとに**同じ検出器を呼ぶ git hook を入れる。
**global の `core.hooksPath` は使わない**（業務リポジトリの husky 等を上書きする）。

```bash
PLG=~/.claude/plugins/marketplaces/yuuki1036-claude-plugins/guardrail-protect

# .git/hooks を使うリポジトリ（worktree でも共通の hooks に入る）
ln -s "$PLG/git-hooks/pre-push.sh" "$(git rev-parse --git-common-dir)/hooks/pre-push"

# core.hooksPath を使うリポジトリ（例: .githooks）では、そのディレクトリの pre-push から呼ぶ
#   #!/usr/bin/env bash
#   exec "$HOME/.claude/plugins/marketplaces/yuuki1036-claude-plugins/guardrail-protect/git-hooks/pre-push.sh" "$@"
```

- push 先が private と確定すれば素通し。公開・不明なら push される範囲を辞書とホスト名で照合し、
  当たれば止める（`confirm_action: "block"` なら汎用パターンの確認項目も止める）
- 検出器が見つからないときも止める。人の判断で外すなら `git push --no-verify`
- 手で確かめる: `python3 "$PLG/hooks/scripts/detect-public-leak.py" scan-git --repo . origin/main..HEAD`
  （範囲の上限なし）、`… scan-text body.md`（本文の事前検査）


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
- **検査されない渡し方**（見出し参照の検証 = 機能 3 のみ）: コマンド置換（`--body "$(cat x.md)"`）・変数展開・`-F -`（stdin）。`gh api` / `gh release` / `gh gist` も対象外。公開先ガード（機能 5）はこれらも解析する
- **公開先ガード（機能 5）で塞げないもの**: スクリプトファイルの中から呼ぶ gh（`bash post.sh`。中身は読まない）、
  plugin の hook スクリプト自身が呼ぶ gh、ユーザーのシェル alias / 関数、画像・動画の中身（確認として止める）、
  バイナリファイルの中身（push ではファイル名だけ見る）、人が Web UI・モバイル・GUI クライアントで投稿するもの、
  hook が入っていない機械・cloud session・scheduled agent・Actions の中の gh、`curl` などで GitHub API を
  直接叩くもの。push に限っては公開リポジトリごとの pre-push（上のセットアップ 3）で塞げる。
  辞書に載らない識別子・略称は、非公開・別 owner のリポジトリで作業中のセッションに限り「確認」で拾う
- **public-leak-guard の既知の誤検知の型**: GitHub 以外の push 先（visibility を引けないので常に検査）、
  `gh` から見えない private リポジトリ（同上）、コマンド名が変数で次の語が `issue` / `push` 等の呼び出し
- **ブロックされたときの回避**: 参照の書き方を変えるか、guardrail-protect を無効化する（**プラグイン単位**。commit 迂回ガードも同時に外れる）。`.claude/guardrail-protect.json` はこの hook を制御しない（設定ファイル保護のみ）
- **config 自己保護**: `guardrail-protect.json` 自体は Edit/Write/MultiEdit（`pre-config-guard.sh`）と Bash 書き込み（`detect-commit-bypass.pl`）の両経路で常にブロック対象。保護スコープを変える場合は Claude 外で人間が編集する。public-leak-guard の辞書・設定・visibility キャッシュ（`~/.config/guardrail-protect/`・`~/.cache/guardrail-protect/`・`public-leak-guard.json`・`$GUARDRAIL_SENSITIVE_DICT` / `$GUARDRAIL_PUBLIC_LEAK_CONFIG` の指す先）と、code-review の publish 設定 dir（`~/.config/claude-review/` の `post-publish`・`machine-label`・`salt` など。`$CLAUDE_REVIEW_CONFIG_DIR` / `$REVIEW_METRICS_CONFIG_DIR` の指す先）も同じ扱い。Bash 経路の `detect-commit-bypass.pl` は `cd` してからの相対パスと `chmod` を見ない（`detect-public-leak.py` 側が止める）

## CHANGELOG

[CHANGELOG.md](CHANGELOG.md) 参照。
