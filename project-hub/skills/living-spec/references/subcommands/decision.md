<!-- 正本依存（SSoT pin）。本ファイルは format-spec.md の、続く pin の節を言い換えている。正本の節が変わったら、その節を言い換えている箇所を確認して pin を打ち直す（`--update-ssot-pins` は repo 全体を一括で打ち直す） -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#2.1 @8de17e9c -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#3 @d620c24e -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#4 @0375a0e6 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#8 @bec4708d -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#9 @3d83e7f4 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#10 @fe9a7606 -->

## Phase 5: decision — Decision log への append と関連 OQ の close

**このサブコマンドが双方向参照を成立させる唯一の場所**。ここが片方向で止まると maintain 段 3 が Critical を出す。

1. 対象ファイルを Read する
2. W2 で `D<max+1>` を採番する。**採番した番号が frontmatter の `spec_table_frozen_by` と同じなら、書き込まずに報告して終了する**（凍結の宣言が、まだ無い Decision を指していた＝手編集の誤記。このまま書くと、この Decision が凍結の根拠として読まれる）:
   ```
   frontmatter の凍結の宣言が、まだ無い D<n> を指しています（壊れた宣言）。先に /living-spec spec --unfreeze を D# なしで実行して消してください。凍結し直すなら、そのあと --freeze D<凍結の経緯を書いた Decision> を実行します（無ければ先に /living-spec decision で残す）。
   ```
3. **関連 OQ を選ばせる**。コメント除去後に `status: open` の OQ を列挙し、AskUserQuestion で確認する（multiSelect）:
   - question: 「この決定が close する OQ を選んでください」
   - header: 「関連 OQ」
   - options: open な OQ ごとに「`OQ<n>`: <問いの先頭 40 字>」（**先頭に「なし（OQ を close しない）」を置く**。決定が既存の問いに対応しないことは普通にあるため）。AskUserQuestion の options は 4 件までなので、OQ の options は「なし」を除いて 3 件までにする。並べる順は、decision の text が名指しした `OQ<数値>`、text の語と問いの語が一致する OQ、残りは番号の大きい順。並べきれなかった OQ は question の文の末尾に `OQ<n>`: <問いの先頭 20 字程度> の形で並べ、選ぶなら Other に書いてもらう。Other で受けた `OQ<数値>` は、OQ 台帳に `status: open` の行があるかを確かめ、無ければ書き込む前に報告して聞き直す（closed の OQ を選ぶと、5 で close し直すことになる）
   - open な OQ が 0 件なら**この確認を飛ばす**（選択肢が無いのに問わない）
3.5. **覆す確定の項目を選ばせる**（GitHub issue #320）。仕様表に `確定` の行が 1 つ以上あり、凍結していなければ（Phase 6 冒頭の「凍結の判定」）、AskUserQuestion で確認する（multiSelect。3 の確認と同じ呼び出しにまとめてよい）:
   - question: 「この決定が覆す確定の項目を選んでください」
   - header: 「覆す項目」
   - options: `確定` の行ごとに「<項目>（関連 Issue: <関連 Issue>）」（**先頭に「なし（確定を覆さない）」**。多くの決定は新しいことを決めるだけなので）。3 と同じく、項目の options は「なし」を除いて 3 件までにする。並べる順は、decision の text が名指しした項目、text の語と項目名の語が一致する行、残りは `since` の新しい順。並べきれなかった項目は question の文の末尾に項目名で並べ、選ぶなら Other に書いてもらう。Other で受けた項目は、仕様表に同じ項目名の `確定` の行があるかを確かめ、無ければ書き込む前に報告して聞き直す（4 の `関連 Issue` と 8 の報告を、この行から作るため）
   - `確定` の行が 0 件か凍結中なら**この確認を飛ばす**
3.6. **同じ対象を決めた既存の Decision を探す**（GitHub issue #553）。decision の text（とユーザーが挙げた根拠）から対象の語を取り、コメント除去後の Decision log の見出しと `根拠` の bullet（その下の子 bullet を含む）を検索する。語の一致で探すので取りこぼしがある。語を変えて 2〜3 回引く（別名・上位の語・仕様表の項目名）。決定の text が `D<数値>` を名指ししていて、その Decision が log にあれば、検索の結果に関わらず候補に入れる。候補の D<m> を見直した後の Decision（見出しが `D<m> の見直し` を含むもの）も、見直しが続く限り辿って候補に入れる（古い方だけを選ばせると、同じ D<m> の見直しが 2 本に分かれる）。同じ対象を決めた Decision が 1 件以上あれば、AskUserQuestion で確認する（multiSelect。3・3.5 と同じ呼び出しにまとめてよい。検索は呼び出しの前に済ませる）:
   - question: 「同じ対象を決めた Decision があります。この決定で見直す Decision を選んでください」
   - header: 「既存の D#」
   - options: 見つけた Decision ごとに「`D<m>`: <見出し>（<日付>）」（**先頭に「なし（対象が別なので関係ない）」**）。AskUserQuestion の options は 4 件までなので、Decision の options は「なし」を除いて合計 3 件まで（名指しされたものを先に、残りは新しい順）にする。並べきれなかった D# は question の文の末尾に並べ、選ぶなら Other に書いてもらう。Other で受けた `D<数値>` は、`### D<数値>: ` の見出しが log にあるかを確かめ、無ければ書き込む前に報告して聞き直す（append-only なので、誤った D# を見出しに書くと直せない）
   - 見つからなければ**この確認を飛ばす**
   - Decision が 100 件を超える living spec では、記憶だけでは拾えない。逆向きの決定を新しい Decision として重ねると、どちらが今の決定かが読めなくなる
   - 3・3.5・3.6 を 1 回の呼び出しにまとめても問いは 3 つで、AskUserQuestion の 1 回 4 問の上限に収まる
4. **Decision log に append する**（4 節の形式。bullet のキーと順序は固定）:
   ```
   ### D<n>: <text を要約した見出し>
   - 日付: <TODAY>
   - 確信度: <高|中|低>
   - 根拠: <なぜこう決めたか>
   - 出典: <ファイルパス / URL / 会話。無ければ ->
   - 残: <この決定で残った未確定。無ければ ->
   - 関連 OQ: <OQ1, OQ3 形式。close しないなら ->
   - 関連 Issue: <ABC-12, #308 形式>
   ```
   - 3.6 で Decision を選んだときは、見出しを `### D<n>: D<m> の見直し: <要約>` にする（複数なら `D2 の見直し, D5 の見直し: <要約>` と D# ごとに書く。hub-living-spec が `D<m> の見直し` の文字列で後の見直しを探すため）。見直される側の既存エントリには何も書き足さない（append-only）
   - 3.5 で項目を選んだときは、`根拠` の下に子 bullet `  - 覆した確定: <項目>, <項目>` を置く（選んだ項目名を仕様表の表記のまま並べる）。見出しや `根拠` の文に項目名が入るとは限らないので、hub-living-spec はこの文字列で、覆された `確定` の行を探す
   - **`関連 Issue` の行は任意**（7 番目。4 節）。3.5 で選んだ項目の `関連 Issue` の和集合（`-` を除く）と、ユーザーが挙げた Issue を書く。どちらも無ければ**行ごと書かない**（`- 関連 Issue: -` を書かない）
   - `確信度` / `根拠` / `残` はユーザーの入力から埋める。読み取れなければ**推測で埋めず**、`確信度: 中` を既定にして `根拠` に与えられた文言をそのまま置く
   - 補足・内訳・但し書きは、該当する bullet の下にインデントした子 bullet で書いてよい（4 節）。散文の段落・引用ブロックは置かない
   - 既存エントリは**絶対に編集しない**（append-only。4 節）
5. **選ばれた OQ を close する**（同じファイルへの in-place 更新）。各 OQ 行を次のように Edit する（**セル区切りは単一スペース。カラム整列のパディングを入れない**。Edit は完全一致置換なので、見た目を整えると `old_string` が一致しなくなる）:
   ```
   | OQ<n> | <問い> | open | - | <since> |
   →
   | OQ<n> | <問い> | closed | D<新番> | <TODAY> |
   ```
   - `status` を `closed` に、`関連 D#` を新しい `D<n>` に、`since` を `<TODAY>` に更新する
   - **行は消さない**（W3）。`status` の書き換えだけで表現する
   - 既に `関連 D#` が入っている場合はカンマ + 半角空白で追記する（`D1, D3`。8 節）
6. **双方向参照を Read で検証する**（adr-keeper の supersede が新旧を Read で相互参照確認するのと同じ規律）: 書き込み後にファイルを Read し直し、**両方向を**確認する:
   - **Decision → OQ**: Decision の `関連 OQ` に挙げた各 `OQ<n>` が、OQ 台帳で `closed` かつ `関連 D#` に当該 `D<n>` を含むこと
   - **OQ → Decision**: 今 `closed` にした各 OQ の `関連 D#` に入れた `D<n>` が、Decision 側の `関連 OQ` にその `OQ<n>` を含むこと（step 5 で close したのに Decision の `関連 OQ` に載せ忘れた経路を捕まえる）
   - 片方向になっていたら**その場で直す**（maintain の事後検知に回さない。ここで直せる）。ファイルは既に Read 済みなので追加コストはない
7. W4 で `last_updated` を更新する
8. 報告:
   ```
   ✅ D<n> を追加しました（.claude/living-specs/<slug>.md）
     <見出し>

   close した OQ: OQ1（<問いの先頭 20 字程度>）, OQ3（<同>）（双方向参照を検証済み）
   残る open な OQ: <残数> 件
   ```
   OQ は番号だけでは読めないので、問いの先頭を添える。
   3.6 で Decision を選んだときは、続けて `見直した Decision: D2（<見出しの先頭 20 字程度>）, D5（<同>）` の形で出す。
   3.5 で項目を選んだときは、続けて次を出す（Issue の状態（仕掛中・未着手・完了）で分けるのは、トラッカーを読む側の仕事。living spec はトラッカーを読まない）:
   ```
   覆した確定の項目:
   - <項目>（関連 Issue: <ID, …> / 無ければ「関連 Issue なし」）
   これらの Issue は、覆す前の決定に沿って書かれています。Issue の本文・作業中の実装を直すかを確かめてください。
   仕様表の行は /living-spec spec <項目> <確度> で更新してください（内容は直接 Edit で直す）。
   ```

> **スコープ外と分かった OQ**も decision で閉じる。見出しを `### D<n>: スコープ外: <要約>` にし、`根拠` に到達点の外だと判断した理由を書く。あわせて「進め方フェーズ」の「スコープ外」小見出しに 1 行残す（template.md のコメント参照）。

> **OQ の reopen は許容しない**（`format-spec.md` 3 節）。close 後に議論が再燃したら、`/living-spec oq` で**新しい OQ を起票**し、その問いの中で旧 OQ / D# を参照する。決定の履歴を線形に保つため。
