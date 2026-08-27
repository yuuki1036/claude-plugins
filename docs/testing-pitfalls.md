# テストの落とし穴（この repo で実際に踏んだもの）

`.claude-plugin/scripts/tests/` にテストを足すとき・直すときに読む。**すべて実測で踏んだ型**で、
共通する性質は「**テストは緑のまま壊れる**」こと — 落ちてくれるなら気づけるが、ここに挙げた
失敗はどれも「検出しなかった」と「検出できなかった」の区別を消す。

CLAUDE.md の Gotchas には規範だけを 1 行で置き、経緯と実測はここに集約する。

## 1. 環境の「不在」に頼らない（Linux CI でだけ落ちる型）

ローカル（macOS）で通って CI（ubuntu）で落ちる型。pre-commit は開発機でしか走らないので、
**この種の失敗は原理的に push 前に検出できない**。

### ① PATH を絞るときは「引けるもの」を列挙する

「このディレクトリには無いはず」に頼らない。Linux の `/bin` は `/usr/bin` の symlink で、
CI には `gh` も `jq` も `python3` も入っている。**引ける側を作る**（手本:
`hook_harness.HookTestCase.path_with_only()` / `test_auto_quality_check.py` の `env(with_encoder=False)`）。

### ② 使い捨てリポジトリは**リポジトリ側**に author を設定する

env の `GIT_AUTHOR_*` は init commit にしか効かない。global config の無い CI でだけ黙って
`git commit` が失敗し、rename が「新規ファイル」に化ける。`git config user.email` を打つ。

### ③ PATH を絞る場面の stub は bash builtin だけで書く

`cat` すら引けない。stub が落ちると出力が空になり、**「指摘なし」と区別できない**
（実測: `cat <<EOF` の stub が `command not found` で死に、テストが緑に見えていた）。

### ④ ライブラリの不在は探さず**作って再現する**

`raise ImportError` する同名パッケージを `PYTHONPATH` の先頭に置く。

### ⑤ 書き込み先を決める環境変数は継承させない

`CLAUDE_PROJECT_DIR` は event bus の出力先（`${CLAUDE_PROJECT_DIR:-$PWD}`）で、本スイートは
**Stop hook / self-review 前段からも走る＝そこではこの変数が入っている**。継承すると publish が
実リポジトリの `.claude/events.jsonl` へ飛び、

- publish を見るテストは落ちる（実測 3 件）
- **黙るはずのテストは緑のまま**「publish しなかった」と「別の場所へ publish した」を区別できない
- 実リポジトリの計測データが汚れる（実測: 偽イベント 20 件が `review-retro` の母数になっていた）

テスト専用の使い捨てディレクトリを指す（`hook_harness` は指定が無ければ自動でそうする）。

### ⑥ プロセス表は使い捨てリポジトリで隔離できない

検査対象が `pgrep` で他プロセスを見るなら、その `pgrep` を **stub に差し替える**。
**PATH から外さない** — `command -v` が偽だとその経路ごと短絡し、一度も実行されないテストになる。

実例: `auto-quality-check.sh` は変異テスト中かを `pgrep -f mutation-test.py` で判定するので、
**このスイート自身が変異テストの中から走る CI の `mutation-test` ジョブ**で全ケースが
スキップ経路へ落ちた（21 件）。**環境差ではなく実行文脈の差**なので pre-commit では踏めない。

### ⑦ git を叩くテストは `git_env.scrub()` を通す

正本は `.claude-plugin/scripts/tests/git_env.py`。git は hook 実行時に `GIT_DIR` 等を子へ渡し、
**`cwd` 指定より優先される**。メインリポジトリからの commit では `GIT_DIR=.git` の相対パスなので
無害だが、**linked worktree からの commit では絶対パス**になり、使い捨てリポジトリのつもりの
`git init` / `commit` が**実リポジトリ**に当たる。

実測（issue #158）: 作業ブランチが `init` コミット 340 個に乗っ取られ、`core.bare` が `true` に
反転して `git status` が通らなくなった。**壊れ方が「テストが 128 件落ちる」なので、最初に疑うのは
自分の変更**になる。⑦は逆に pre-commit（開発機）でしか踏めない（CI は worktree を作らない）ので、
`test_git_env_isolation.py` が汚染環境を**作って**再現する。

> テストから直接 `git` を呼ばない。`TempGitRepo` のメソッド（`commit` / `branch`）を使う。
> 直接呼ぶと `test_git_env_isolation` の「git を叩くモジュールは代表テストを持つ」規約に掛かる。

### 実測サマリ

①〜③で CI が 6 件・⑤で Stop hook 経由が 3 件・⑥で CI が 21 件落ちた（#139 / #140）。

## 2. hook スクリプトは `hook_harness.py` でテストする

hooks.json を経由せずスクリプトを直接叩き、**発火する条件より「黙る条件」を厚く**書く
（暴発の blast radius が最大だから）。`safe_hook_input` の参照有無は静的検査で見ているが、
**その自己判定が実際に効くか**は実行しないと分からない（実測: 最初の 19 テストで publish が
丸ごと落ちる欠陥を 3 件検出した）。

不正 JSON を流したいときは `run_hook(raw=...)` を使う（`json.dumps` を通す経路では
「壊れた payload でどちらに倒れるか」を構造上テストできない）。

**rc だけを見ない**。safe-hook の正常系も ERR trap も exit 0 なので、
「ガードで黙った」と「途中で死んだ」は stderr の `Unexpected` の有無で見分ける。

## 3. 検証機構の期待値をその機構自身で生成しない

壊れていても全件 pass する。実例（v2.63.1）: SSoT pin の初期ハッシュを未テストの
`_slice_section` で作ったため、節の 46% が無保護なまま 14 pin 全部が ok に見えた。
**期待値はテスト側で独立に構築する**（手本: `test_digest_matches_independently_computed_expectation`）。

## 4. テストの置き場所

`.claude-plugin/scripts/tests/` に置く（プラグイン配下に置かない — 配布物にテストが混ざる）。
ハーネスは python の subprocess で、bats 等の外部依存を足さない。
判断の経緯: `code-review/CHANGELOG.md` v2.68.0。

## 5. 起動口は `run-tests.py`

素の `python3 -m unittest discover` でも走るが、その経路には**テストが起動したプロセスの
残留を検出・回収する仕組みが無い**（実測: テストは緑のまま 12 本が 4 時間回り続けた / #140）。
