# 前回の指摘への修正（self-review 限定 / GitHub issue #298）

前回の self-review の Step 7 で修正を選んだ指摘を記録し、次の self-review で今回の diff と照合して、範囲を絞った回でも検証済みにしない仕組み。記録・照合・消去の正本は `scripts/prior-fixes.sh`（本体は `scripts/lib/prior_fixes.py`）。`--embed` で呼ぶ feature-dev は Step 7 を通らないので、前回の対象を `--prior-findings` で渡す（4 節 / GitHub issue #313）。reviewer への渡し方は記録分と同じ（照合の違いは 4 節）。

**読むタイミング**: Step 1 で `## prior-fixes` が出たときと、Step 7 で修正を選んだとき。どちらも無い回は読まない。

- **なぜ要るか**: 指摘を受けた修正は、指摘されたケースだけに合わせた狭い直し方になりやすく、最も見直しが要る行になる。ところが `--focus` や共通ブロックのスコープで「前回以降」に絞ると、その修正も「前回以前」に入って検証済みになり、どのレビューにも見られなかった（実測: 5 回の self-review で報告 0 件にした PR が、外部レビューで、直したフラグが同じ形の別の 2 ケースを拾っていないと指摘された）

## 1. `## prior-fixes` が出た回（Step 1 → Phase 0 → Step 4 → Step 6）

出力は、前回の Step 7 で修正を選んだ指摘のうち、今回の diff が触ったファイルの分（`file:line<TAB>観点<TAB>要旨`。行番号は指摘した時点のもので、修正でずれていることがある）。次の 3 つを守る:

- **絞り込みの例外**: `--focus` / `--exclude` や共通ブロックのスコープ（「前回以降」など）で範囲を絞った回でも、この行を検証済み（`already verified`）に入れない。各行の観点の reviewer を構成に入れ（`--focus` に無い観点でも入れる）、その reviewer の担当ファイルに当該ファイルを含める。実効上限に収まらなければ既存の reviewer に相乗りさせる — **ただし `--since` の回は triage-guide.md `### 6.5` に従い、effort 上限の内側では相乗りにせず専任を起動する**
- **観点のキーが reviewer の観点でない行**: `specialist-*` はその specialist を red-flag の有無によらず起動して割り当てる（修正が red-flag の形を消すと、delta では起動しなくなる）。`recall-skeptic` / `meta` / 語彙外のキーは reviewer-bugs に割り当てる（skeptic と meta は前回の対象を受け取らない層なので、確かめ役にならない）
- Step 4 で、**reviewer と specialist のプロンプトにだけ** `prior_fixes:` として各行をそのまま並べる（読み方は `${CLAUDE_PLUGIN_ROOT}/references/prompts/reviewer-common.md`「前回の指摘への修正」）。共通ブロックには入れない — 共通ブロックは skeptic にも届き、前回の指摘が渡ると findings 非注入の独立性が崩れる（#313）
- Step 6 のレポートの `**前回の指摘への修正**` の行に、確認対象に戻した件数と観点を出す

## 2. 記録する回（Step 7）

「すべて修正」「BLOCKER/CRITICAL のみ」で修正を終えたら、修正した指摘を記録する（コマンドは SKILL.md の Step 7）。`file` は repo のルート相対、`focus` は観点判定表のキー、`title` は指摘の要旨。

- 記録は作業ツリーに 1 ファイルで、中をブランチ別に持つ。同じブランチで記録し直すと、そのブランチの前回の分を置き換える
- 「このまま」の回は記録しない。`--embed` の回は Step 7 自体を通らないので記録しない（feature-dev の G-V ループは、前回の対象を `--prior-findings` で、範囲を `--since` で渡して見直す / #313）
- detached HEAD ではブランチ名が常に `HEAD` になり、無関係な作業の記録と一致するので、記録も照合もしない
- 書き込めなかった回（一時ディレクトリを作れない等）は `WARN:` を出して exit 1 で終わる。レビューは続けてよい（次の回は照合を飛ばすだけ）

## 3. 消す回（publish）

self-review の publish（Step 6.4）が `prior-fixes.sh clear` を呼び、**今回の diff に入った分だけ**を記録から消す（この回の Step 1 が照合して reviewer に渡した分）。diff に入らなかった分は reviewer に渡っていないので、次の回へ持ち越す。

- **publish が最後まで通らなかった回は消えない**。payload の不備で `FATAL:` になった回・`--dry-run` の回は clear の前に終わるので、照合済みの行が次の回にもう一度出る。害は reviewer が同じ行を余分に見るだけなので、publish をやり直して通せばよい（dry-run は状態を進めない契約なので、そこで消すようには変えない）
- diff が無く照合できなかった回（base を特定できず Step 1 の照合を飛ばした等）は消さない

## 4. `--prior-findings` の形（正本 / GitHub issue #313）

self-review の `--prior-findings=<path>` で渡す前回の対象。feature-dev の `gv-loop.py` が書き、code-review が読む（両プラグインの境界の契約なので、形を変えるときは両方の版を合わせて上げる）。

- **形は `prior-fixes.sh record` の stdin と同じ**: JSON 配列 `[{"file": ..., "line": ..., "focus": ..., "title": ...}]`。検査も記録と同じ（`file` の無い項目・repo の外の絶対パスは捨てる。改行・タブは潰す）
- **使えないファイル**（読めない・JSON でない・配列でない・空でないのに使える項目が 0 件）: triage-signals.sh が `fallback=prior-findings-unreadable` で `--since` も無視し、diff 全体で続ける（前回の対象なしに delta だけを見ると、修正が対象の行に触れなかった回に、直っていない指摘を誰も見ない）。一部の項目だけが無効なら、捨てた件数を WARN に出して残りを使う
- **照合**: 記録分は今回の diff に入ったファイルの分だけを出すが、`--prior-findings` の分は diff で絞らない（修正が base の状態へ戻したファイルは diff 全体から外れる。そのファイルの対象こそ確かめる）。記録分と同じ `file:line:focus` の `--prior-findings` の分と、`--prior-findings` の中で重複した分は捨てる（記録分どうしと、行の無い項目は畳まない）。制御文字を含むパスと repo の外を指すパスも捨てる。ヘッダは `recorded=<記録の件数> extra=<使えた件数（形の違う項目と上限超過を捨てた後）> in_diff=<出した行数>`
- **並び順と上限**: 書き手は古い順（後ろほど新しい）に並べる。上限は 50 件（記録と同じ）で、超えたら前から捨てて WARN を出す（直前の回の対象が残る）
- **detached HEAD でも出す**（記録はブランチ名で照合するので使わないが、渡された分は記録に頼らない）
- **記録には書かず、publish の clear でも消さない**（呼び出し元が毎回渡す）
