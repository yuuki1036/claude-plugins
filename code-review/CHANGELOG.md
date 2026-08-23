# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [2.84.1] - 2026-08-23

v2.84.0 の CI（変異スモーク `--strict`）が拾った生存 1 件の解消。**ローカルの回帰テストは全件緑だった** — 変異テストでしか見えない穴だった。

### Added

- **`waves_expected` の境界テスト 2 件**（explorer 0 体 / verify 0 体）。既存テストが全部 explorer 1 体・verify 1 体だったため、`_agents_n("explorer") > 0` を `>= 0` に広げる変異（＝**常に 1 wave 多く見込む**）が生存していた。広げると `[5,1]` 型（explorer 無し）の分割が**丸ごと見えなくなる** — 見込み過多は偽陽性ではなく**検出漏れ**として出るので、鳴らないこと自体が正常と区別できない
- `verify` 側の境界も独立に表明した（CI は `--max 5` のサンプリングなので今回の抽選には入っていないが、nightly の深い方で拾われる位置にある）

## [2.84.0] - 2026-08-23

一括発行違反（`orchestration-guide.md ## 0`）の**全層検出**。既存の 2 経路がどちらも一部しか見ておらず、**実測で fleet span の 20%（9 分）を失った回が「正常」と判定されていた**。

### Added

- **`dispatch.waves_expected`（publish が注入）と `measurement_gaps` の `wave-split`**
  - 既存の検出は ①`dispatch.verdict == "serial"`（**単独 wave 3 連続**を要求）②`agents.explorer_waves`（**explorer 層しか数えない**）の 2 つで、**「reviewer 5 体のうち 1 体だけ先に出した」型を両方とも取り逃す**。実測 `2026-08-22T04:09` の回は `bug-detection` だけが 9 分早く単独発行され、`wave_sizes` が `[1,1,5,3]`・`max_solo_run` 2 で `layered`（正常）判定だった。一括なら `max(505s, 822s)` で済むところを `505 + 36 + 822` 払っている
  - 期待本数は `(explorer が 1 体以上 ? 1 : 0) + 1 + (verify が 1 体以上 ? 1 : 0) + (round2 が 1 体以上 ? 2 : 0)`。**窓を切った実サンプル 6 件で 6/6 正解・偽陽性 0**（既知の違反 2 件を両方検出）
  - **層の同定はしない。** `subagents/*.meta.json` の `description` で層を分類する案を実データで検証して**棄却した** — 書式が LLM の自由文で安定せず（実測 25 セッションで大半が分類不能。`reviewer bug-detection` / `Review CLAUDE.md compliance` / `R1 bug-detection` / `doc 整合性レビュー（R1）` が混在）、分類器は**静かに何も検出しない**方向に倒れる。さらに窓を切らないと別レビューの agent を数え、Round 2 の正当な分割も違反にする（実測で両方の偽陽性を確認）
  - **`agents-mismatch` の回では立てない**（期待は `agents` の自己申告から作るので、申告が壊れた回に重ねると原因の違う 2 つの信号が混ざる）
  - **まだ WARN は出さない。** skeptic の fallback 起動（`triage-dynamic-gates.md ## 8.5` / 真に単独 wave になる唯一の正規経路）を見込むと実測済みの違反を両方取り逃すため見込んでおらず、**その偽陽性がどれだけ混ざるかを測るのが本 gap の目的**（`agents-mismatch` と同じ「まず発生率を測る」段階）
- **回帰テスト 6 件**（`WaveSplitTest`）。検出 / 正準形で鳴らない（偽陽性ガード）/ Round 2 の見込み / `agents-mismatch` での抑止 / `waves_expected` が常に載る / fail-fast しない

## [2.83.1] - 2026-08-23

nightly の変異テストが検出した生存 8 件（GitHub issue #164 / #161 の打点補完コード）を解消した。**生存 = その挙動を検証していない**。

### Added

- **`durations` の marker-wins を `t1` にも表明した**。`we` / `w` しか見ていなかったため、`t1` 行の `&&` を `||` に緩める変異（＝**実打点を補完値で上書きする**）が生存していた。補完は欠測の穴埋めであって上書きではない、という契約の当のところ
- **値を取るフラグの引数ガードを 4 つすべてに広げた**（`--pr` / `--derived-t1` / `--derived-explore` / `--derived-wave`）。publish は `--derived-*` を 3 つ並べて渡すので、**単独で渡す形が結合テストから一度も通らない**。`--derived-t1` だけ表明していたため他 2 つの境界変異が生存していた
- **`late-publish` の境界（ちょうど 10 分）を両側で表明した**。既存テストは 30 分と 0 分だけで、境界を 1 つ狭める変異が生存していた。片側にずれると**契約が壊れた回を正常として集計に入れる**

### Changed

- **等価変異 5 件に `# mutation-ok:` を理由つきで置いた**（`publish-review-event.sh`）。いずれも上流の不変条件から到達しない経路: `wave_clock` は `None` か非空リストしか来ない（`measure-tokens.sh` は `waves_by_msg` が空なら `None` を出す）/ `ok()` の `v is None` は呼び出し側が同じ式を代入するので出力が変わらない / `ok()` の `t0` 下限は窓を `since-t0` に限定したので到達しない（既存マーカーが `if` 行にしか無く `return` 行が素通りしていた）/ explorer wave 突合の `break` 2 つは `n` が 1 以上で acc が狭義単調増加するため

## [2.83.0] - 2026-08-23

publish 済みイベントに transcript から計測を後付けする CLI を追加した。**サンプル待ちで止まっていた計測 issue の母数を、新しくレビューを回さずに増やす**ための道具（#153 は n=1 から 6、#156 は n=2 から 7 になった）。

### Added

- **`scripts/review-backfill.sh`** — `review:completed` の窓（`[t0, t2]`）を payload の `duration_*` から逆算し、生き残っている `subagents/agent-*.jsonl` に対して `measure-tokens.sh` を回して `dispatch` / `tokens` を後付けする。読むだけで **publish はしない**
  - **窓が汚れる回は捨てる**（誤値より欠測）: ①区間欠測で窓を作れない ②窓の外にも同セッションの agent がある（`--since` に上限が無いので別レビューが `wave_clock` の末尾に入る。実測で 1 セッションに 3 レビューが入った回を踏んだ）③`max_inter_wave_sec` が 2 時間超（窓が別レビューを内包。実測 27 時間）。**除外は理由ごとに件数を出す**
  - **`agents` の突合式は `publish-review-event.sh` の `declared` と同一**（allow-list の 5 キー + `recall_skeptic` / `meta_reviewer` の `fired`）。実装時に deny-list で書いて、契約外の `skeptic` キーを足し `-1` の偽の食い違いを出した。#154 が検知したい信号と同じ形のノイズなので回帰テストで固定した
  - `orchestration-measurement.md ## 18.1` に「後付け値を publish しない / retro に混ぜない」を含む運用を書いた
- **回帰テスト 7 件**（`ReviewBackfillTest`）。除外の 3 経路・突合式・ログ不在の fail-fast・0 件時の JSON 契約・0 件を「計測が壊れている」と読ませない文言

### Changed

- **transcript の project ディレクトリ導出を `lib/review-paths.sh` の `review_project_dirs` に集約**した。`measure-tokens.sh` にインラインで書かれていた式を切り出し、`review-backfill.sh` と共有する（複製を作らない / CLAUDE.md）。挙動は従来と同じ（cwd 側 + `--git-common-dir` の親の 2 候補）

## [2.82.3] - 2026-08-22

#153 Phase 2 の判定。**末尾 1 体 wave は現状維持**とし、実測ベースライン（`orchestration-measurement.md ## 15`）に fleet の内訳を追記した。

### Changed

- **`max_inter_wave_sec` を「次の wave の費用」と読む誤りを doc で名指しで禁じた**。この値は **wave N 起動 → wave N+1 起動**なので、**wave N+1 がまだ起動していない区間**を含む。#153 起票時はここから「反証 1 体を起動するために fleet の 56-70% を払っている」と読んでいたが、`wave_clock` で末尾 wave の `end - start` を直接測ると **中央値 14.8%（11.6〜25.5% / n=3）**。実測 `[5,1]` の回で `max_inter_wave_sec` は span の 74.5% を占める一方、末尾 1 体そのものは 25.5% で、残りは wave 1 の reviewer 5 体が回っていた時間だった。**指標の読み違えで打ち手の期待値を 4 倍に見積もる**経路なので、正本側に禁止として置いた
- **`## 15` の「explorer 以降の wave 間隔」を内訳 2 行に割った**（更新の条件として本節自身が予告していたもの）。前 wave の agent 実行が **中央値 89.0%（78.1〜93.5% / n=6）**、orchestrator の統合作業が **中央値 11.0%**
- **fleet 全体の分解を追記**。orchestrator の待ちは **中央値 8.4%・最大 14.3%（n=6）**で、**fleet の約 92% は agent が回っている時間**。往復削減で縮む上限がここだと明示した。壁時計の打ち手は wave の本数ではなく 1 体あたりの実行時間（#156）にあることを行き先として書いた
- `triage-guide.md ## 7` の「内訳の分離は GitHub issue #153」を、分離済みの参照に更新した
- **`design-notes/pending-optimizations.md ## 11` に「末尾 1 体 wave の廃止 — 採らないで決着」を追加**。末尾 1 体は既定 high では**反証レイヤー本体**（`## 9` の meta 由来追加バッチではない — 既定 high では meta が走らない）で、#150 の実測では報告 10 件中 3 件を降格している。14.8% と引き換えに落とすものが大きい。`## 4`（explorer wave 廃止）の「wave を削るなら見るのは reviewer → 反証 の間」も、決着済みの参照に更新した

### Notes

- 上記の実測のうち **fleet 分解と末尾 wave 占有率の 2 行は後付け値**。`wave_clock` は payload に載せない契約（`## 16`）なので、生存している `subagents/agent-*.jsonl` に `[t0, t2]` の窓をかけて事後に算出した。`review-retro.sh` には出ない点を表に明記してある
- 母集団は **self-review / high / medium に偏っている**（6/6）。review 側の wave 構成では内訳が変わりうるので、次の更新条件を「review 側 5 件」に置いた

## [2.82.2] - 2026-08-22

### Fixed

- **`ok()` の docstring が散文に比較演算子を書いており、変異テストが等価変異として拾って CI（`--strict`）を落としていた**。変異ツールはコメント行（`#` 始まり）を除外するが、**`.sh` 内の python ヒアドキュメントの docstring** は `#` で始まらないので除外の対象外。説明文中の `v >= max(t0, lo)` がそのまま演算子として書き換えられ、挙動は変わらないので**必ず生存する**。「以上」「以下」と日本語に置き換えた（`<` / `>` 単体は変異対象外なので影響を受けるのは 2 演算子だけ）。同じ罠を次に踏まないよう root CLAUDE.md の Gotchas にも追記した

## [2.82.1] - 2026-08-22

v2.82.0（#161）のセルフレビューで検出した欠陥の修正。反証レイヤーで 15 件を検証し **confirmed 7 / severity-inflated 6 / refuted 2**。

### Fixed

- **`t0` 打点が欠測した回に、無関係な agent の時刻で `t1` を補完して誤値を publish していた**。`t0` が無いと `measure-tokens.sh` は `--since` なし＝**セッション全体**を窓にするため `wave_clock` に同一セッションの別作業の agent が混ざる。しかも `ok()` は `t0` 欠測だと下限チェックを飛ばすので、**何時間も前の起動時刻**がそのまま `t1` になっていた（実測: 本来 10 分の回が `duration_fleet_min` 120 分）。**#161 が守ろうとした「縮退先は欠測であって誤値ではない」を #161 自身が破っていた** — しかも `derived_markers` に載るので retro では最も信頼度が高いラベル付きの過大値として集計に入る。補完の実行条件を `window == "since-t0"` に限定した（`wave_clock` が「この回の agent だけ」であることの担保は窓しか無い）
- **`payload.agents` が truthy な非 dict のとき未捕捉 `AttributeError` で補完機構が丸ごと no-op になっていた**。`or {}` は falsy しか吸収せず、`.get()` が `try` の**外**にあった。同ファイルの payload 構築側は元から `isinstance` で正規化しており、新規ブロックだけが不変条件を落としていた。`agents` は SKILL テンプレートを LLM が埋めるフィールドなので、**payload が荒れている回＝打点も落ちやすい回**で優先的に落ちる経路だった
- **explorer wave が最終 wave より後に終わる回で `duration_explore_min` と `duration_synthesis_min` が重なっていた**。`wave_clock` は **start でソート**されているので `clock[-1]` は「最後に起動した wave」であって「最後に終わった wave」とは限らない。`we > w` なら explorer 側を欠測に倒す
- **補完の異常終了が「補完対象が無かった」と区別できなかった**。両方が `derived_markers: []` に潰れ、retro が機構の失敗を「補完条件を満たさなかった回」として数えていた。`measurement_gaps` に `derived` を立てる（同型の状況で `dispatch` / `diff-digest` / `tokens` が既に取っている扱いに揃えた）

### Added

- **回帰テスト 13 件**。v2.82.0 のセルフレビューは**新設したガードの変異 8 件が 8 件とも生存**することを実測で示していた（`span()` の負クランプ / 非数値スクラブ / `ok()` の下限 2 本 / explorer-wave の marker-wins・`end` 完全性・bool ガード / retro の補完内訳）。**肯定系（補完が効く経路）は守られていたのに、`## 14` の原則を実際に守っている行だけが全部テストの射程外**という非対称だった
  - `--derived-*` は usage に載った公開 CLI なので、`durations` の **stdout を直接見る**テストを足した（従来は returncode しか見ていなかった）
  - retro のテストは `measurement_gaps` と `derived_markers` に**同じ識別子**を入れていたため、`assertIn(..., out)` が既存の「欠測内訳」行だけで満たされ、補完内訳を丸ごと殺しても緑だった。fixture を非対称にし `derived_line()` で行を絞る
  - `ok()` の `t0` 下限は窓の限定で publish 経路から到達しなくなったので `# mutation-ok:` で明示的に外した（防御としては残す）
  - **等価変異を 2 件踏んで fixture を組み直した**: ①explorer 群の `end` 完全性は explorer が **2 wave に割れた形**でないと `wave_clock` 側が既に `end=None` に倒しており、ガードを外しても結果が変わらない ②bool ガードは `True == 1` なので**先頭 wave が 1 体**でないと累計が一致しない。どちらも「テストは書いたが検証していない」状態だった
  - `durations` 側の marker-wins（publish とは独立した二段目）は結合テストから到達しないので、**CLI を直接叩く**テストで表明した
  - **修正した 12 経路すべてで「実装を壊すとテストが落ちる」ことを実測で確認**した

### Changed

- **`timeline()` を `ScriptTestBase` へ移した**。計測ファイルの書式を組み立てる helper が 2 つ（`DerivedMarkerTest.timeline()` / `LatePublishTest._stale_timing()`）になっており、マーカー行書式が変わると直す箇所が 2 つになる。後者を前者の薄いラッパにした
- **doc の陳腐化 4 件**（v2.82.0 が既存記述を偽にしたもの）: `## 13.1` のサブコマンド列挙に `epochs`（8 → 9）/ `## 14` の `duration_synthesis_min` 行と publish 算出行に補完の但し書き / `## 14` の表の `explorer-wave` に埋めない条件 2 つ / **`## 16` の `measurement_gaps` 定義**（「`duration_*` が `-1` になった理由」→「打点規約が守られたか」。直下の `derived_markers` 行と正面から矛盾していた。**SSoT pin を打ち直した＝節を再確認したはずなのに残した**）
- **コメントが実装より強い保証を謳っていた 3 件**を実装に合わせた: `ok()` の docstring（`t0 <= lo` は未検査 / 欠測側は制約なし）/ `epochs` の存在理由（`we <= w` は検算していない）/ 実測値と射程解釈の二重記載を `publish-review-event.sh` 側を正本に一本化（数字を 2 箇所に書くと更新漏れで食い違う）

## [2.82.0] - 2026-08-22

### Added

- **打点が落ちた区間を agent transcript の実測時刻で埋める**（GitHub issue #161）。区間打点（`review-timing.sh mark`）はオーケストレーターの記憶に依存しており、実測で **v2.62.0 以降の 10 件中 5 件が 1 つ以上落としていた**（`t1` 1 / `wave` 2 / `explorer-wave` 2 / `t2` 1）。結果として `duration_explore_min` が 4/10・`duration_synthesis_min` が 3/10 で欠測し、**#156 が基準値の裏付けに使った回と #153 が初の `schema 3` サンプルにした回が、どちらも打点漏れで区間内訳を欠いていた** ——打ち手を決めるための 2 サンプルが、計測基盤の穴で削られていた
  - **#135 / `pending-optimizations ## 8` が残していた側**。あの項の動機は「①一括発行違反が検知できない ②打点漏れで区間が欠測する」の 2 つで、①は #142 が `dispatch` を transcript から機械計測して解決済み。**②は手つかずで、Agent hook 案の「発火するか確認できていない」というブロッカーの後ろに残っていた**。しかし #142 / #153 が読んでいる `subagents/agent-*.jsonl` には、hook で取ろうとしていた時刻が既に入っている——**新規 hook を足さずに既存の事後計測経路で埋まる**
  - `measure-tokens.sh --json` が `wave_clock`（wave ごとの `{n, start, end}`）を返し、`publish-review-event.sh` が `review-timing.sh durations --derived-t1 / --derived-explore / --derived-wave` へ渡す。**payload には絶対時刻を載せない**
  - 補完するのは `t1`（最初の agent 起動）/ `wave`（**最終 wave** の終了）/ `explorer-wave`（先頭から累積して `agents.explorer` に**ちょうど一致**する wave 群の終了）の 3 つ。**`t2` / `t0` は補完しない** — メイン文脈のイベントで agent transcript に現れず、publish 時刻からの逆算は `orchestration-measurement.md ## 14` が禁じている当のもの
  - **`## 14` の「逆算による補完はしない」は撤回していない**。あの禁止の射程は *publish 時刻からの推定*（＝誤値）で、ここで使うのは実測時刻。両者を分ける線は「**その時刻が実際に観測されたか**」であって「補完したかどうか」ではない、と doc 側で明示した
  - **explorer wave の同定は突合であって推定ではない**。体数の累計が一致しない回（explorer を複数 wave に割った回・Round 2 の追加 explorer が混ざった回）は埋めない。「先頭 wave = explorer」と決め打つと、区間が別物に化ける
  - **縮退の向き**: `dispatch` が判定できなかった回（`unresolved` あり）は一切埋めない / 最終 wave の体が 1 つでも終了時刻を持たなければ埋めない（#153 と同じ）/ `t0 <= 補完値 <= t2` を満たさない値は採らない。`durations` 側にも**負の区間を `-1` に倒す**二段目を入れた（打点だけなら時刻は単調増加なので起こりえず、負が出るのは補完値の矛盾か時計のずれ）
- **`derived_markers` を payload に追加**（識別子の配列 / 常に載る）。**`measurement_gaps` は消さない** — 打点漏れ率そのものが観測対象（#123 B）で、補完で消すと「打点規約が守られているか」が見えなくなる。2 つを分けることで**「区間の欠測率」と「打点漏れ率」が分離して読める**
- **回帰テスト 11 件を追加**（補完の 4 契約 + retro の待ち行 3 状態 + 引数ガード）。変異テストのスモーク（`--max 6`）で生存 1 件を検出して潰した — publish は `--derived-t1 / --derived-explore / --derived-wave` を並べて渡すため、**単独で渡す形が結合テストから一度も通らず**、境界を 1 つ狭める変異（`$# -ge 2` → `-gt 2`）が生き残っていた
- **`review-retro.sh` の計測の健全性に補完済みの内訳を追加**。待ち行は 3 状態を出し分ける（①フィールドを持つ回が 0 = 旧版のみ ②持っているが 1 件も補完していない ③補完あり）。②を「判定対象なし」に潰すと**補完機構が入っているのに一度も効いていない**を見逃す（#153 / #156 で同型の縮退を踏んでいる）

### Changed

- **`publish-review-event.sh` の計測フィールド収集の順序**を「トークン計測 → 補完値の算出 → `durations` → late-publish 判定 → 窓の命名」に入れ替えた。`durations` が `measure-tokens.sh` の結果に依存するようになったため。`TOKENS_WINDOW` の `since-t0-late` への書き換えだけが late-publish 判定に依存するので、そこを最後に回して循環を解いた
- **`measurement_gaps` の WARN 文言**を「打点由来は対応する `duration_*` が -1」から「実測時刻で埋まらなければ -1」に修正し、補完できた識別子を同じ行に出すようにした（補完後は前者が成り立たない）

## [2.81.0] - 2026-08-21

### Added

- **`review-retro.sh` に複数ログを合算する `--logs` を追加**（GitHub issue #160）。**判断に足りるサンプル数はリポジトリを合算しないと出ない**のに、ログ探索は自リポジトリ（`--git-common-dir` の親 + main root）に固定されていた。実測でマシン全体 91 件のうち 70 件が単一リポジトリに偏っており、**シグナルのサンプル数下限**（skeptic `fired >= 15` / meta `fired >= 10`）に他のリポジトリが単独で届くことは構造的に無い。結果、直近の計測 issue（#150 / #153 / #154 / #156）は**すべて手で `events.jsonl` を連結してから**書かれていた ——「LLM に毎回 jq を組ませない」ためにスクリプト化したのに、合算するときだけ手で組み直していた
  - **探索はしない**（`--all-repos` は探索範囲の規約を決める別の判断）。渡したファイルだけを見るので、どの母集団で判断したかが履歴に残る。`--logs a b c` は後続の非フラグ引数をすべて取るので `--logs ~/Projects/*/.claude/events.jsonl` とシェルの glob を直接渡せる
  - **読めないパスは exit 2**（判定不能）。明示指定の誤りを「サンプルが少ない」に化けさせない
  - **重複は 2 段で落とす**: 同一ファイルの重複指定（glob の重なり）はパスの実体で畳み、同一イベントが別ファイルにある場合（worktree へコピーされた `events.jsonl`。実測で 3 本が同じ 70 件を持っていた）は `ts` + `plugin` + payload 全体で落とす。前者を畳まないと**ログ別件数の合計が n を超える**表示になる
- **どのログから何件採ったかを必ず出力する**（`--logs` の有無を問わず。text と `--json` の両方）。「⚠️ が出たときだけ行動する」契約は母集団が言えて初めて成立するが、件数だけでは母集団が再現できなかった（#150 の「83 件」と #160 の「91 件」がどのファイル由来か不明）。0 件のログも列挙する（「見ていない」と「見たが 0 件」は別）

## [2.80.0] - 2026-08-21

### Added

- **自己申告の `agents` と機械計測の `dispatch.agents` の食い違いを publish が検知する**（GitHub issue #154）。実測で **review 側だけ内訳合計が 3 割足りない**（dispatch 28 対 内訳 19 / 27 対 20。self-review は 6/6 件で完全一致）。`agents` は**体数中央値・体数 vs fleet の相関・`sub_output_k` との相関すべての分母**なので、片方の skill で取りこぼすと skill 間の比較が成立せず、#150 の非対称（`severity_inflated` が review 84-90% / self-review 50%）を「体数の差」で説明できるかどうかも検証できない
  - 突合は `explorer + reviewer + specialist + round2 + verify` に**動的層の `fired` ぶんを足して**から行う（`agents` は meta / skeptic を含まない契約のため。補正しないと self-review まで恒常的にずれ、review 固有という信号が埋もれる）。`verify_findings` / `explorer_waves` は体数ではないので足さない
  - 食い違ったら `measurement_gaps` に **`agents-mismatch`** を積む。**fail-fast にしない** — 差の存在自体が観測対象で、publish を止めると計測が丸ごと消える（`inflated_axes` の合計不一致を落とすのとは非対称）。**まず発生率を測る**段で、原因の特定と `agents` の機械計測化は次段（#154 の 2 / 3）

## [2.79.0] - 2026-08-21

### Added

- **動的層の `skip_reason` を publish 時に語彙検証する**（`missing_coverage` / issue #132 と同型）。正本（`orchestration-measurement.md ## 16`）は層ごとに語彙を決めているのに検証が無く、実測で `no-surface` が `surface-none` / `surface-not-detected` に割れていた（全リポジトリ 91 件中 3 件。**うち 1 件は #132 の対策より後**）。retro の skip 理由集計は `group_by` なので、綴りが割れると「どのゲートで落ちているか」がその件数ぶん消え、しかも**別バケツとして出るため集計上は欠測に見えない**。語彙外は publish せず `FATAL` で落とす（黙って正規化しない — 寄せ先を推測すると別の綴り割れを作る）。層をまたいだ流用（skeptic に `no-high-severity` 等）も弾く
- **`measurement_gaps` に `payload:<field>.skip_reason` を追加**。`fired=false` なのに理由が無い回（実測 8/49 件）は retro で `unknown` に化けるだけで、「書き忘れ」と「語彙に無い」を区別できなかった。**語彙外と違い寄せ先を推測できない**ので、落とさず可視化する側に置く（`payload:<field>.fired` と同じ流儀）

## [2.78.2] - 2026-08-21

### Changed

- **wave 単価の目安を実測に合わせ、数値の正本を `orchestration-measurement.md ## 15`（新設）に一本化した**（GitHub issue #155）。Phase 0 が提示していた「wave あたり 6〜16 min」は実測（`dispatch.max_inter_wave_sec` n=5 で 14〜34 分）と 2 倍以上ずれていた。**単一の数字では表せない** — explorer wave だけが 6 分（`duration_explore_min` n=29）で安く、外しているのは reviewer → 反証 の間なので、`explorer 約 6 min / 以降 14〜34 min` と層で分けて出す。`triage-guide.md ## 5 / ## 5.1` と `triage-dynamic-gates.md ## 9` / `pending-optimizations ## 7` は提示・参照に留め、数値を二重に持たない
- **`pending-optimizations ## 4`（explorer wave の廃止）を「採らない」で決着させた**（同 #155）。保留条件「`duration_explore_min` が貯まって wave 単価が分かってから判断する」は n=29 で満たされ、**explorer wave は直列 wave の中で最も安い**（6 分 vs 14〜34 分）ことが分かった。廃止で減るのは 6 分だけで reviewer の探索量は増えるため、トレードオフの向きが「採らない」に確定した。再検討の条件を明記してある

## [2.78.1] - 2026-08-21

### Fixed

- **`per_agent_buckets` のガードが片側だけ `null` の payload で落ちうる経路を回帰テストで塞いだ**（nightly 変異テストが検出 / GitHub issue #157）。`sub_cache_read_k` だけ `null`（＝ `measure-tokens.sh` が cache_read を返せなかった回）で `cr is None` より先に `cr < 0` を評価すると `TypeError` になり、retro は `set -uo pipefail`（`-e` なし）+ 末尾 `exit 0` なので **rc 0 のまま出力が途中で切れる**。
- **v2.78.0 が dispatch 側の同型（`test_wave_gap_survives_a_half_missing_payload`）だけを塞いでいた**。同じ失敗モードが同じ版の中に 2 箇所あり、片方しか見ていなかった。ローカルの変異テストは直前コミットの変更行しか対象にしないため出ず、nightly（`--base` が 2 日前・39 変異）で初めて生存した。**「同型を 1 つ直したら、同じ形が他にないか grep する」** を手順に足すべきシグナル

## [2.78.0] - 2026-08-20

**セルフレビュー（`b4cbaac..HEAD`）で v2.76.0 / v2.77.0 の集計出力に欠陥 7 件**。反証レイヤーが 10 件中 7 confirmed / 3 降格。**足した計測自身が誤った打ち手を指す**型が 4 件で、うち 2 件は回帰テストが構造的に検出できない位置にあった。

### Fixed

- **`agent 側 N%` を回ごとの比の中央値にした**。旧実装は総和プール `sum(a)/sum(a+i)` で、**同じ行に並ぶ中央値と逆の結論を出す**（実測: `(10,90)(11,89)(12,88)(13,87)(3000,200)` で中央値は idle 支配なのにプールドは agent 85%）。外れ値 1 件で打ち手が反転する状態で、#153 が防ごうとした誤判断を集計側で再生産していた。隣の `per_wave`（体数/wave）と同じ流儀に揃えた
- **打ち手の提示に下限 `WAVE_GAP_MIN_N = 5` を掛けた**。旧実装は n=1 から `>= 60% なら末尾 wave の去就` を印字し、**その挙動を自分の回帰テストが固定していた**。同ファイルの他の打ち手行はすべて下限を持つ（`R_MIN_N` / `VERDICT_MIN` / `GAP_MIN_N` / skeptic `>= 15` / meta `>= 10`）。数値そのものは n=1 から出す（観測の可視化）が、支配側の判定は下限から。40-60% は「支配側なし」と明示する
- **「サンプル待ち」の原因断定をやめ、除外理由を件数で出し分けた**。else に落ちる経路は ①該当 schema 0 件 ②終了時刻の欠測 ③`batched` でギャップ無し の 3 つで、**③は一括発行が守られた回の常態**（1 wave ⇒ `inter` 空 ⇒ 必ず `(0,0)`）。目標状態に近づくほど「schema 3 待ち」の誤メッセージが恒久化していた。トークン側も同様（版が古い / `sub_agents` が 0・欠測で除算不可）
- **`per_agent_buckets` に版マーカーゲート（`TOK_CACHE_READ_MIN_SCHEMA = 2`）を足した**。フィールド在否での代用は今は等価だが、冒頭の層別の原則（版マーカーで切る）から外れており、待ち行が名乗る `schema 2` をコードが強制していなかった
- **`## 17` の `cache_read` 行が「前後比較の指標には使わない」のまま残っていた**。v2.76.0 が `## 16` に足した記述（重み付けコスト最大 / 基準値 5,039k と比べる）と正面衝突し、`## 18` の戻り先マップが読者をその行へ送る導線になっていた。#156 の目的そのものを打ち消す位置
- **欠測条件の記述が実装より広かった**。「取れない体が 1 つでも」→ 実装は**最大ギャップ直前の wave の体だけ**を見る（最終 wave の終了時刻は一度も参照されない）。`## 16` は SSoT pin された正本なので、doc に合わせて実装を狭める逆修正の温床だった
- **`## 18` の対応表に 3 行追加**（1 体あたり cache_read / 発行パターン / 最大ギャップの内訳）。「発行パターン」は v2.70.0 からの既存の穴
- **v2.76.0 / v2.77.0 が直した doc drift を版に記録していなかった**（`tokens` は review 限定、という v2.70.0 で撤回済みの記述の残存 / #143）

### Added

- 回帰テスト 9 本。**2 件は「変異させても全テストが通る」ことを実測してから書いた**:
  - `test_wave_gap_picks_the_largest_gap_not_the_first` — 既存 fixture が全部 2 wave（ギャップ 1 本）で `argmax` が恒等になっており、`i = 0` に変異させても全件 green だった。explorer → reviewer → 反証 は設計上 3 wave 以上なので主経路
  - `test_wave_gap_excludes_batched_zero_gap_without_dying` — `(a + i) > 0` を守るテストが無く、`>` → `>=` の変異が生存。回帰すると `ZeroDivisionError` だが `set -uo pipefail`（`-e` なし）+ 末尾 `exit 0` で **rc 0 のまま stdout が途中で切れる**。`signals()` の liveness ガード付き
  - 他 7 本: プールド比への逆戻り検出 / 下限未満で打ち手を出さない / 待ち行の理由出し分け（dispatch・tokens 両側）/ 版ゲート / 欠測とギャップ無しのカウンタが独立に効くこと / 片側だけ `null` の payload で落ちないこと / 支配側の判定が 60%・40% ちょうどを含むこと
- **除外理由のカウンタ 3 本と境界 2 つは、初回の変異テストで 5 件生存した**箇所。とくに「片側だけ `null`」は `a is None` を `a < 0` より先に評価する短絡が守っており、壊れると `TypeError` → **rc 0 のまま出力が途中で切れる**（本版が直した #3 と同じ縮退）。修正した欠陥と同じ失敗モードが修正コード自身に潜んでいた
- コメント推敲 5 件（`inf` は起きない・「末尾を読めば」が `max` 実装と食い違う・trip wire の失敗メッセージが版マーカー欠落を指したまま 等）

## [2.77.0] - 2026-08-20

**wave 間ギャップの内訳が分離されていなかった**（GitHub issue #153）。`dispatch.max_inter_wave_sec` は「wave N 起動 → wave N+1 起動」なので、**agent が回っていた時間**と**オーケストレーターの統合・dedup・scoring 時間**が合算されている。実測（n=5）では `wave_sizes=[6,1]` / `[4,1]` の回で**反証 1 体を起動するために fleet の 56-70%**（17.5 分 / 14.2 分）を払っており、支配側が分からないまま末尾 1 体 wave を消すと「wave を消したのに fleet が縮まない」を踏む。

### Added

- **`dispatch.inter_wave_agent_sec` / `inter_wave_idle_sec`**（`schema` を 3 へ）。**`max_inter_wave_sec` が報告している当のギャップ**の内訳で、**和は `max_inter_wave_sec` に一致する**（idle は引き算で出す — 独立に丸めると 1 秒ずれて「3 つ目のバケツがある」と誤読される）。取得元は #142 と同じ `subagents/agent-*.jsonl` で、**先頭を読めば起動時刻・末尾を読めば終了時刻**という対称性を使う（事後計測なので暴発しない）
- **終了時刻は timestamp 付き行が 2 行以上あるときだけ採る**。1 行しか無い回は `sub_last == sub_first` になり「起動と同時に終わった」と区別がつかない。そのまま使うと agent 実行 0 秒 → idle が総取りになり、**「オーケストレーターが遅い」という誤った打ち手**を選ばせる（#153 が縮退の向きとして禁じているのがこれ）。**最大ギャップ直前の wave に属する体**で 1 つでも終了時刻が取れなければ両方 -1（欠測）。他 wave の欠測は内訳を潰さない（wave 構成は起動時刻だけで決まるため）
- **`review-retro.sh` に最大ギャップの内訳を出す**。agent 側 `>= 60%` なら打ち手は末尾 wave の去就、`<= 40%` なら往復削減、という読み方を添える。欠測は分母から外す（0 に倒すと idle 支配の誤読）。schema 2 しか無い間は待ち行
- 回帰テスト 7 本（publish の内訳・欠測・はみ出し 3 / retro の集計・欠測除外・`agent 実行 0 秒`・待ち行 4）。変異テストは 10/10 killed だが**初回は 1 件生存**し、それが `agent 実行 0 秒` の回を分母から落としても誰も気づかない穴だった （＝ idle 支配の証拠を捨てて分母が agent 支配側に偏る。本 issue が避けようとしている誤読を集計側で作ることになる）

### 意図的にやらなかったこと

**末尾 1 体 wave（反証 / meta 由来の追加反証）に手を付けていない。** #153 が Phase 2 として切っているとおり、支配側が (a) agent 実行なら wave を減らす・(b) 作業時間なら往復を削る、と打ち手が正反対になる。分離した実測が貯まる前に当てると、直ったかどうかを事後に切り分けられない。

## [2.76.0] - 2026-08-20

**トークン計測が重み付け最大の項を落としていた**（GitHub issue #156）。`tokens` payload は `output` と main の `cache_write` しか載せておらず、コスト比で 45% を占める `cache_read` が観測の外にあった（`pending-optimizations.md ## 計測の基準値`）。実測（`2026-08-18T03:17Z` の self-review・9 体・レビュー区間のみ）では **sub の `cache_read` 単独で総コストの 38%**、1 体あたり 5,749k で基準値 5,039k から下がっていない。**規模キャップ（#96）は「広さ」を切っただけで、1 体あたりの読む量には一度も手が入っていない。**

### Added

- **`tokens.main_cache_read_k` / `sub_cache_read_k` / `sub_cache_write_k`**（`schema` を 2 へ）。`measure-tokens.sh --json` は元から返しているので取得経路の追加は無く、**落としていたのは publish 側**
- **`review-retro.sh` に「1 体あたり cache_read」を effort × size_tier で層別して出す**。総量だけでは「体数が多い」と「1 体が読みすぎ」を切り分けられず、tier は担当ファイル数を・effort は 1 体あたりの探索量を決めるので層別しない中央値は両方の交絡を負う（体数 vs fleet の r を tier 内で取るのと同じ理由 / #151）。`sub_agents` が 0・欠測の回は**除算せず落とす**（0 に倒すと集計が例外で死に、1 に倒すと 1 体あたりが総量に化ける）
- schema 1 のサンプルしか無い間の待ち行（黙ると「1 体あたりは問題なかった」と読まれる / #131 と同じ型の誤読）
- 回帰テスト 4 本（publish の値 1 / retro の層別・除算ガード・待ち行 3）

### なぜ観測だけなのか

削る候補（担当ファイルの絞り込み / 探索予算 / 体数）はどれも recall とのトレードオフを持つ。`pending-optimizations.md ## 10`（`class` で機械的に絞る）は既に「採らない」で決着しており、残る材料は `## focus-signals` の根拠ファイル側だが、**シグナルが出ていないファイルを構造的に落とす**ので recall への影響測定が前提になる。層別の実測が無いまま当てると、どれが効いたのか事後に切り分けられない。

## [2.75.0] - 2026-08-20

**上流較正の効果が review 側で出ていない**（GitHub issue #150）。tier・effort・ゲートを揃えても `severity_inflated` が review 84-90%（confirmed 6-12%）/ self-review 50-51%（confirmed 25-46%）と非対称で、PR レビューが `pre_major 50 → 報告 7 件`・4 本中 3 本が報告 0 件になっていた。**本版は打ち手ではなく観測**を足す（現状 n=14 で「型が的外れ」の証拠はまだ無いので、プロンプト修正を先に当てない）。

### Added

- **`adversarial_verify.inflated_axes`** — `severity_inflated` の**型別内訳**。反証エージェントは既に `axis` を返しているので、語彙に `overstated-impact` / `miscategorized` を足して `prompts/reviewer-common.md`「降格される典型パターン」の 4 型に対応させ、型ごとに数える（`pre-existing` / `intended` → `base_derived`）。**軸が返らなかった件は `unknown`** に落とし、publish が **合計 == `severity_inflated`** を fail-fast で確かめる（型が取れなくても件数は落とさない）
- **`below_threshold_counts.demoted_types`** — reviewer が `{{SEVERITY_THRESHOLD}}` を跨いで自分で降格した分の型別内訳。**`inflated_axes` と同じ語彙**にしてあり、上流降格と下流降格を同じ軸で並べて読める。合計が `below_threshold_counts` の合計を超えると fail-fast
- **`review-retro.sh` の型別内訳を skill 別に出す**。非対称そのものが観測対象なので skill を潰して合算しない。内訳が 1 件も無い間は待ち状態を 1 行出す（黙ると「型は取れている」と読まれる / #131 と同じ型の誤読）
- 回帰テスト 13 本（publish の検証 10 / retro の出力 3）

### なぜ観測だけなのか

`design-notes/scoring-rationale.md` が用意している切り分け（「型が的外れ」か「そもそも上流で直せない」か）は、**どの降格典型で落ちたかが payload に残っていない**ため進められなかった。仮説は「review 側の reviewer に base 文脈が構造的に届いていない」（self-review は変更意図をメインコンテキストが知っているが、review は PR diff から復元するしかなく、4 型のうち `pre-existing` / `intended` の判定材料が不足する）。**`base_derived` が支配的だと出れば、打ち手はプロンプトの表現ではなく「review 側に base 側の情報を渡す」になる** — その分岐をデータで決めるための計測。

## [2.74.0] - 2026-08-20

`review-retro.sh` の ⚠️ シグナル「体数と fleet 時間の相関が高い」が **tier 交絡で常時点灯**していた（GitHub issue #151）。全 9 リポジトリ n=83 の実測。

### Changed

- **体数 vs fleet 時間の相関を `size_tier` 内で計算し、発火条件を層別後の `r` だけで判定するようにした**。`size_tier` は体数（`triage-guide.md ## 7` の体数表）と fleet 時間の**両方**を決めるので、層別しない相関は tier の効果を体数の効果として計上する。実測で層別なし **r=0.592** に対し最大サンプルの medium（n=30）は **r=0.315** まで落ちる（`7 体 → 126 分` と `12 体 → 61 分` が同じ tier に共存する）
  - 層別なしの `r` は「tier 交絡を含む参考値」として表示だけ残し、**発火条件からは外した**。CLAUDE.md の「初回実行で偽陽性が出る warning は入れない方がまし」に該当する状態だった
  - tier ごとの下限は層別なしと同じ `R_MIN_N`（10）。**緩めると単発の tier が点灯する側に倒れる**ので、割れて判定不能になる tier が増える方を選んだ
  - 相関の式（Pearson）は変えていない。**層別の単位だけ**の変更で `review-retro.sh` 内に閉じる
  - `--json` に `agents_fleet_by_tier` を追加（`agents_fleet_r` / `agents_fleet_n` は後方互換で残置）
  - **`triage-guide.md ## 7` の再監視条件（`|r| >= 0.6`）の水準は変えていない** — 層別後の値が各 tier で貯まってから判断する（内訳: `design-notes/triage-rationale.md`）

### Added

- **回帰テスト 5 本**（`test_code_review_scripts.py`）。中核は **tier 内 r=0.000 / 層別なし r=0.944** という交絡だけを取り出した fixture で、シグナルが鳴らないことを見る。黙らせすぎ防止の liveness（tier 内 r=1.0 なら鳴る）と、**境界ちょうど**の 2 本（`n == 10` は判定する側 / `|r| == 0.6` は発火する側）を含む。境界は変異テストで `>=` → `>` が生存したため追加した（`r` がちょうど 0.6 になる整数 fixture を構成してある）

## [2.73.1] - 2026-08-20

### Fixed

- **`measure-tokens.sh` の `mutation-ok` 印を変異行と同じ行へ移した**（GitHub issue #152）。印は等価変異の理由つきで書かれていたが**直前の行**に置かれており、`SKIP_MARK` は行内しか見ないため無効だった（nightly で 40 件中 1 件だけ生存 = この行）。等価性の根拠自体は変わらない — `and` を `or` にしても、存在しない `meta_path` は `open` が `OSError` を投げて同じ「引き当て失敗」経路に落ちる

## [2.73.0] - 2026-08-19

**情報収集フェーズの往復を畳んだ**（GitHub issue #147）。16 回の実測で main は 1 レビューあたり **42 往復・cache_read 15M** を使う。`cache_read` は「往復回数 × その時点の文脈量」で決まるため、体数削減も分冊も往復数には効かない。`pending-optimizations.md ## 2`（main 側のバッチ化）は v2.49.0 以前の基準値で却下していたので、実測を材料に**部分的に撤回**した。

### Changed

- **self-review の Step 1 と 1.4 を 1 つの Bash 呼び出しにまとめた**（`review-timing.sh start` / base 検出 / `triage-signals.sh` / `detect-recent-review.sh` = **3 往復 → 1**）。review も Step 2 と 2.4 を畳んだ（**2 往復 → 1**）
  - **判断基準は「間に LLM の判断が挟まるか」**であって、コマンド同士が独立かどうかではない。後段が前段の**出力を読んで決める**なら分ける、同じシェルの変数とファイルを使うだけなら畳む。`detect-recent-review.sh` は `triage-signals.sh` が書いた diff ファイルを読むので**順序の依存はある**が、間に判断は無い
  - **`set -e` を張らない**規約を明記した。base 検出の `grep` は非マッチで exit 1 を返すので、`set -e` 下では `BASE=$(... | grep ...)` を含む `||` リストがそこでシェルごと落ち、**以降の 2 本を実行せずに終わる**（CLAUDE.md Gotchas の ERR trap family）。素で書けば BASE が空のまま次行のガードが偽になり、何が起きたかが出力に残る

### 含めなかったもの

- **機械層の先行実行（self-review 1.7）**。直前の 1.4 に「中止する」＝ agent を 1 体も起動せず終える経路があり、lint / 型 / テストを前倒しすると**中止しても払い戻せない実行時間**を先に払うことになる
- **review の Step 1**。`gh pr checkout` の失敗が中止経路で、失敗したまま `triage-signals.sh` を走らせると base branch の diff を掴む
- **main のバッチ化を一般則としては今も採らない**。畳める箇所はこの 2 つで打ち止めで、残りは「前の出力を読んで次を決める」形をしている

### 効果の見積もり（過大評価に注意）

issue #147 は「main は 1 往復あたり平均 350k」から 2 往復ぶんを見積もっていたが、**`cache_read` の往復単価はセッション後半ほど高い**（文脈量に比例するため）。今回畳んだのは**セッション中で文脈が最も小さい冒頭**なので、平均単価を当てると数倍過大になる。往復数でも main 42 往復のうち 2 本（≒5%）。**「往復を減らせば効く」は正しいが、減らす場所で単価が桁で違う** — 次に測るときの前提として `pending-optimizations.md ## 2` に残した。

SKILL 本文の増分は self-review +9 行 / review +5 行（常時読み込みのコストを払う側）。


## [2.72.0] - 2026-08-19

**空振りしやすい層の実験予算を絞った**（GitHub issue #144）。16 回の実測で **sub agent が重み付きコストの 71%**（103,015k / 145,411k）を占めるが、**一律の往復上限は打てない** — agent 別に見ると高コストな体ほど高価値で（冷や読み skeptic 1,956k で CRITICAL 1 件 / test-quality 1,646k で変異実証つき 3 件）、そこを削ると recall を直接失う。削るのは**空振りしやすい層**に限る。

### Added

- **`reviewer-common.md` に「実験予算」を追加**（適用範囲: **specialist のみ**）。ここでいう実験は**対象を実際に動かして挙動を確かめる行為**（実行 / exit code の観測 / 入力を変えた再実行 / 変異注入）で、既存の「探索予算」が縛る**読む量**とは別の軸
  - **実験は 1 経路につき 1 回**。網羅的な全数実測は求めず、**代表 1 ケース + 境界 1 ケース**で足りる。2 ケースで結論が出なければ打ち切って confidence を下げる
  - 根拠: `specialist-guardrail-bypass` が exit code を **16 通り全数実測**して「骨抜き無し」と結論した回が、重み付き **1,043k で指摘 0 件**だった。断定自体には価値があるが全数実測は要らない。specialist は「断定できなくても低 confidence で報告する」層なので、**確度を買うために払うコストの見返りが最も小さい**
  - **focus reviewer は対象外**。実プロセス・変異による実証は最も価値の高い指摘を出す層で、上限を課すと recall を直接失う（独立検証レイヤーは探索予算と同じく元から対象外）
  - 打ち切ったら `## unmet_information` に `実験打ち切り: <対象>` を 1 行残す（探索予算と同じ扱い。痕跡が無いと予算経由の recall 低下を事後に検出できない）

### Changed

- **全ファイルを渡してよい観点を 3 つに閉じた**（`cross-cutting` / `pattern-consistency` / `spec-compliance`）。いずれも**ファイル間の関係そのものが観点**で、部分集合では判定が成立しない。旧版はこれを「等」で開いていたため、`## focus-signals` に根拠ファイルを持つ観点まで**既定で全件に落ちていた**（実測: `claude-md-compliance` に全変更ファイルを渡した回が重み付き 857k で指摘 1 件）
  - 絞る材料が本当に無ければ全件でよいが、その reviewer の構成テーブル `指示` 欄に `担当: 全件` と書く。**判断して全件にしたのか既定で落ちたのかを区別できないと、この規約が守られたかを観測できない**（#142 と同じ「規約はあるが観測されていない」型を作らない）

### 採らなかった案

- **`class`（core/test/doc/gen）による機械的な絞り込み**。判断が要らず決定的だが、分類が `\.md$|(^|/)docs/` を doc とするため**プラグインリポジトリでは成果物が丸ごと doc に落ち**、`claude-md-compliance` の担当が空集合になる。`class` は `size_tier` を決めるための分類であって「誰が読むべきか」の分類ではない — 転用すると md が本体のリポジトリで後者だけが壊れる。→ `design-notes/pending-optimizations.md` `## 10`

プロンプト・ガイドのみの変更（スクリプト変更なし）。


## [2.71.0] - 2026-08-19

**検出 → 報告の歩留まりを「本文を書いてから捨てた」と「件数だけ返した」に分離した**（GitHub issue #146）。実測で検出 342 → 報告 91（26.6%）だったが、消えた 251 件が **(a) reviewer が本文を書いてから捨てられた**（＝出力トークンの純損失）のか **(b) `## below-threshold` で件数だけ返した**（＝#117 で既に節約できている）のか、集計から切り分けられなかった。`pre_adjust_counts` が両方を合算しているためで、この状態では**閾値注入が効いているかどうかを判定できない**。

### Added

- **payload に `below_threshold_counts` を追加**（`{blocker, critical, major, minor}` + `schema`）。`pre_adjust_counts` に足し込んだ `## below-threshold` ぶん**だけ**を同じ severity バケツで再掲する。`pre_adjust - below_threshold` が「reviewer が本文を書いて列挙した指摘」になる
  - **`pre_adjust_counts` は合算のまま据え置く**（schema 3 にしない）。列挙分だけに変えると既存 12 サンプルとの比較可能性が切れ、下流の jq も全部書き換えになる。合算 + 再掲なら**過去データはそのまま読める**
  - 版マーカー `schema: 1` は `SCHEMA_MARKERS` で**スクリプトが注入**する（手書きさせない / issue #125）。層のオブジェクトが落ちた回は `measurement_gaps` に `payload:below_threshold_counts` が立つ
- **`review-retro.sh` に「検出 → 報告の内訳」**を追加。`below_threshold_counts` を**持つ回だけ**で集計する（持たない回を混ぜると `pre` の母数だけ増えて (a) が過大に出る）。サンプルが 0 件の間は**歩留まりだけ出して黙らず**「分離にはサンプル待ち」と明示する（黙ると分離できていると読める / #131 と同じ型）

### Fixed

- **`below_threshold_counts` が `pre_adjust_counts` を超えたら publish を fail-fast する**。再掲が元を超えるのは定義上ありえず、pre 側への足し忘れか below 側の二重計上のどちらか。**分離がこのフィールドの唯一の用途**なので、汚染を通すと足した意味がそのまま消える（`missing_coverage` / `findings_class` と同じ位置・流儀）
  - 0 件でもキーを省かせない（「閾値未満が無かった」と「数えなかった」を 0 に潰さないため）
  - `pre_adjust_counts` が揃っていない回は突合をスキップする（契約の範囲外まで publish を止めない）

### Changed

- 両 SKILL のスコアリング手順 6 / `scoring-guide.md` / `orchestration-guide.md` に再掲の規約を追記し、`orchestration-measurement.md ## 16`（正本）に切り分けの式と 3 つの落とし穴を記録した — ①`pre_adjust_counts` を列挙分だけに変えない ②`below_threshold` は非 dedup の生合計なので差し引いた値と粒度が違う ③「本文を書いてから捨てた」は**負になりうる**（手順 1 の後に走る `recall_skeptic` / `meta_reviewer` が足すため）ので丸めない

テスト +13 件（publish 側の検証 9 / retro 側の集計 4）。


## [2.70.1] - 2026-08-19

**発行パターンの判定単位を wave に是正した**（GitHub issue #149）。v2.70.0 で入れた `dispatch` は、**規約を完全に守っていても 2 層以上のレビューが `serial` に落ちる**欠陥を持っていた。

### Fixed
- **`dispatch` の判定を wave 単位にした**（#149）。旧版は agent の起動時刻をフラットに並べて 120 秒閾値を当てていたため、**wave 間ギャップ（explorer → reviewer → 反証 という設計上正当な逐次実行。実測ベースライン 6〜9 分）を違反として数えていた**。実測でも v2.70.0 以降の 4 件すべてが `serial` になっていた
  - **wave は推定しない**。`subagents/agent-*.meta.json` の `toolUseId` を transcript の `tool_use` ブロックへ引き当てると、どのアシスタントメッセージから発行されたかが確定する。時間閾値も LLM の自己申告も要らない（`agents.explorer_waves` は打点の自己申告なので、打ち忘れた瞬間に違反の証拠も消えていた）
  - **束ねるキーは行の `uuid` ではなく `message.id`**。transcript は 1 メッセージを tool_use ブロックごとに別行へ分解して書くため、`uuid` で束ねると**一括発行した回まで「1 体ずつの wave」に見え、全件が `serial` に落ちる**（実装中に踏んで実データで気づいた）
  - `verdict` を `batched`（全体が 1 メッセージ）/ `layered`（層ごとの wave。**設計上正当**）/ `serial`（単独 wave が 3 連続以上）/ `single` / `unknown` に整理し、**警告は `serial` だけ**にした。`mixed` の廃止と併せて「⚠️ が出たときだけ行動する」契約を回復する
  - 閾値の根拠: 1 体だけの wave 自体は正当（設計上 1 体しか起動しないフェーズがある）。2 連続も skeptic → meta のような別ゲートの並びで説明がつく。**3 連続以上はこのパイプラインの層構造では説明できない**。上げ下げの判断材料として `waves` / `wave_sizes` / `max_solo_run` を payload に残す
  - **引き当てられない agent が 1 体でもあれば判定しない**（`verdict: "unknown"` + `unresolved`）。一部だけで wave を組むと wave 数が実態より小さく出て `batched` 寄りに誤判定する。#142 が持っていた原則（「一括だった」に倒さない）を**両側**に効かせた
  - 実データでの検証（直近 8 セッション）: 旧判定は 8/8 が `serial`。新判定は `batched` 1 / `layered` 5 / `serial` 2（`[1,1,1,...]` の 9 wave と、末尾に単独 wave が 5 連続する 30 体の回）
- **`review-retro.sh` は `dispatch.schema >= 2` だけを集計する**。schema 1 は誤った単位の判定なので、混ぜると「守られた割合」が構造的に 0% に張り付く。除外件数は出力に明示する
- `publish-review-event.sh` の WARN 文言が「fleet は**最長 1 体ぶん**」（レビュー全体）と `review-retro.sh` の「**wave 内最長の 1 体**」（wave 単位）で食い違っていた。wave 単位に統一した

### Changed
- `references/orchestration-measurement.md` `## 16` の `dispatch` 契約・`measurement_gaps` の `dispatch` 語彙を追従（SSoT pin 再打刻）

## [2.70.0] - 2026-08-18

**計測できていなかった 2 つを payload に載せた。** このマシンの `review:completed` 37 件を transcript と突き合わせた実測が契機（GitHub issue #142 / #143）。

### Added
- **`dispatch`: agent の発行パターン**（#142）。`measure-tokens.sh` が agent transcript の**起動時刻の間隔**から `batched` / `serial` / `mixed` / `single` を判定し、publish が payload に載せる。`verdict` が `batched` 以外なら stderr で警告する
  - **なぜ要るか**: `duration_fleet_min` は「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を区別できない。実測では **16 回中 13 回が逐次発行**で、累計 **431 分（7.2 時間）** を失っていた。守られた 3 回はいずれも 3〜5 体の小規模で、**体数が多い＝一括発行が最も効く回ほど破られている**
  - 一括発行の規約（#95 / `orchestration-guide.md ## 0`）は 2026-07 から存在する。**規約はあるのに守られない**原因は、守られたかどうかを誰も観測していないこと。事後計測なので暴発しない（発行そのものを hook で止める案より安い）
  - 判定できない回（agent 0〜1 体 / transcript を引けない）は `measurement_gaps` に `dispatch` を立てる。**「一括だった」に倒さない**
  - `review-retro.sh` に「一括発行が守られた割合」を追加
- **self-review でも `tokens` を載せる**（#143）。実測: 37 件すべてで欠測しており、**体数削減・分冊・遅延読み込みの効果を一度も測れていなかった**
  - 旧版は「self-review は publish の後に Step 7 の修正作業が続く」として除外していたが、`measure-tokens.sh` は **publish 時点の transcript を読む**ので `t0 → publish` は閉じている（後続の修正はまだ transcript に無い）
  - 窓に修正作業が混ざるのは**遅れて publish した回だけ**なので、そこは `window: "since-t0-late"` として区別する（集計側は `since-t0` だけを使う契約なので自動的に外れる）

### Changed
- `references/orchestration-measurement.md` `## 16` / `## 17` を追従（`tokens` の適用範囲・`dispatch` の契約・`measurement_gaps` の語彙）

## [2.69.1] - 2026-08-18

**セルフレビューが自分の機械層変更に見つけた欠陥の修正。** 機械層の exit code 契約（0 緑 / 1 検出 / 2 判定不能）が、消費側の `run-oracles.sh` で失われていた。

### Fixed
- **`run-oracles.sh` が機械層の exit 2 を `red` に落としていた**（`status=green|red|timeout|error` の `*)` に吸われていた）。`red` は「検査が問題を検出した」の意味で、AskUserQuestion も「問題を検出しました。直しますか？」と提示するため、**実体が「jsonschema 未導入で検査を実行できなかった」でも直せない指摘として突きつけられる**。`2` を `126|127` と同じ `error`（前提が無く判定できなかった）へ倒す。`references/machine-layer.md` の status 表も exit 2 を明記する形に更新した
  - 契機: リポジトリ側の機械層が exit 2 を返す条件を広げたこと（jsonschema 不在での SSoT 検査）。宣言側（`.claude/review-oracles.sh`）は当初から「exit 2 = 判定不能」を契約していたが、消費側がその status を持っていなかった
  - `test_code_review_oracles.py` に exit 2 → `status=error` を固定するテストを追加

## [2.69.0] - 2026-08-17

**機械層を agent の手前に出し（#137）、残っていた同梱スクリプト 7 本にテストを付けた（#138）。** テストを書いた過程で**実バグ 9 件**を検出している（1 本あたり 1.3 件）。うち 1 件は **UTF-8 ロケールでしか再現しない**型で、開発機のシェル設定次第で人手レビューからは永久に見えない。

### Added
- **self-review Step 1.7: 機械層の先行実行**（`scripts/run-oracles.sh` / 原則 8 の除外を部分撤回。設計判断は `.claude/adr/20260817170000-machine-layer-before-self-review-agents.md`）。**プロジェクトが `.claude/review-oracles.sh` を置いたときだけ**動き、無ければ完全 no-op:
  - **コマンドはプラグイン側で推測しない**。self-review は任意のプロジェクトで動くので、`package.json` から lint を当てにいくと誤検出時に任意のコマンドを走らせることになる。**何を安いオラクルとみなすかはプロジェクトの判断**なので、宣言ファイルの存在自体を opt-in として扱う
  - **`red` で自動停止はしない**。AskUserQuestion で続行可否を委ねる（「lint は赤いが設計レビューを先に受けたい」を潰すと recall が落ちる）。隣の Step 1.4（重複検出）と同じ形
  - **`timeout` / `error` を green に倒さない**。緑と欠測を混ぜると、reviewer は空の「既知」リストを見て「機械層は何も検出しなかった」と読む
  - **「既知」の抑制は `同一 file:line × 同一ルール` に限る**（過剰抑制は同じ箇所の別欠陥を消す）。機械層の結果を agent に再検証させない（Opus 5 規約）
  - 効果は `findings_class.lint` の減少で測り、`judgement` が減ったら注入をやめる（ADR に撤回条件）
  - macOS に `timeout` が無いので**プロセスグループごと打ち切る**（`set -m` + `kill -TERM -$pid`）。孫プロセスのテストランナーが生き残らないことをテストで固定した
- **同梱スクリプト 7 本に CLI テストを追加**（`test_code_review_diff_scripts.py` / `test_code_review_detection.py` / `test_code_review_context.py` / `test_code_review_oracles.py` = 175 件。全体 333 → 512 件）:
  - `cleanup-agent-worktrees.sh` は**不可逆**（worktree を消す）なので「**消さない**条件」を肯定側より厚く書いた（メインリポジトリ上では走らない / 配下でない worktree に触れない / 未コミット変更があれば残す / 生きた worktree の使用中ブランチを消さない）
  - `gh` は PATH 先頭の stub に差し替え、**stub を本物の flag 体系に合わせた**（`gh repo view` に `--repo` は無い等）。ここを緩めると「stub でだけ通る」経路ができる
  - `detect-recent-review.sh` は `publish-review-event.sh` と**2 本通しで**測る（書き手と読み手が同じ digest を見ているかは片方の単体テストでは分からない）
  - **テストの env で `LC_CTYPE=C.UTF-8` を固定**した。C ロケールでは下の多バイト展開バグが**再現しない**ため、開発機のロケール次第でテストが空振りする
- **`validate_plugin_quality.py` に `shell-multibyte` 検査を追加**（errors）— `"$VAR（..."` のような**波括弧なしの展開 + 直後の非 ASCII**を検出する。既存 repo での実測は該当 1 件（下の実バグそのもの）＋コメント行 1 件（除外規則で落ちる）で、**偽陽性 0 件**を確認してから errors にした
- **`.claude-plugin/scripts/machine-layer.sh`（repo 側）**: 検査の並びの正本を 1 本に集約した。同じ並びが Stop hook / pre-commit / CI / self-review 前段の 4 経路で要り、`auto-quality-check.sh` のヘッダは既に一覧の複製を抱えていた

### Fixed
- **`diff-slice.sh --list` が幻のパスを出し、rename / mode 変更・binary を落としていた**（レビュー対象の切り出しなので、取りこぼすと**レビューしていない差分が「レビュー済み」になる**）:
  - 追加行の内容が `++ foo` だと diff 上は `+++ foo` になり、行全体に `^\+\+\+ ` を当てていたため**本文が一覧のパスとして載っていた**
  - **内容変更を伴わない rename・mode 変更のみ・binary は `---` / `+++` を持たない**（実測）ため一覧から丸ごと落ちていた。`rename to` と `diff --git a/P b/P` の対称形からの復元を足した
  - **空白入りパスが必ず 0 件マッチ（exit 3）になっていた**。git は `--- a/sp ace.txt` の末尾にタブを 1 つ付ける。**合成 fixture にはそれが無く、「空白入りパスを扱える」というテストが何も検証していなかった** — 実 git 出力に切り替えて発覚した型
  - `--list` と切り出しが**別実装**だったのを 1 つに統合した（食い違うと「一覧に出たのに切り出せない」が起き、agent は「担当ファイルの diff が取れない」と報告して 1 体ぶん空振りする）。「一覧に出たパスは必ず切り出せる」を不変条件としてテストに固定
- **`triage-signals.sh` の `large-file` シグナルと `## agents-md` が、リポジトリルート以外から起動すると黙って消えていた**。スクリプト自身が「self-review は worktree に入らず cwd はセッション起動 dir のまま」と明記して `git grep` だけ `-C "$WT"` で直しており、**同じ前提が他の 2 箇所に適用されていなかった**。`## agents-md` は reviewer の CLAUDE.md 準拠観点の入力なので、空になると観点が入力なしで走る
- **`detect-recent-review.sh` の WARN が UTF-8 ロケールで出ないまま exit 1 していた**。`"$DIFF（"` は `（` の先頭バイトまで変数名に取り込まれ、`set -u` で `DIFF<0xef>: unbound variable` になる（`C.UTF-8` / `ja_JP.UTF-8` / `en_US.UTF-8` で再現、C / POSIX では再現しない）。**「明示指定の不在は caller のバグなので黙らない」ための経路が、まさに黙っていた**
- **`fetch-pr-context.sh --repo` 経路が丸ごと機能していなかった**。`gh repo view` に `--repo` flag は無い（位置引数）ため `unknown flag` で落ちる。`--repo` が指定されているならその値が答えなので API 呼び出し自体を省いた。あわせて**取得失敗時に前回の PR コンテキストが残る**問題を塞いだ（成功時のみ mv するガードは空ファイル対策で stale 対策ではない — `triage-signals.sh` の diff と同じ規約に揃えた）
- **`cleanup-agent-worktrees.sh` がブランチ削除の失敗を件数から落としていた**（worktree 側は `失敗 N 件` を報告するのに非対称で、「必ず件数を報告する」という自身の契約に反していた）
- **`measure-tokens.sh` の `--session` / `--since` が値欠落時に `set -u` の生エラーだけ出していた**（他の同梱スクリプトと同じ形で弾く）
- `triage-signals.sh` の `doc-prose-lines` のコメントが実挙動と食い違っていた（**箇条書きの本文は数える**。数えないのはマーカーだけの行）。本文が箇条書きの doc が大半なので、除外すると doc-substance の閾値にほぼ届かない — コメント側を実装に合わせた

### Changed
- **変異テスト実行中のコミットを pre-commit で止めた**（repo 側）。実行中はディスク上のファイルが変異体に差し替わっており、その状態で `git add` すると**変異が index に入る**（実測: `and` を `or` に反転した行がステージされていた）。ツール側のガードは「対象ファイルの外部編集」だけを見ていて staging は素通りするので、ジャーナルの実在で決定的に判定する
- `self-review` の embed mode return 仕様と Vault 照合を SKILL 本文からポインタに置き換えた（正本は `orchestration-optional-flows.md ## 15` / `## 11`。本文の複製を減らし、Step 1.7 追加後も本文サイズ上限に収めた）

## [2.68.1] - 2026-08-17

### Fixed
- **`FC_MIN_SCHEMA` の層別が現時点で恒真であることを明記**（`review-retro.sh`）— `schema_of` は欠落・`0` を `1` に丸めるので `>= 1` は何も除外しない。前方互換のフックとして正しいが、`dropped_schema: 0` を「層別が効いている」と読める形だった（このリポジトリが繰り返し踏んでいる「死んだ指標」の型）。**恒真であること自体を回帰テストで固定**し、分類の定義を変えて 2 に上げたらテストが落ちるようにした
- 版ラベルの追随漏れ（3 回再発）に**決着をつけた**。**規約の説明文は行内コード／フェンスに入れる**（SSoT pin と同じ扱い。入れないと置換・検出が説明文ごと壊す — 実測で 7 箇所を書き換えた）。検出側の機械化は 2 度失敗している（履歴参照と区別できない / Claude Code の版と表記が衝突する）ため、**検出をやめて発生を消す**方に倒した — プラグイン配下の md / sh / py には `vNEXT` と書き、`bump-version.sh` が bump 時に実版へ置換する。経緯と残る穴は `design-notes/pending-optimizations.md ## 9`

## [2.68.0] - 2026-08-17

**「self-review が改善のたびに指摘を出し続ける」問題への構造対応**（運用課題 / issue 由来ではない）。直近 2 回のセルフレビューで報告した MAJOR 14 件を「何が捕まえるべきだったか」で分類すると **lint 6 / 回帰テスト 6 / 判断が要る 2 ＝ 86% が機械で捕まる層**だった。agent 8 体を回して linter の仕事をさせていたことになる。

### Added
- **doc / 構造 lint を `validate_plugin_quality.py` に追加**（errors）— いずれも**セルフレビューが実際に見逃した / agent 8 体を要した**型で、判定は行走査だけで決まる:
  - **番号見出しの重複**: 同一ファイルの `## 5` が 2 つあると他 doc からの番号参照が曖昧になる（SSoT pin の anchor 曖昧一致と同型）。v2.67.1 で実際に踏んだ
  - **孤立した `>` 行**: blockquote の途中に見出しを挿入すると継続行の `>` だけが残り、後続の規範段落が別の節へ再親子化する。**導入直後に v2.67.1 の消し残りを 1 件検出した**（8 体のセルフレビューが見逃した箇所）
  - **テスト収集漏れ**: `if __name__` より後ろの `TestCase`。`unittest.main()` が `sys.exit()` するので**直接実行だけ静かに件数が減り、しかも `OK` が出る**
  - **本体同一のテストメソッド**: 名前が別の主張をしているのに中身が同じ＝独立に失敗しうる条件を持たない。**導入直後に再発を 1 件検出した**（v2.67.1 で直したはずが、fixture のノイズを既定化した副作用で元に戻っていた）
  - 4 種すべてに回帰テストを添え、**実装に欠陥を注入すると該当テストが落ちること**を確認（フェンス除外を外す変異も含む）
  - **版ラベルの追随漏れ検出は試して外した**（同版内）。初回実行で **6/6 が偽陽性**（CHANGELOG が履歴を語る行・doc が過去版を参照する行）で、markdown だけでは「この変更を指すラベル」と「履歴への参照」を区別できない。**偽陽性の warning は「⚠️ が出たときだけ行動する」契約を壊すほうが損**。表記の規約が先に要る → `design-notes/pending-optimizations.md ## 9`
- **`findings_class` を payload に追加**（`lint` / `test` / `judgement` + `schema`）— 「機械が見つけるべきものを agent に探させている割合」を追跡する。`review-retro.sh` が構成比を出し、`lint` か `test` が 30% を超えたら（n>=20）シグナルを出す:
  - **0 件を目標にしない**（300 行の diff で指摘 0 件のレビューの方が疑わしい）。見るのは構成比で、`lint` が高い＝ linter を足す余地、`test` が高い＝回帰テストが足りない
  - **`lint` は「今ある linter が検出できた」ではなく「静的検査で検出しうる」**。そうしないと「lint が無いから lint 可能な指摘は 0 件」という恒真の指標になる

- **同梱スクリプトの回帰テストを新設**（`.claude-plugin/scripts/tests/test_code_review_scripts.py` / 23 件）— `review-timing.sh` / `publish-review-event.sh` / `review-retro.sh` は全履歴で 7 / 9 / 4 回変更されているのに**テストが 0 件**で、挙動は手で fixture を叩いて確認していた:
  - **ハーネスは python の subprocess**（bats を入れない）。既存の `unittest discover` にそのまま載るので pre-commit / CI / Stop hook の 3 経路に**設定変更ゼロ**で乗り、CLI サブコマンドという実際の呼ばれ方をそのまま再現できる
  - **範囲は「v2.66.0〜v2.67.1 で実際に壊れた経路」**（`publish-pending` の 4 状態 / 掃除の成否追随 / `late-publish` の閾値と review 非適用 / `missing_coverage` の fail-fast / 版マーカー注入 / retro の層別と gap 分母）。全分岐の網羅は費用が見合わない
  - 変異テスト 5 種（`pub` マーカー判定を外す / 掃除を成否から切り離す / `fullmatch` を `match` に戻す / late 閾値を無効化 / 較正の層ガードを外す）で**すべて該当テストが落ちること**を確認
  - 代償: テスト全体が 0.03 秒 → **5.1 秒**（subprocess 1 回 24ms）。pre-commit の体感に出るので、増えたら分離を検討する

### Fixed
- **セルフレビュー（MAJOR 19 件）のうち、この版に残す 10 件を修正**。19 件中 9 件は公開記録の典拠ガード hook（#130）由来で、**hook ごとこの版から外して issue に差し戻した**（測定は済んでいるが、実装が fail-loud 宣言に反する無言経路を 3 つ抱えており、doc の実測値も検算を通らなかった）:
  - **`findings_class` に publish 側の検証を足した**（合計一致 + 型 / `missing_coverage` と同じ位置で fail-fast）。正本は「合計は報告件数と一致させる」と契約していたのに強制力が無く、**`missing_coverage` で「規約だけでは守られない」と学んだ直後の新フィールドが同じ穴を持っていた**。しかもこれは「次に何を機械化すべきか」を決めるメーターで、汚染時の損失が他より大きい
  - **`findings_class` のシグナル下限を「レビュー回数 × 指摘件数」の二重にした**。件数だけで切っていたため**指摘 23 件のレビュー 1 回で点灯**し、実際に導入直後の retro が点灯して見せた（既存シグナルはすべて回数で切っている）。あわせて**しきい値を 30% → 55%** に上げた — 実測ベースラインが lint 43% / test 43% なので 30% では定常状態で常時点灯する
  - **`findings_class` を版マーカーで層別**（同ファイル冒頭の「版マーカーを持つ指標は必ず層別する」に従っていなかった唯一のレイヤーだった）
  - **`if fc_total:` が「指摘 0 件」と「未収録」を同一視**していたのを `fc_rows` 基準に直した（`--json` は正しく出るので**人間向けだけが嘘をつく**状態だった）
  - **retro の出力から repo 固有ファイル名を外した**（`validate_plugin_quality.py` は配布物に入らないのに、他プロジェクトの利用者に提示されていた。プラグイン独立性）
  - **`check_duplicate_test_bodies` の誤検知を 2 つ塞いだ**: decorator / 引数を比較キーに含める（`@patch` 違いは本体が同じでも独立に失敗しうる正当なテストなのに **errors で pre-commit をブロックしていた**）/ `pass` のみのプレースホルダを対象外に（3 つあると 2 件目以降が全部誤検知）
  - **孤立 `>` の探索を節境界内に限定**（引用が節末尾で終わり次が見出し、という正常形を誤検知しうる）
  - **テストの空振りと片側検証を修正**: doc lint の `*/skills/*/SKILL.md` 経路が未カバー（glob から落としても全件 pass）/ `late-publish` シグナルの**点灯する側**が無く分母を 0 に潰す変異が生存していた
  - doc の数値と参照を訂正: 「直近 20 コミットで 7〜9 回」→ 実測は 7 / 9 / **4** 回（全履歴）/ `pending-optimizations.md` の裸の `## 9` 参照 3 箇所を `triage-dynamic-gates.md ## 9` と明示（**新設 `## 9` と衝突していた — error 級 lint を新設した理由と同型の曖昧さを同じコミットで作っていた**）
- v2.67.1 の消し残りだった孤立 `>` 行（`## 16`）を除去。**新設した lint 自身が検出した**
- `test_matching_values_produce_no_error` と `test_noise_tables_in_the_same_section_are_not_read` の本体が再び同一になっていたのを分離（前者を noise 無しの baseline に）。**これも新設 lint が検出した**

## [2.67.1] - 2026-08-16

v2.67.0 のセルフレビュー（MAJOR 8 / MINOR 3）の修正。**8 件中 4 件が「検証機構自身が静かに効かなくなる」型**で、#134 が塞ごうとした穴と同じ構造を新しい検証コードが持っていた。

### Fixed
- **`schema-markers` チェックの縮退を fail-closed に直した** — 「script と doc の両方が在るとき以外は無音 skip」だったため、**片方をリネーム / 移動しただけで保護が無言で外れた**（実測: script のパスを外すと `errors == []`）。skip の判定を「プラグインが在るか」に変え、片側欠落は error にする。兄弟チェック（`check_safe_hook_sync` / `check_routing_axes_sync` / `check_ssot_pins`）と縮退の向きを揃えた
- **doc 側を「最初のテーブルブロック」限定にした** — anchor の節は次の同レベル見出しまで（実測 **193 行**）に及び、`## 16` は payload 契約の本体なので同型の表が同居する。節全体に `findall` を掛けていたため、**節の後方の同型行が dict の後勝ちで正本を上書きした**（実測: 1 行足すと `gate_schema` が 3 → 2 に化けた）。表の中の重複キーも後勝ちで黙らせず error にする
- **`bool` を整数として受理していた** — `isinstance(True, int)` は真なので `{"schema": True}` が doc の `1` と `True == 1` で一致扱いのまま素通りし、publish される JSON に `true` が入る経路だった。あわせて「読めない」理由を 5 種に分けた（一律「記法変更か構文エラー」は値の型が違うだけの回に誤った是正先を指す）
- **回帰テストが直接実行で 8 件走っていなかった** — 新クラスを `if __name__ == "__main__": unittest.main()` の**後ろ**に足したため、`unittest.main()` の `sys.exit()` で後続のクラス定義が評価されず、**直接実行だけ静かに 33 件になっていた**（`discover` は 41 件。どちらも `OK`）。`__main__` を末尾へ移し、**収集漏れ自体を検知するテスト**を足した
- **「節外を読まない」テストが別テストと本体同一で空振りしていた** — fixture が非対象表を節の**外**に置いており、実データ（同一節内に非対象表が 2 種）を再現していなかった。節内ノイズ・表内ノイズ・後方の同型行・重複行を実データ相当に置き直し、**変異テスト 5 種すべてが該当テストを落とすこと**を確認（fail-open に戻す / ブロック限定を外す / bool ガードを外す / 重複検知を外す / 行書式を緩める）
- **今回の注記 5 箇所の版ラベルが `v2.66.0` だった**（実際は v2.67.0）。この repo は版ラベルで効果測定の母集団を切るので、CHANGELOG と doc が 1 版ずれる（#131 で直した「サンプルが逆の版バケツに入る」と同型を doc 側に持ち込んでいた）
- **`## 16` の新見出しを blockquote の途中に挿入していた** — payload テンプレートの規範（「層のオブジェクトそのものは必ず入れる」）が新節の配下に再親子化し、孤立した `>` 行が残っていた。新節を blockquote の後ろへ移した
- **保留判断の根拠サンプルが実データと合っていなかった** — #136 の前提訂正が名指しした「MAJOR 7 件の回」は存在せず、`skip_reason` を持つのは 3 件（MAJOR 8 / 6 / 8）。**結論（3 件とも effort=high の設計どおりの不発）は独立に成立する**が、証拠の同定が誤っていたので実値に置き換えた。閾値の数値を `## 9` から書き写していた 2 箇所も参照に変えた（片方だけ古くなる複製を作らない）
- **`design-notes/pending-optimizations.md` の `## 5` が重複していた**（v2.66.0 で追加した節が既存節と衝突）。CHANGELOG が同じ anchor で別々の節を指していたので、v2.66.0 以降に足した 3 節を `## 6` / `## 7` / `## 8` へずらし、参照 5 箇所を追随させた
- **`## 8`（Agent hook）の保留理由に `SubagentStop` の検討を足した**（セルフレビューの 🔁 指摘）— 本 repo の `hooks.schema.json` が正式イベントとして許可しており、**体数を数えるだけならこちらで足りる**ので「`Agent` で発火するか不明」は打ち手全体のブロッカーにならない。打点漏れの検知は `SubagentStop` / 一括発行違反の検知は `Agent` の PreToolUse、と役割を分けるのが第一候補
- **WARN 仕様の doc が「破られた可能性」のままだった**（script は v2.67.0 で断定に変えた）

## [2.67.0] - 2026-08-15

計測基盤の残り 3 件（#134 / #136 / #135）。いずれも**検知経路の不在**で、値そのものは現時点で壊れていない。

### Added
- **版マーカー定数の script ↔ doc 同期を機械検証する**（GitHub issue #134 / `validate_plugin_quality.py` の `schema-markers` チェック）— v2.65.0 の注入方式（#125）で「2 箇所を人手で揃える」関係が SKILL↔doc から **script↔doc へ移動しただけ**で、強制力はコード内コメント 1 行しかなかった。**SSoT pin は md 限定なのでこの関係を宣言できない**（Gotchas / ADR-20260813223000）ため、pre-commit も CI も無言で通していた:
  - `orchestration-measurement.md ## 16` に機械可読な「版マーカーの現行値」表を新設し、`SCHEMA_MARKERS` を `ast.literal_eval` で読んで突合する。ずれは Critical
  - **`tokens.schema` を対象外にする例外を明文化した**（#134 の併発指摘）。`SCHEMA_MARKERS` は「層のオブジェクトが無ければ `payload:<field>` gap を立てる」経路と対なので、**review 限定フィールドを入れると self-review で毎回 gap が立つ**。規約文だけ読んだ将来の追加者が区別に気づけるようにする
  - 回帰テスト 8 件を追加（33 → 41）。**期待値はテスト側の 1 つのリテラルから script / doc の両 fixture を生成して独立に構築する**（CLAUDE.md「検証機構の期待値をその機構自身で生成すると、壊れていても全件 pass する」）

### Changed
- **反証スキップ時のレポート文言を「未実施」に変えた**（GitHub issue #136）— `反証: 対象 0 件` は**「検証したが問題なし」と読める**が、実際は「検証していない」で、確信度の表示が実態より高く出ていた。`no-eligible-findings` のときだけ `反証: 未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）` と書く（他の 4 つの skip 理由は「この構成では走らせない」なので従来どおり）
  - **ゲート幅の拡張（#136 の本命案）は保留**。「加減算で報告閾値を超えた MAJOR を対象に足す」は指摘として妥当だが、**既定 high では meta が走らず反証 wave 自体が無い回が多いため、足すと直列 wave が 1 本生える**（xhigh / max は既に MAJOR 全件が対象なので効くのは high 限定）。`## 9` の再監視条件（`gate_schema >= 2` が 10 件 / `no-eligible-findings` 50% 以上）が点灯してから判断する → `design-notes/pending-optimizations.md ## 7`
  - **issue の前提を実データで訂正した**: #136 は実例を xhigh としているが、`skip_reason` を持つサンプルは 2 件とも **effort=high** で、どちらも設計どおりの不発だった（xhigh で MAJOR が対象外になっていた事実は無い）
- **explorer の一括発行違反・wave 打点漏れをレポートに出すようにした**（GitHub issue #135 / 案 B）— 規約違反は実行中に何も起きず、**打点漏れは違反の証拠自体を消す**（`explorer_waves` は打点の行数で直列発行を暴く指標なので、打ち忘れると検知不能になる）。publish の WARN に「レポート末尾に `⚠️ 計測: ...` を 1 行追記せよ」の具体指示を足し、両 SKILL に追記規約を書いた
  - **本命は `Agent` hook（独立した観測者）だが未採用**。subagent のツール名が `Agent` であることは transcript で実測したが、**PostToolUse が `Agent` で発火するかを確認できていない**（hook の発火は transcript に残らず、セッション内で settings を足す実験は偽陰性を返しうる）。検証手順・自己判定の要件・`component-addition-advisor` ゲートを → `design-notes/pending-optimizations.md ## 8`

## [2.66.0] - 2026-08-14

計測基盤の 3 件（#133 / #132 / #131）。v2.65.0 と同じ「レビュー基盤の効果を判定する側」の欠陥で、型は **記録が黙って落ちる / 落ちても実行中に誰も気づかない**。

### Added
- **`review-timing.sh publish-pending` と `mark t2` の締め通知**（GitHub issue #133）— self-review Step 6.4 の publish が、レポート出力後そのまま Step 7 の修正フローへ進むと踏まれずに終わっていた。**publish は副作用のみで標準出力に何も足さないため、脱落しても実行中は誰も気づかない**（実測: MAJOR 4 件を報告して全件修正した回が丸ごと欠測。`meta_reviewer.gate_schema=3` かつ `fired` のサンプルを 1 件失い、`## 8` のロールバック判定に要る 10 件の蓄積が 1 件のまま）。ユーザーが事前に「指摘は全部修正して」と伝えている回ほど落ちる:
  - **`mark t2` が「締めは publish で終わる」を stdout に出す**（打点の直後 ＝ 落ちる直前に言う）。**「次は publish」とは書かない** — review の締めフロー 1〜3（精査・解説・ドラフト）を飛ばす誘導になるため、終点として言う
  - **`publish-pending` が「`t2` があって `pub` が無い」で未 publish を検出する**（`mark published` は publish 成功時のみ打つ）。呼ぶ位置は self-review Step 7 冒頭（**`--embed` / 指摘 0 件でもここだけは実行する** — embed は publish の後に呼び出し元の作業が続く＝最も落ちやすい経路）/ review 締めフロー 5（必須ステップ）。**ファイル不在は無言** — publish 済みで掃除された回と「そもそも計測していない」を区別できないので、鳴らす側に倒すと毎回鳴って「⚠️ が出たときだけ行動する」契約が壊れる
  - **一時ファイルの掃除を publish 成功時のみに変えた**（セルフレビュー指摘）。旧来は成否に関わらず掃除しており、**イベントが書かれなかった回ほど痕跡が残らない**という逆向きの縮退だった（打点ごと消えて再 publish もできず、ガードもファイル不在で無言 = 最も損失の大きい回だけ見逃す）。失敗回は一時ファイルを残すので同じ引数で再実行すれば復旧できる。`pub` マーカーは `--keep-temp` でファイルが残る回の誤検知も同時に潰す
  - **SKILL 側は「レポート出力 → `mark t2` → 6.4 publish」を不可分の締めとして書き直した**（番号が分かれているだけで 6.4 は任意ステップではない）
  - **Stop hook への昇格は見送った**（判定は決定的だが、glob が他セッション・他リポジトリの計測ファイルにも当たる誤検知設計が未確定）。理由と再判断の材料は `design-notes/pending-optimizations.md ## 6`
  - **遅れて publish した self-review は `duration_min` を `-1` に倒し `late-publish` gap を立てる**（t2→publish が 10 分超）。self-review の `duration_min` は「t0 → Step 6.4」が契約なので、修正作業の後に踏むと契約と違う区間を**もっともらしい大きい値**として載せてしまう（`## 13.1` の「縮退先は欠測であって誤値ではない」）。**review には掛けない** — あちらは締めフロー（人間待ち）込みが契約。`duration_fleet_min` 以下は t2 で閉じているので影響を受けない

### Fixed
- **`missing_coverage` の語彙を publish 時に機械検証する**（GitHub issue #132 / `^[a-z0-9-]+(:[a-z0-9-]+)?$`）— 「識別子のみ」の規約（`## 16`）は v2.44.0 からあったが検証が無く、実データに理由つき自由文が **12 種**混入していた。同一概念が `adversarial-verify` / `adversarial-verify: F2 未反証` / `adversarial-verify: 対象が実証済み` / `adversarial-verify:finding-A` の **4 項目に分裂**し、欠損観点の偏り集計（本フィールドの唯一の用途）が過小に出ていた:
  - **JSON 妥当性検証と同じ位置で fail-fast する**（`FATAL` で publish 中止）。**黙って正規化はしない** — どの識別子に寄せるかを推測すると別の綴り割れを作る
  - 理由・件数・finding id はレポート本文の「⚠️ 欠損観点」に書く規約なので、落として直させても情報は失われない
  - **フィールドごと落として通す逃げ道を塞いだ**（欠落は `measurement_gaps` の `payload:missing_coverage` として記録する）。塞がないと綴り割れが**静かな全欠測**に置き換わるだけになる
  - **`re.fullmatch` を使う**（セルフレビュー指摘）。`re.match` + `$` は末尾改行 1 個を通し、`json.dumps` がエスケープするので**下流のどの検証にも引っかからずに**綴り割れが復活する。publish 全体を落とす代償を払う検証を緩い一致で妥協しない
  - **自由文を指示していた上流 14 箇所を識別子に統一した**（セルフレビュー指摘 / 両 SKILL・`orchestration-guide` `## 5` `## 8a/8b`・`orchestration-dynamic-rounds` `## 6` `## 7` `## 9`・`triage-guide` `## 6.2`・`triage-dynamic-gates` `## 8` `## 8.5`）。**規約は v2.44.0 からあったのに、同じ doc 群が「観点未起動: `<focus>`（規模キャップ: `<帯>`）」等を記録せよと指示し続けていた** — 検証を入れた結果、指示どおり書くと publish が必ず落ちる状態になっていた（規模キャップが効いた回・Round 2 スキップ回・agent 失敗回が該当）。語彙に `round2` / `meta-reviewer` / `head-mismatch:<focus>` を追加
- **`severity_inflated` シグナルが上流較正の対策前サンプルで発火し続けていた**（GitHub issue #131）— `calibration_schema` が LLM の手書きだった v2.64.x 以前は全サンプルが層 1（v2.62.0 の較正対策**前**）に落ちるため、**`triage-dynamic-gates.md ## 9` が「上流対策の効果測定に使うな」と書いている累計値を、`review-retro.sh` のシグナル判定が使っていた**（実測: 51 サンプル中 `calibration_schema` を持つものが 0 件）:
  - 注入への移行は v2.65.0（#125）で済んでいるので、本版は**判定側のガード**。`severity_inflated` シグナルは `calibration_schema >= 2` の層でしか発火しない
  - **黙るだけにはしない** — 判定できない間は verdict 表の下に状態を 1 行出す（層 1 のみ = 「対策前」/ 層 2 が `VERDICT_MIN` 未満 = 「蓄積中 N/20」）。**層で切るだけでは足りない**（セルフレビュー指摘）: 現行版は `calibration_schema: 2` を常に注入するので層 2 は 1 件目で現れる一方、シグナルは 20 verdict を要求するため、**蓄積中が無言区間になって避けたかった誤読（無言＝効果あり）を作っていた**
  - **`uncertain` / `refuted` のシグナルには掛けない**。あちらは反証レイヤー自身の effort / バッチサイズの再監視条件であって、上流較正の効果測定ではない（較正版で層別する理由が無い）
- **`measurement_gaps` のシグナルを種類ごとに評価するようにした**（セルフレビュー指摘 / `review-retro.sh`）— 旧来は `max(gap_counts)` で最頻 1 種だけを閾値にかけていたが、**分母は種類ごとに違う**（`tokens` は review のみ / `late-publish` は self-review のみ / 他は全件）ため、生カウントで勝者を決めると母集団の違う指標を比べることになっていた。実害は 2 方向で、①分母の小さい種類が 1 件 100% で単発点灯しうる（同ファイルが「1 件でも点灯する条件を混ぜない」と宣言しているのに違反）②逆に 100% の種類が件数で負けて一度も評価されない。種類ごとに自分の分母で判定し、下限（5 件）も自分の分母に掛け、欠測率の高い順に上位 2 件までを出す

## [2.65.0] - 2026-08-14

計測 3 件（#125 / #129 / #126）。いずれも「レビューの中身」ではなく「レビュー基盤の効果を判定する側」の欠陥で、共通の型は **payload の一部を LLM に手書きさせている / そもそも記録していない → 下流の層別が壊れる**。

### Added
- **反証レイヤーに `fired` / `skip_reason` / `gate_schema` を追加**（GitHub issue #129 / 正本: `orchestration-measurement.md ## 16` + `triage-dynamic-gates.md ## 9`）— 3 つある動的層のうち**この層だけが発火記録を持たず**、`review-retro.sh` は `agents.verify > 0` から起動有無を推定するしかなかった。そのため **「走らなかった」と「走れる対象が無かった」を区別できない**:
  - 効いてくるのは既定 effort のゲートが狭いため。high の反証対象は非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）だけなので、**BLOCKER / CRITICAL が 1 件も出なければ MAJOR が何件あっても対象は構造的に 0 件**になる。実測（issue #129 / `pre_adjust_counts` を持つ 6 件）では未起動 3 件がすべて「effort=high かつ BLOCKER+CRITICAL=0」で、実装バグでもスキップでもなく**設計どおりの不発**だった
  - `skip_reason` の語彙は `effort` / `config` / `scope` / `emergency` / **`no-eligible-findings`**。**5 つ目だけは設計上の非該当ではない**ので下流の分母から外さない（`review-retro.sh` の `OUT_OF_SCOPE_SKIPS` がこの区別を持つ）。これが「ゲート幅が実効的に狭いか」の観測点になる
  - **ゲート設計を否定する変更ではない**。「詰めると取り下がるのは不確実だが報告される非対称ゾーン」という設計意図は妥当で、**測れないことが問題**だった。ゲート幅の再監視条件（`gate_schema >= 2` が 10 件かつ `no-eligible-findings` が 50% 以上）を `## 9` に明記し、`review-retro.sh` が ⚠️ シグナルとして自動判定する
  - 層ごとスキップした回もレポートに 1 行出す（`反証: スキップ（<skip_reason>）`。skeptic の silent skip 防止と同じ扱い）
- **トークン消費を `review:completed` payload に載せた**（GitHub issue #126 / `tokens` フィールド・**review のみ**）— `triage-guide.md ## 7` の核心テーゼは「**体数削減が確実に効くのは壁時計ではなくトークン**」なのに、payload は時間しか持たず `## 18` の自動集計も時間だけを見ていた。つまり**主要レバーが効かない指標を自動集計し、効く指標を集計していなかった**:
  - `## 17` の「skill 実行中に自分の消費量を観測できない」制約は **publish 時点（レポート出力後 ＝ transcript 確定後）には当たらない**。`publish-review-event.sh` が `measure-tokens.sh --json --since <t0>` を呼んで `main_output_k` / `main_cache_write_k` / `sub_output_k` / `sub_agents` を注入する（`measure-tokens.sh` に `--json`、`review-timing.sh` に `t0` サブコマンドを追加）
  - **窓は `t0` 以降**（`window: "since-t0"`）。`t0` を撮れなかった回は `"session"` になり、**集計側は `since-t0` だけを使う**（レビュー外の作業が混ざった窓を体数と対応づけない）
  - **self-review には載せない**。メインセッション共有でレビュー単独に切り出せず、窓の汚染度が読めない。review は Step 0 で必ず `EnterWorktree` する隔離セッション ≒ 1 レビューなので窓が近似として成立する。**この非対称は仕様**
  - `review-retro.sh` に main.output / sub.output の中央値と**体数 vs sub.output の相関**を追加した（「体数はトークンに素直に効く」という前提の検算。壁時計側の r とは別物として読む）
  - **`main.n == 0` は欠測に倒す**（セルフレビュー指摘）。review は必ずメインループのメッセージを出してから publish するので 0 は「引けなかった / 窓が空振りした」を意味する。ゼロを実測値として載せると retro の中央値と相関が壊れる（実測: 相関 **1.00 → 0.18**・中央値が 4 割過小）。人間向けモードにあった「黙って 0 を返さない」ガード（#104）が `--json` の早期 return で迂回されていた
  - **`sub_agents` は窓内に usage を持つ本数**に直した（同上）。glob 総数は `--since` が効かず、`window: since-t0` を名乗るオブジェクトに窓外の体数が混ざっていた（実測: `sub.n=0` なのに `sub_agents=8`）。glob 総数は `--json` の `sub_files` として別名で残し、payload には載せない
  - **`session` / `first_ts` を payload に残す**（同上）。transcript の選択は「候補 dir の最新 `.jsonl`」という推定で worktree 並列運用では取り違えうるが、値はもっともらしいので**この 2 つが無いと事後に検出できない**

### Fixed
- **版マーカーの整数を LLM の手書きからスクリプト注入に移した**（GitHub issue #125 / `publish-review-event.sh` の `SCHEMA_MARKERS`）— `pre_adjust_counts.schema` / `adversarial_verify.calibration_schema` / `recall_skeptic.{attribution,gate}_schema` / `meta_reviewer.gate_schema` は「常に N を入れる」定数なのに、**15 フィールドある手書き payload の一部**だった:
  - 落ちると欠測ではなく**サンプルが逆の版バケツに入って集計を汚す**ので、単なる欠測より悪い。実測でも `recall_skeptic.gate_schema` に導入後の miss があり、`calibration_schema` は 1 セッション中に 2 版跨いだためテンプレ追従が漏れた。**marketplace が worktree 並列運用前提なので version drift は常態**
  - スクリプトは版付きディレクトリ（`.../code-review/<version>/scripts/`）配下にあり**自分の版の定数を知っている**ので、注入なら構造的に漏れない（`duration_*` / `explorer_waves` / `measurement_gaps` / `diff_digest` が既に採っている方式の踏襲）
  - **層のオブジェクトごと落ちた回・`fired` が落ちた回は `measurement_gaps` に `payload:<field>` / `payload:<field>.fired` を立てる**（空オブジェクトを捏造すると「起動記録なし」として母集団に混ざるため注入はしない）。transcript を引けなかった回の `tokens` も同様
  - **「ゲートを動かす変更には必ず版マーカーを足す」規約の追加先を `SCHEMA_MARKERS` に変更**し、あわせて「動的層を足すときは `fired` / `skip_reason` / `gate_schema` の 3 点セットを持たせる」を #129 の一般化として `## 16` に足した
  - **区間マーカー（wave 打点）のパス脆弱性は本版では変更しない**（issue #125 のもう 1 つの提案）。`${CLAUDE_PLUGIN_ROOT}` の版付き絶対パスが更新で壊れる懸念は正しいが、**壊れるときは publish 自身も同時に壊れる**（同じ plugin root 配下）ため、打点だけを退避しても publish ごと失われて事象は「部分欠測」ではなく「イベント不在」になる。打点側の独立した対策では救えないので、`TS_FILE` のパスが版に依存しない（`--show-toplevel` + `TMPDIR` 由来）ことを確認したうえで据え置く
- **版マーカーの注入方式だけでは「発火記録の欠落」を層別できない**（セルフレビュー指摘 / #125 と #129 の相互作用）— 版マーカーはスクリプトが入れるので、**`fired` を落とした現行版 payload にも最新版が入る**。「フィールドの有無が版マーカー」という層別は旧版にしか効かず、記録漏れが `skip_reason=unknown` として分母に混ざっていた。合成イベントで再現したところ **`meta-reviewer が起動対象 8 件で 1 度も起動していない` という存在しない実装バグのロールバック提案が点灯**し、逆に #129 の反証シグナルは分母が膨らんで発火しにくくなっていた（100% → 50% の境界へ低下）。publish は `payload:<field>.fired` gap を既に立てていたのに retro が読んでいなかったので、`layer_stats` に `dropped_unrecorded` を足して外す
- **retro の欠測シグナルが gap の種類を問わず「打点箇所の見直し」を提示していた**（同上）— v2.65.0 で語彙が 3 種増えたのに文言が据え置きで、payload の記述漏れに対して誤った是正先を指していた（再現済み）。識別子のプレフィックスで是正先を出し分け、**`tokens` gap は review でしか立たない**ので分母も review に絞った（#127 と同型が新語彙側で再発していた）
- **retro のトークン節だけが「分母の明示」「版マーカーで層別」の作法から外れていた**（同上）— `window != "since-t0"` の回を件数も残さず捨てていたため、`t0` 打点が構造的に壊れて全回 `session` になったときに「サンプルが無い」と「計測が壊れている」を区別できなかった。`n_raw` / `dropped_window` / `dropped_schema` を出力に足した
- **doc の伝播漏れ・事実誤認 3 件**（同上）— ①両 SKILL のスコアリング手順 6 に「`schema: 2` を記録する」が残っていた（正本からは削除済みで、次に版を上げたとき SKILL だけが旧値を書かせ続ける）②`## 16` の「実測: 3 回連続で不発」が引用元の 6 件表から再現しない（間に起動回が 2 件挟まる。「3 回連続」は issue #129 の複数リポジトリを含む実運用報告）③「review は隔離 worktree セッション」が事実に反する（`EnterWorktree` は cwd と subagent slug を変えるだけでセッションはメインのまま。self-review を外す本当の理由は**publish の後に修正作業が続く**こと）
- **`review-retro.sh` の「動的層の発火」行で反証と round2 の母集団が絞られていなかった**（issue #129 / #127 と同型）— 括弧書きが自ら「skeptic / meta は絞った」と述べており、**残り 2 つは全サンプルが分母**だった。反証は `adversarial_verify.gate_schema >= 2`、round2 は `agents.round2` のキー存在を版プロキシにして絞る。あわせて `layer_stats()` の「価値」判定を層ごとに差し替え可能にした（**反証は指摘を足す層ではないので `findings_added` を持たず、既定のままだと価値率が恒常 0% に潰れる**）

## [2.64.0] - 2026-08-14

### Added
- **🔁 付録の対象を「報告閾値を割った全経路」へ拡張**（GitHub issue #128 / 正本: `scoring-guide.md ## 報告閾値を割った指摘の記録`）— 従来 🔁 付録は**反証由来の脱落専用**（`refuted` の −40 と `severity-inflated` の降格 / #109）で、**スコアリングの加減算（手順 3〜5 の減算・クランプ）で報告マトリクスを割った指摘は本文にも付録にも出なかった**。`docs/pipeline-design.md` の「no silent caps」に反する:
  - **反証レイヤーの対象は既定 high では非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）限定**（xhigh / max では 95+ と MAJOR まで拡大）なので、既定 high で MAJOR しか出ない回では反証由来の脱落が 0 件になり、**記録経路が丸ごと存在しなかった**
  - **加減算由来は severity を問わず記録する** — ①には「高 severity を反証で消さない」不変条件があるが、②にその保護は無い（`[unverified]` の 75 クランプで CRITICAL が、好みクランプの 40 で任意の severity が落ちうる）
  - 実測（2026-08-13 / self-review・effort=high・v2.63.1 の diff）: 「テストコードでの指摘 −10」で MAJOR 2 件（confidence 100→90 / 95→85）が閾値 95 を割った。どちらも内容は正しく実際に修正されたが、規則どおりの機械適用ではレポートのどこにも出なかった
  - 両 SKILL の Step 5 に手順 4.5 を追加し、Step 6 のレポート見出しを `### 🔁 反証で取り下げた指摘` → `### 🔁 報告閾値を割った指摘` に変更（脱落理由に経路①②が分かる情報を必須化）
  - **新設した正本 → 消費サイト関係に SSoT pin を打った**（両 SKILL → `scoring-guide.md#報告閾値を割った指摘の記録`。計 15 → 17 pin）。あわせて正本の見出しから括弧を外した — anchor は空白を含められず前方一致の区切りに `.` / 空白しか許さないため、`## 見出し（補足）` の形は pin で引けない

### Fixed
- **`review-retro.sh` の「計測の健全性」が版未導入サンプルを分母に含んでいた**（GitHub issue #127）— `synthesis %d/%d` / `explorer_waves %d/%d` の分母が全サンプル（`n_all`）だったため、**版を重ねるほど記録率が構造的に下がって見え**、「マーカーが記録できていない」と誤読させていた:
  - `orchestration-measurement.md ## 16` は「**フィールドの有無が版マーカー**」「層別は必ずフィールドの有無で行い、日付では切らない」と規定している。フィールド不在は「そのサンプルは古い版で publish された」の identification であって欠測ではない
  - 母集団を `measurement_gaps` を持つ回（= v2.62.0 以降）に絞った。**フィールド自身の有無を分母にすると循環する**ので、後発フィールドを版プロキシに使う
  - **2 フィールドで欠測の現れ方が違うので判定を分けた**: `duration_synthesis_min` は打点が無ければ `-1` が入るので存在判定（`measured()`）で検出できるが、**`agents.explorer_waves` は打点が無くても `0` が必ず入る**（`publish-review-event.sh` が無条件代入）。後者を存在判定で数えると母集団と恒真に一致し、**打点漏れがあっても常に 100% を表示する死んだ指標**になる。漏れは `measurement_gaps` の `explorer-wave` として現れるのでそちらで数え、分母も explorer を起動した回に絞る（未起動は該当なし）
  - 実測（このリポジトリ n=22）: `explorer_waves 4/22` → **`2/2`**（`n_modern` = 2）。**判定標本は 2 件**しかない。なお 6 マーカーを横断した instance ベースでは導入後分母 21/22 が記録済みで、「記録率が低い」という読みは分母の作り方に由来していた
  - `--json` は `measurement.n_modern` / `modern_synthesis` / `modern_explorer_waves` / `modern_explorer_waves_scope` を追加（既存 `have_*` は後方互換のため据え置き。**waves だけ分母が `scope` 側**）
- `scoring-guide.md` の不変条件節が旧見出し名「🔁 反証で取り下げた指摘」を参照していた（正本内の伝播漏れ）

## [2.63.1] - 2026-08-13

### Added
- **SSoT pin による正本 → 消費サイトの伝播検証**（15 pin / ADR-20260813223000）— v2.63.0 のセルフレビューで検出した欠陥 11 件中 **6 件が「正本を書き換えたが複製先に伝播していない」型**だったが、対応関係が doc の散文（「正本は X」）にしか無く機械検証できていなかった。消費サイトの冒頭に `<!-- SSOT: <path>#<anchor> @<hash8> -->` を宣言し、`validate_plugin_quality.py` が正本の該当節のハッシュと突合する:
  - 検証の意味論は**内容の一致ではなく「正本が変わったら消費サイトを確認して pin を打ち直す」手順の強制**。今回の 6 件はどれも言い換え・要約なので、既存の routing-axes 型（byte-identical 区間比較）では 1 件もカバーできなかった
  - **節単位**なので正本の無関係な節を編集しても発火しない。行末空白のみの変更も正規化で吸収する（実測で確認）
  - 打点先: `orchestration-guide.md ## 3.5` の 4 消費サイト（reviewer-prompts / orchestration-dynamic-rounds / review・self-review SKILL）ほか、`## 0` / `## 5` / `triage-dynamic-gates ## 8` `## 8.5` `## 9` / `orchestration-dynamic-rounds ## 6` `## 10` / `orchestration-measurement ## 16` / `triage-guide ## 7.1` / `reply-tone-guide ## 0.1`
  - 打ち直しは `--update-ssot-pins`（明示操作。pre-commit では自動更新しない。repo 全体を一括で打ち直す）

**同版内のセルフレビュー（explorer 1 + reviewer 5 + 反証 2）で初稿の欠陥を検出し対処した。** 最大のものは**機構そのものが silent に不発だった 1 件**:

- **節の切り出しがフェンス付きコードブロックを認識していなかった** — bash 片のコメント行（`# ...`）を見出しと誤検出して節を途中で打ち切っていた。実測で 14 pin 中 3 pin が該当し、`orchestration-measurement.md ## 16` は **156 行中 85 行しかハッシュ対象になっていなかった（46% が無保護）**。無保護側には `pre_adjust_counts` / `missing_coverage` / `adversarial_verify` の全フィールド定義が入っており、**両 SKILL の payload 契約が消費する中核部分がまるごと検証外**だった。pin の初期ハッシュを同じ壊れた関数で生成していたため 14 pin すべてが `ok` に見えていた（生成と検証が同一関数を共有する自己整合の盲点）。`_markdown_headings` でフェンス状態を追跡する形に修正し、対照実験で偽陰性の解消を確認
- **`--update-ssot-pins` が errors を捨てて exit 0 を返していた** — canonical 欠落 / anchor 不明などが「打ち直しで最も起きやすいミス」なのに沈黙し、`total: 0 pin(s) updated` と表示されていた。エラーを出力して非ゼロで返す
- **ファイル全体 pin の循環ガードを追加** — anchor 省略の相互 pin は打ち直しが収束しない（合成ケースで実測）。正本自身が pin を持つ場合は error にする
- **`#8` が同レベルの `## 8.5` を含まない**ことを docstring / CLAUDE.md に明記し、`triage-dynamic-gates.md ## 8.5` の pin を追加（散文では依存を明示していたのに pin が無かった）
- pin コメントの「打ち直し」文言が repo 全体一括であることを伝えていなかった点、消費サイトも md 限定である制約が未記載だった点、ADR の規模数値（280）が「正本」の言及行数であって宣言数（51）ではなかった点を訂正

上記 2 件を回帰テスト（`.claude-plugin/scripts/tests/` / stdlib unittest 24 件）で固定した。**期待ハッシュをテスト側で独立に構築する**ことで、生成と検証が同一関数を共有する自己整合の盲点を塞ぐ。変異テストで、フェンス修正を戻すと 5 件・update errors 修正を戻すと 1 件 fail することを確認済み。pre-commit / CI / Stop hook の 3 経路に接続した。

## [2.63.0] - 2026-08-13

実 PR 1 件（medium 帯 core 7 files / 208 lines・effort `xhigh`・全体 81 分・直列 wave **5 本**・agent 12 体）の区間計測と `measure-tokens.sh` を突き合わせて特定した 4 点（GitHub issue #124）。`duration_synthesis_min` が 2 分しかなく、`orchestration-measurement.md ## 14` の切り分けに従えば打ち手は scoring 側ではなく **wave 側**という診断に基づく。

### Changed
- **unmet 分類表の「他リポジトリ」を実体の有無で 2 分割**（`triage-dynamic-gates.md ## 8` / issue #124 (a)）— 旧表は他リポジトリを一律 到達不能 に置いていたが、**兄弟ディレクトリに clone があれば `Read` / `Grep` で普通に届く**。実測では該当する unmet 2 件を Round 2 起動と誤判定し、**直列 wave 1 本（3.6 分 + プロンプト構築）を消費したうえ、同じファイルをオーケストレーターが後から読み直して二重作業になった**:
  - 判定は「target が指すパスを `Glob` / `Read` で 1 度試す」に還元する。**LLM の「たぶん別リポジトリだから無理」を挟まない**ので冪等になる
  - 実体あり = セッション到達可能（v2.60.0 が用意した「メインで直接照会して解決。Round 2 の代替であって追加ではない」経路に載る）
- **追加反証バッチに `confidence + 15 >= 報告閾値` の上乗せゲート**（同 `## 9` / issue #124 (b)）— 上表のゲートは severity で選ぶので confidence を見ない。**本体バッチ（並列）はそれで正しい**が、**追加バッチはこの層で唯一の直列 wave** なので、verdict がレポートに一切影響しない指摘に wave 1 本（実測 6.6 分）を使う経路になっていた:
  - `+15` は最良ケース（`confirmed` が「複数エージェント同一指摘 +15」の発火源）で、**それでも閾値に届かないなら 4 verdict すべてが no-op**
  - **本体バッチには適用しない**（閾値未満でも `🔁` 付録の取り下げ理由を埋めるので説明価値があり、並列なので wave コストがゼロ）
  - 対象 0 件なら起動しない。除外件数はレポートの反証行に出す（silent に落とさない）
  - **v2.62.0 の meta ゲート緩和（#123 C）で発火頻度が上がる側だった**ため、その後始末でもある
- **可変部の共通ブロックをファイル経由に変更**（`orchestration-guide.md ## 3.5` / issue #124 (c)）— §3.5 の対象表に「オーケストレーターが組む可変部の共通ブロック」が無く、体数ぶん手書きになっていた。実測では reviewer 5 + skeptic 1 + meta 1 + 反証 3 の**計 10 本に同一ブロックを繰り返し記述**しており、wave 間のメイン時間 ≈16.1 分（fleet の 26%）がここに効いていた。§3.5 自身の判断基準（複製係数 = 体数）に照らせば明確にパス渡し側なのに表から漏れていた:
  - `triage-signals.sh` の `## meta` が `agent_ctx_file=` を出し、オーケストレーターがそこへ 1 回書く（パス導出は `lib/review-paths.sh` の `agentctx`。式を複製しない）
  - **explorer の「確定事実」をこの共通ブロックに畳んだ** — 従来は「唯一の意図的なインライン例外」だったが、共有ファイルができたので例外でなくなった。10 行上限は**reviewer が読む量**を抑えるために維持
  - 掃除は `publish-review-event.sh` が `$DIFF_FILE` / `$PR_CTX_FILE` と同じ扱いで行う

### Added
- **origin 主張の base 検算をオーケストレーター側に追加**（`orchestration-guide.md ## 5` / issue #124 (d)）— reviewer は `prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」で縛られているのに、**レポート掲載前に origin を検算する規約がオーケストレーター側に無かった**:
  - 実測では冷や読み skeptic が「本 diff 由来の退行」と主張し、オーケストレーターがそれを支持してユーザーに伝えたあと、反証レイヤーが `refuted`(axis: pre-existing) で覆した。**`git show <base>:<file>` 1 コマンドで決まる事実**だった
  - **冷や読み skeptic は reviewer 側の base 確認規約を継承していない**（`prompts/recall-skeptic.md` が `reviewer-common.md` を参照するのは worktree セットアップと出力フォーマットの 2 点だけ）。v2.62.0 の上流ガードでは塞がらない層
  - **影響の非対称**: 反証レイヤーは effort ≥ high でしか走らないため、low / medium では誰も検算せず誤帰属がそのまま報告される。本検算は effort 非依存

### Fixed

**同版内のセルフレビュー（explorer 1 + reviewer 5）で初稿の欠陥 11 件を検出し、全件対処した。** 11 件中 6 件が「**正本を書き換えたが複製先に伝播していない**」型で、doc がそのまま実行手順になる本プラグインでは doc の consumer が他の doc であるため、コード変更より伝播先が見えにくいことの現れ:

- **`references/reviewer-prompts.md` が旧設計のまま**だった — 両 SKILL が「組み立て方の**正本**」と名指ししているファイルで、可変部テンプレは実値の直書きを指示し、確定事実を「**複製係数が体数ぶん立つ唯一の枠**」と断言していた（新 `## 3.5` と字義的に真逆）。共通ブロック方式へ同期
- **`orchestration-dynamic-rounds.md` の 4 箇所**が「PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}` 注入（必須）」のままだった。Round 2 / meta / skeptic / 反証の**実行手順の正本**なので、(c) が「reviewer wave では効くが動的ラウンドでは効かない」半端な状態になっていた
- **同ファイルの unmet 分類定義**が (a) の旧定義のままで、手順どおり動くと (a) が runtime で不発になった
- **`skills/review/SKILL.md` に旧「注入（必須）」ブレットが残り**、同じ箇条書き内で新ブレットと矛盾していた（self-review 側は削除済みで非対称）
- **`## meta` の説明と「パスを控えておく」指示に `agent_ctx_file=` が無かった** — 印字（Step 2）から Write（Step 5）まで数ステップ空くのに控える指示が無く、slug は不透明な cksum 値なので取り違えると復元できない
- **`Write` が `allowed-tools` に無かった**（skill / command 4 ファイルすべて）。(c) は Write を必須手順にしたのに宣言が無く、**施策が毎回 no-op になる**経路だった。`validate_plugin_quality.py` は「宣言したが本文で未使用」しか見ないため、逆方向は機械検出されない

**設計の核を壊していた 1 件**:

- **確定事実の「specialist・skeptic を除く」が消えていた**。共通ブロックに畳んだ結果、リポジトリ全体から除外記述が消え、skeptic にも届く形になっていた。`triage-dynamic-gates.md ## 8.5` の「findings 非注入がこのレイヤーの設計の核」と正面から矛盾する。**確定事実を共通ブロックから外し、reviewer 限定のインライン注入（10 行以内）に戻した** — 10 行上限で複製コストは既に抑えられており、false-negative hunter の独立性と引き換えにする価値がない

**条件式・参照先の穴 4 件**:

- **(b) が `{{SEVERITY_THRESHOLD}}` を見ていなかった**。報告マトリクスと `review_severity_threshold` は直列 2 段なので、`CRITICAL` 運用では MAJOR が conf 80 でゲートを通るのに全 verdict が no-op になり、塞ごうとした経路が残っていた。surface-aware 適用時の算術例（MAJOR conf 70 / CRITICAL conf 55）も併記
- **(d) の降格が no-op になる先を指していた** — 参照先の pre-existing 項は「reviewer が既に下げているので追加調整しない」で、申告の無い skeptic 指摘には何も起きない。`scoring-guide.md` に「**オーケストレーターの base 検算で pre-existing と判定した場合**」の項を新設して繋いだ
- **(a) の候補パス導出が未規定で「冪等」が未達**だった。`unmet_information` の target は散文でよい規約（実測 2 件も散文）なので、パスへの変換手順が無いとそこに推測が戻る。`main-root` の親を 1 回 `Glob` して当て、該当が無ければ 到達不能（掘り進めない）と規定
- **(d) の `git show` に base ref 解決のフォールバックが無かった**（`origin/<base>` → `<base>` の 2 段に。どちらも解決できなければ `base 検算: 未実行` を残す）

**その他**:

- `agentctx` に **stale 除去が無かった** — 他の一時ファイルは全て「配る前に消す」or「成功時のみ mv」を持つのに、agentctx だけ run 開始時に消す主体がおらず、publish に到達しない回（payload 検証失敗 / 途中中止 / python3 なし）の残骸を次回が「読めるが前回の値」として掴む経路があった。`triage-signals.sh` が配る直前に `rm -f` する
- **base 検算を `pre_adjust_counts` 記録の前に置いていた** — 降格が「調整で消えた分」の会計から抜け、(d) の効果を事後に測れなくなる。記録の後へ移動
- `## 3.5` の項目列挙に **`base ref` が欠落**し、**書き出しタイミングが未定義**だった（explorer 完了後にしか書けないのに「Step 2 の `## meta` が出すパスに書く」と読めた）。「explorer wave 回収後・reviewer 一括発行の直前に 1 回」「explorer プロンプトは対象外」を明記し、インライン許容の閾値（20 行）を確定事実の 10 行と別の数字にした

**取り下げた指摘 1 件**: 「SKILL が 500 行 warning を超えたまま（509 / 506）」は**全体行数と本文行数の取り違え**。`validate_plugin_quality.py` が見るのは frontmatter を除いた本文で、実測 492 / 491・skill-size warning は 0 件。

### 効果見込みと、変更しなかったもの

**(a) で直列 wave 5 → 4 本**（Round 2 の 3.6 分 + プロンプト構築分）。**(b) は実測ケースでは 0 本削減** — 対象 2 件はどちらも新ゲートを通る（`## 9` が「通る範囲は変えていない」と明記）ので、あれは**判定を式にして運任せを消した**ものであって、no-op バッチが将来発生したときの予防。(c) は wave 数ではなく wave 間のメイン時間に効く。

> issue #124 は「(a)(b) で 5 → 3 本」と見込んでいたが、**(b) のぶんは実測ケースからは導けない**（初稿でそのまま転記していたのを同版内のセルフレビューで訂正した）。次回の振り返りで「5→3 を期待したのに 4 だった＝施策が効いていない」と誤判定しないための記録。

**実測で妥当性が確認できたため変更していない設計**（over-correction 防止の記録）: 規模キャップ（effort `xhigh` の上限 6/10/6 に対し実際 2/5/0）/ explorer の費用対効果（7 分で確定事実 10 項目 → 後段 10 体の裏取りが効いた）/ `triage-guide.md ## 7`「体数を壁時計のレバーとして扱わない」（壁時計は wave 数が決め、体数は token 側を決めていた）/ 最小保証 2 体の固定費（`claude-md-compliance` は 40 tool_uses・12.8 分で MAJOR 0 件だったが、負の結果として価値がある）。

## [2.62.0] - 2026-08-13

`review:completed` の蓄積イベント **49 件（うち区間計測あり 22 件・反証 verdict 計 102 件）** を集計した振り返りに基づく改善（GitHub issue #123）。**計測して分かったことを計測基盤側に還す**版で、レビュー本体のアルゴリズムは変えていない。

### Added
- **降格される典型パターン 4 型**（`prompts/reviewer-common.md` / issue #123 A） — 反証 verdict の**過半が `severity_inflated`**（累計 102 件中 53 件 = 52%）で `refuted`（9%）を大きく上回る。下流で 52% を降格し続けるより **severity の定義を上流で精密にする**方が安い。base 由来 / 読み違え / 影響の過大見積もり / カテゴリの取り違え を判別基準の表にした:
  - **追加の検証手順ではない**（探索予算は据え置き）。手元の情報で**ラベルを選び直す**ための定義で、該当したら 1 段下げて理由欄に型名を書く。CLAUDE.md「Opus 5 で逆効果になる足場」の②（自分でダブルチェックさせる）を踏まないための線引き
  - 「迷ったら下げる」ではない旨を明記。4 型に当てはまらない指摘を予防的に下げると較正が逆方向に壊れる
  - **効果測定用に `adversarial_verify.calibration_schema` を新設**（1 = base 確認のみ / 2 = 4 型明示）。累計比率で読むと施策前サンプルに薄まるため層別が要る
- **`scripts/review-retro.sh`（振り返り集計 / issue #123 E）** — `triage-guide.md` / `triage-dynamic-gates.md` には各層の**ロールバック条件・再監視の条件**が随所に書いてあるのに、**判定するための集計手段が無かった**（本 issue 自体も jq を手で組んで書いた）。条件は比率と件数で決まる決定的な計算なので、LLM に毎回 jq を組ませずスクリプトへ閉じた:
  - 出力は effort × size_tier の fleet 時間・体数、体数 vs 壁時計の相関、検出 → 報告の歩留まり（schema 2 / 閾値別）、反証 verdict 分布（`calibration_schema` 層別）、動的層の発火率と skip 理由、計測マーカーの欠測率
  - **ロールバック条件・再監視条件に該当したときだけ ⚠️ シグナル行**を立てる（閾値とサンプル数下限はスクリプト側）。「サンプルが無いうちは判断しない」（`triage-guide.md ## 7`）を集計側でも守る
  - **publish の直後に毎回実行する**（`## 18`）。集計が「気が向いたときにやる作業」に落ちると条件判定が永久に走らないため
- **`scripts/detect-recent-review.sh`（skill 跨ぎの重複レビュー検出 / issue #123 D）** — `--focus` / `--exclude` は**同一 skill 内**の重複しか防げない。実測では self-review と PR レビューが同一 diff を 2 回舐め、互いを知らないまま同じ 3 件に独立到達していた:
  - 突合キーは **diff の内容ダイジェスト**（`diff_digest`）。HEAD SHA ではなく diff にしたのは self-review が未コミット変更を含むため。内容ベースなので publisher に依らず一致する
  - 検出時のみ **AskUserQuestion** で続行可否を確認する（review Step 2.4 / self-review Step 1.4。`--embed` ではスキップ）。**出力が空なら何も報告しない**（no-op を報告しない）
  - **前回の指摘本文は参照しない** — 判定材料を payload だけに限り、前回の結論に引きずられないようにする
- **`measurement_gaps` / `diff_digest` payload フィールド** — いずれも `publish-review-event.sh` が算出して注入する（SKILL からは渡さない）。前者は `duration_*` が `-1` になった理由を「打ち忘れ」と「該当なし」に分け、**欠測率そのものを計測対象**にする

### Changed
- **区間マーカーの打点規約を `mark wave` の 1 本に統一した**（issue #123 B） — `duration_synthesis_min` の保有率 **3/49**・`agents.explorer_waves` **2/49** と計測が機能していなかった。原因は打点のたびに `t1b`（explorer）と `t1c`（その他）を**判断させて**いたこと。「wave を回収したら `mark wave`、explorer wave なら `--explorer`」に一本化した:
  - **逆算による補完はしない。** publish 時刻から推定すれば欠測は消えるが、それは誤値であって計測ではない（`## 13.1` の「縮退先は欠測であって誤値ではない」と同じ原則）。欠測は `measurement_gaps` として可視化する側で扱う
  - **explorer 打点を synthesis 側に混ぜない**（スクリプトで分離）。混ぜると reviewer wave の打点を落としたときに「もっともらしい過大値」が出る
  - 旧キー（`mark t1b` / `mark t1c`）はエイリアスとして受理し続ける
- **meta-reviewer の起動ゲートを緩めた**（`gate_schema: 3` / issue #123 C） — 旧ゲートは高 severity の存在だけを条件にしており、**実測 xhigh 14 件中 `fired=1`**（skip 理由は全件 `no-high-severity`）とほぼ常時不発だった。「報告見込みの MAJOR が 3 件以上」を起動条件に追加した:
  - **緩めてよくなったのは v2.61.0 で wave コストが消えたから**（meta は反証と同一 wave）。増えるのは meta 1 体ぶんの token だけで、xhigh / max は明示 escalation なのでこの帯に限れば見合う
  - **effort ゲート（xhigh/max 起点）は据え置く。** 昇格の判断軸は価値率だが、`fired=1` では出せない。**まず起動サンプルを貯めるのが先**
  - **ロールバック条件つき**: `gate_schema >= 3` かつ `fired=true` が 10 件以上で `findings_added > 0` が 20% 未満なら層を畳む。判定は `review-retro.sh` が自動で出す
- **`review-timing.sh mark` が失敗しなくなった** — `start` 未実行・一時ファイル消失でもファイルを作り直し、stderr に警告を出して exit 0 で返す（issue 報告時に `mark t1b` が exit 1 で落ちていた）。マーカー 1 個の失敗でレビュー本体を止めない。`mark t2` 時に wave の打点が 1 つも無ければその場で警告する
- **payload テンプレートを両 SKILL から `orchestration-measurement.md ## 16` へ移した** — 「payload 契約の正本は `## 16`」と書きながら**テンプレート本体だけが SKILL 側に 2 つ**あり、フィールドを足すたびに 3 箇所を同時に直す形になっていた。移設で両 skill の差分（`pr` 固定値 / `head_verified` / `comment_polish` の 3 点）も 1 画面で見えるようになる。publish 直前に `## 16` を Read する既存手順のままで足りる

### Fixed

**同版内のセルフレビュー（reviewer 8 + 反証 3 + meta 1）で初稿の欠陥 12 件を検出し、全件対処した。** 「計測基盤を直す版で、その計測基盤の集計側に判断を誤らせる欠陥を入れていた」という構図だったので、以下は再発防止の記録でもある:

- **集計の母集団定義が節ごとにアドホックだった**（4 件が同根） — `review-retro.sh` に共通の層別を入れて解消:
  - **`layer_stats()` が版マーカーで層別していなかった**。`triage-dynamic-gates.md` は skeptic に `attribution_schema >= 2`、meta に `gate_schema >= 3` の絞り込みを**必須**と定め、「壊れた計測を根拠に不可逆な撤去をしない」とまで書いてあるのに、**そのロールバック判定を実装する側が絞り込みを落としていた**（同ファイル内で反証 verdict 側だけが `calibration_schema` で層別できていた非対称）
  - **meta シグナルの分母に「設計上 meta が起動しない帯」が入っていた**。既定 effort=high を 8 回回すだけで「1 度も起動していない」が必ず点灯する（反証層が 8 件投入して再現）。`skip_reason` が `effort` / `config` / `scope` / `emergency` の回は分母から外す
  - **相関の結論文が `r` の値に依らず固定だった**。「体数は壁時計のレバーではない」を無条件に印字しており、**このリポジトリの実データで `r = 0.877` の直後に出ていた**。`n < 10` は解釈しない / `|r| >= 0.6` は ⚠️ シグナルとして再監視条件に載せる、へ分岐化
  - **歩留まりの `schema != 2` が前方非互換だった**。次の版 bump でセクションが無音で消える。`>= 2` にして版ごとに層別表示する
- **「検出できなかった」と「該当なし」を同一出力に潰していた**（3 件が同根）。**この版の中核成果は `measurement_gaps` でまさにその区別をフィールド化したこと**なのに、同版で入れた consumer 2 本がその区別を捨てていた:
  - `--json` が「0 件」「ログ未存在」で **Markdown を返していた**（機械可読契約の破れ）。両経路とも JSON を返す
  - 明示指定した `--diff` の不在が silent だった（caller のバグと「重複なし」が区別できない）。**SKILL から `--diff` を落とし**（自力導出と等価で失敗モードごと消える）、明示指定時のみ WARN する
  - 突合キーを算出できなかった回に痕跡が無かった → `measurement_gaps` に `diff-digest` を追加。あわせて「欠測は gaps で見える」という**存在しない機構を指していたコメント**を実装に追随させた
- **`diff_digest` が review / self-review 間で一致しないのに doc が「publisher に依らず一致」と保証していた**。review は `gh pr diff`、self-review は `git diff BASE..HEAD` + `--cached` + unstaged の**3 本連結**で diff を作るため原理的に一致しない（反証層が実 PR で実測: `1462260100-1256` vs `2713407599-105966`）。**issue #123 D の動機シナリオがまさにこの経路**だったので、doc を実態に合わせるだけでなく**弱いキー `diff_files`（変更ファイルパス集合）を併設**して skill 跨ぎを拾えるようにした（弱いキーの一致は「重複の疑い」どまりと明示）
- **`except OSError` が `UnicodeDecodeError` を捕捉していなかった**（`ValueError` のサブクラス）。`readlines()` は全体を先にデコードするので、共有ログである `.claude/events.jsonl` に非 UTF-8 バイトが 1 つ混入すると新規 2 スクリプトが恒久クラッシュする。`errors="replace"` で、壊れた行だけが既存の `except ValueError` に落ちる設計どおりの縮退に戻した
- **空白を含むリポジトリパスで新規 2 スクリプトが機能停止していた**。パス集合を空白区切り文字列に畳んで未クォート展開しており、`review-retro.sh` は「計測データがまだ無い」と**事実に反する断定**を返していた（3 reviewer + 反証層が bash で end-to-end 再現）。配列 + `${ARR[@]+"${ARR[@]}"}` へ
- **`lib/review-paths.sh` の「この式を他所へ複製しないこと」に反する複製があった**。events.jsonl の場所導出 12 行が新規 2 本に逐語複製（`diff -u` で文字単位一致）。`review_event_logs()` / `review_diff_keys()` を lib に追加して 3 スクリプトから呼ぶ形に集約
- **`explorer_waves` の規約と計測意味論が矛盾していた**（meta-reviewer の指摘）。「explorer wave を回収したら `--explorer`」を普遍則としながら `>= 2` を「一括発行違反」と断定していたため、**xhigh/max で Round 2 の追加 explorer を起動すると規約どおりの動作が誤検知される**。`--explorer` は**初回 explorer wave 専用**と定義し、Round 2 の追加 explorer は `mark wave` で打つことを両 SKILL に明記
- **上流降格に透明性の記録が無かった**（反証層が refuted の副産物として発見）。下流（反証）降格には `🔁` 付録があるのに、今回追加した降格典型 4 型で `{{SEVERITY_THRESHOLD}}` を跨いだ降格は痕跡が残らない。`## below-threshold` に `demoted-across-threshold: <型名> N` を添える規約を追加
- **同梱シェルスクリプトに機械的検証ゲートが 1 つも無かった**（meta-reviewer の指摘。上記の複数件の共通原因）。`shellcheck` / `bash -n` / `py_compile` はリポジトリ全体でゼロヒットで、**420 行の bash + 埋め込み Python が構文検証を一度も経ずに配布される**状態だった。`validate_plugin_quality.py` に `check_shell_syntax`（`bash -n` / errors 扱い）を追加し、pre-commit と CI の両方で掛かるようにした
- **`orchestration-measurement.md` の目次に `## 19` が無かった**（`orchestration-guide.md` の索引は `## 18` / `## 19` の両方が漏れ）。冒頭の「レビュー本体の実行には不要」も `## 19` だけ例外である旨を明記

- **反証レイヤーの実測分布の記述を累計 n=102 に更新**（`triage-dynamic-gates.md ## 9` / `design-notes/scoring-rationale.md`）。あわせて **「この 52% を上流対策の効果測定に使わない」**旨と、v2.55.0 の上流ガードに版マーカーを付け忘れていた経緯（プロンプト変更はゲート変更ではないと読んだが、**計測値の意味は同じように変わる**）を根拠側に記録した
- `orchestration-measurement.md` の「`wave` は毎回追記して**よい**」を「追記**する**」に直した（v2.60.2 で `review-timing.sh` 側だけ直していた許可の含意が、正本側に残っていた）
- `review-timing.sh` のサブコマンド数の記述が 4 のままだった（実体は `waves` / `gaps` を含めて 6）

## [2.61.0] - 2026-08-13

`self-review` 1 件（`effort: xhigh` / `size_tier: large` / core 25 files・1694 lines / 全体 57 分・agent 18 体・約 335 万 tokens）の `review:completed` 実測に基づき、**breadth（体数）ではなく wave 数と重複探索**を削った版（GitHub issue #122）。検証層（反証 2 体が 5 件を severity 降格・1 件を refute / skeptic 単独由来 1 件 / meta 単独由来 1 件）は費用対効果が確認できたため削っていない。

### Added
- **`agents.explorer_waves`（`t1b` マーカーの行数）** — 「explorer は同一メッセージで一括発行する」規約（`orchestration-guide.md ## 0`）は v2.35.0 から正しく書かれていたが、**破ったときに計測へ現れない**ため事後に検知できなかった。実測では 1 体を単独発行してから残り 3 体を次のメッセージで出したため `duration_explore_min` が 18 分（7.7 + 9.2）— 一括なら wave 内最長の約 9 分で済んでいる:
  - **マーカー種別を増やさずに検知する**。`t1b` は「explorer 結果の回収直後」に打つ規約なので、wave ごとに打てば行数がそのまま wave 本数になる（`review-timing.sh waves`）。`durations` は最後の `t1b` を採るので `duration_explore_min` の意味は変わらない
  - 値の注入と WARN は `publish-review-event.sh` が行い、**SKILL 側は渡さない**（自己申告にすると系統的に「1」へ潰れる）。`>= 2` で「一括発行が破られた可能性」、`agents.explorer >= 1` かつ `0` で「マーカーの打ち忘れ」を stderr に出す
- **explorer の「確定事実」枠（`## 確定事実（explorer 共通・裏取り済み）`）** — 実測で**同じ事実に 5 体が独立到達**し（`next.config.ts` に `serverActions` が無く Next 既定の 1MB が効く）、5 体それぞれが同じ 2 ファイルを読み直していた。explorer 出力に `#### 確定事実`（最大 5 項目・`ファイル:行` 必須）を設け、統合したものを**全 reviewer に共通注入**する:
  - 複製係数が体数ぶん立つ**唯一の意図的な例外**なので、**合計 10 行以内**で殺す（超えるなら選択的注入に落とす）。消しているのは複製コストではなく reviewer 側の重複探索
  - reviewer 側は**裏取り済みとして扱い再確認の Read をしない**（「参考情報」だと結局各自が読み直し、複製コストだけ増える）。矛盾を観察したときだけ自分で Read して明記する
- **共通モジュール explorer 必須ルールの規模下限** — 実測では**型引数を 1 つ足しただけ（`+5 -2` 行）**の共通モジュール変更に explorer 1 体が 13.6 万 tokens・35 tool_uses を費やして「問題なし・後方互換」と結論していた。`importers ≤ 5` かつ後方互換な変更かつ他の explorer 条件に非該当なら reviewer の Read に委ねる（`triage-signals.sh` の `shared-module` 行に呼び出し元の概数を追加）。v2.12.0 の緩和意図は撤回せず、**波及先が数えられて少ない場合に限る**

### Fixed
- 上記 3 点をセルフレビューで検証し、初稿の不備を修正した（同版内で対応済み。以下は「入れた変更が意図どおり効かない」型で、実行時に落ちるものは無い）:
  - **`importers` の計数失敗が explorer 下限ゲートを fail-open させていた** — `wc -l` は上流が失敗しても数値を出すため `?` フォールバックが到達不能で、失敗が `0`（下限 `≤5` を最も緩く通す値）に潰れていた。`git grep` の終了ステータス（0/1 は正常・2 以上はエラー）で分岐するよう修正
  - **`git grep` の既定 pathspec が cwd だった** — `self-review` は worktree に入らず cwd がセッション起動ディレクトリのままなので、リポジトリルート以外から起動すると探索範囲が縮み、`$f`（repo ルート相対）との自己除外も効かなかった（実測: repo root 85 件 → サブディレクトリから 5 件）。`git -C "$WT" --full-name` で repo ルート基準に固定
  - **「過大見積もりだから安全側」は片側だけの断定だった** — 追跡済みファイルの literal 一致しか見ないので、未追跡ファイル・barrel / path alias 経由の import を取り逃して**過小にも振れる**。両方向を明記
  - **同一 wave 化の伝播漏れ 3 件** — 毎回読む正本 `orchestration-guide.md ## 0` が meta を「単体起動＝一括発行の対象外」と宣言したまま／meta を high 起点へ昇格させない根拠「直列 wave を 1 本足す」が 2 サイトに残存（`triage-dynamic-gates.md ## 8.5` / `triage-rationale.md`。**昇格の判断軸は wave コストではなく価値率に移った**旨を明記）／反証の体数上限「3 体・15 件」が 4 箇所で未更新（実効 4 体・20 件）
  - **参照・記述の誤り 4 件** — `triage-guide.md` の典拠が `## 7` を指していた（実体は self-review SKILL の規則）／両 SKILL の 5.8・4.8 冒頭と各フェーズのスキップ先ポインタが旧実行順のまま／`review-timing.sh` のヘッダが t1b にも「全 agent wave で打つ」と読める書き方だった／`README.md` の Phase 5.6 説明が単独ラウンド前提のまま

### Changed
- **meta-reviewer（5.6 / 4.6）と反証レイヤー（5.9 / 4.9）を同一 wave で一括発行**（実測で約 8 分の短縮 / `design-notes/pending-optimizations.md` に未実装案として置いていたものを実装）。両者は入力が同じ「reviewer の全指摘」で**互いの出力に依存しない**（meta は足す係・反証は較正する係）。冷や読み skeptic を reviewer wave に相乗りさせたのと同じ理屈:
  - **唯一の依存**（meta が足した指摘も反証対象）は **追加バッチ 1 体・上限 5 件**に閉じた。`[meta]` タグ付き指摘が反証ゲートに該当したときだけ直列で走り、0 件なら wave は増えない（期待値で削減）
  - 前提として**冷や読み skeptic の統合（5.8 / 4.8）をこの wave より前に済ませる**（skeptic の指摘を反証対象に含めるため。統合は agent を要さないメイン作業）
  - 見送っていた理由「xhigh/max でしか meta が走らないので既定 high では効果ゼロ」は据え置かない — **meta が走る帯は 1 wave の単価が最も高い帯**でもあるため
- `triage-guide.md ## 5.1` の wave 表・レポートの「直列 wave」行を `[meta+反証]` / `[追加反証]` に更新

## [2.60.2] - 2026-08-12

### Fixed
- **`review-timing.sh` の `t1c` 説明が「追記して**よい**」と許可を含意していた**。正本（`orchestration-dynamic-rounds.md`「回収したら毎回書くのが正しい運用」）は義務なので「追記**する**」に統一する。「1 回だけ書けば足りる」と読めると v2.60.1 で塞いだ打点漏れを再び誘発する
- `mark` 分岐のインラインコメントがヘッダ（15-16 行）と同内容を再掲していたので 1 行に圧縮（`durations` の後勝ちという非自明な事実は残す）

## [2.60.1] - 2026-08-12

v2.60.0 のセルフレビューで検出した **「正本を直したが消費サイトの片方が旧版のまま」型の同期漏れ**を全件閉じた版。挙動の追加・変更はなく、v2.60.0 が意図した挙動を実行経路に届かせる修正のみ（変更はすべて `*.md`）。

### Fixed
- **Round 2 の 3 分類が実行手順の正本に届いていなかった**（`orchestration-dynamic-rounds.md ## 6`）。手順 1.5 / 2 が「repo 内 / repo 外」の二分のままで、SKILL が「`## 6` の手順に従う」と指示する経路では**旧規範が勝ち、v2.60.0 の変更が構造的に不発**になっていた。3 分類とセッション到達可能 target のメイン照会経路を手順側に反映した
- **同じ 3 分類化が `self-review` に未適用だった**（Phase 4.5）。review 側だけ更新され、self-review はスキップ条件が旧語彙のまま・レポート雛形だけが `スキップ（unmet をメインで直接照会して解決）` を持つ自己矛盾状態だった
- **`mark t1c` の打点が一部の agent wave 回収点で欠けていた** — auto-retry（`orchestration-guide.md ## 5`）/ Round 2 / 反証レイヤー / 冷や読み skeptic の fallback 単独起動。打ち漏らすと欠測（`-1`）ではなく**そのフェーズの agent 稼働時間を丸ごと含んだ過大値**が出るため、誤りが誤りとして見えない。包括指示の射程を「すべての agent wave の回収点」へ広げ、各フェーズにも明示を足して 5.6 / 4.6 だけが特別扱いだった非対称を解消した
- **`t1c` がマーカー一覧から漏れていた**（両 SKILL Step 1 のコメント / `orchestration-measurement.md ## 13.1` / `## 14` の見出し）。レビュー開始時に最初に読む全体像なので、ここが 3 つのままだと後続の打点漏れを誘発する
- **「Phase 5.6 だけが規模帯に連動する」が過剰一般化だった**（`triage-dynamic-gates.md ## 8`）。Phase 5.5 は起動可否こそ帯非連動だが**段数は従来から帯連動**（`triage-guide.md ## 6.3` / `## 5.1`）で、断定のままだと `small` 帯 + xhigh で 2 段経路が選ばれ規模キャップ（explorer 0 体）を上書きしうる。射程を「起動可否が帯連動するのは 5.6 だけ」に限定し、effort 適応表にも 1 段圧縮の注記を足した
- **plugin.json / marketplace.json / INDEX.md の description が v2.60.0 の挙動変更と矛盾していた** — 「深さを担う層（… meta …）は規模で削らない」と「triage / explore / fleet / closing に分割」の 2 点。`validate-ssot.sh` は plugin.json ↔ marketplace.json の文字列一致しか見ないため、**両方が同じまま古くなるこのケースは機械検証を素通りする**
- **`triage-guide.md ## 8.5` / `## 9` への参照が壊れていた**（両 SKILL の計 4 箇所）。分冊時に `triage-dynamic-gates.md` へ移った節を旧パスのまま参照していた
- **記述精度**: v2.60.0 の Added に `prompts/focus/doc-substance.md` の変更を追記／`orchestration-measurement.md ## 16` の「skeptic は n=15」を正本（昇格 n=8・ロールバック判定 n=15）に訂正／`triage-rationale.md` の「全体 47 分」を「レポートまでの 47 分」と明示し、単位が復元できなかった `+ 529` を「リトライを含む」に置き換え

## [2.60.0] - 2026-08-12

`review` 実行 1 件（`size_tier: small` / `effort: xhigh` / 全体 58 分・レポートまで 47 分）の実測から、**壁時計の内訳が構造的に見えていなかった**問題に対処した版。`duration_fleet_min` 44 分のうち agent wave の実時間は約 24 分で、**残り約 20 分（46%）がオーケストレーター側**だったが、どの payload フィールドにも現れていなかった。支配的な区間が不可視だと「時間が長いから体数を減らす」という `## 7` が禁じている誤った打ち手に誘導される。

### Added
- **`duration_synthesis_min` と `t1c` マーカー** — 最後の agent wave を回収してからレポート出力までの区間。「回収済み ＝ 全 agent 終了済み」なので **agent 非稼働が構造的に保証される唯一の区間**で、オーケストレーター時間の**下限値**として読む:
  - `## 14` の「**マーカーを増やして測ろうとしないこと**」（v2.43.0）は **プロンプト組み立て時間の分離**についての結論であり、そこは正しい（書く行為＝ Agent call の発行なので分離不能）。**射程を「Agent call の前後に置くマーカー」に明確化**し、wave 回収後の区間は対象外であることを追記した。既存の結論は削っていない
  - `t1c` は **wave ごとに毎回追記する**（`durations` の awk が後勝ちで最後の値を採る）。動的ラウンドは起動可否が実行時に決まるため、「最後の wave の後だけ書く」規約にするとスキップ時に書き忘れて欠測になる
  - wave 間のプロンプト構築・分冊 Read は依然 wave 区間側に残るため**全量ではない**。`duration_fleet_min - duration_synthesis_min` が「agent wave + wave 間のメイン時間」
- **claim grounding に分類 ②' ツール検証可**（`prompts/reviewer-common.md`）— 「repo の外」と「確かめられない」は別のことなのに、旧 ③ が両方を飲み込んでいた。実測では **reviewer 3 体全員が外部 API のレスポンス形状を「未認証のため検証不能」として ③ に落としたが、オーケストレーターは同じ情報を数コールで取得できた**（結果は MAJOR → CRITICAL 昇格 1 件と偽陽性 1 件の除去）。**read-only・3 コール上限・書込禁止**の枠付きなので「探索を延長しない」原則は維持している。あわせて `prompts/focus/doc-substance.md` の A 軸 grounding にも ②' を反映した（doc が外部ツール / API の挙動を規定している場合は実照会する / 兄弟 doc 同士の整合だけで正誤を決めない / 二重定義は別途 MAJOR 相当）
- **`meta_reviewer.gate_schema`** — 下記のゲート変更に対する版マーカー。v2.59.0 で `## 16` に足した「**ゲートを動かす変更には必ず版マーカーを足す**」規約の初適用（`1` = 帯非連動 / `2` = 帯連動）
- **reviewer プロンプト可変部の予算**（`reviewer-prompts.md`）— 1 体 40 行以内・スロットを埋めるだけ。本文をパス渡しにしても、**可変部に散文で観点解説を書けば同じコストが `main.output`（単価最大）に戻る**。同じ読み替えを 2 回書いたらテンプレート側へ移す規約を明記

### Changed
- **meta-reviewer を `size_tier: small` かつ BLOCKER 不在でスキップ**（`skip_reason: "size-tier"`）。`## 6.3`「規模キャップが削るのは breadth だけ」に対する**唯一の例外**。実測 1 件で meta は **8.9 分（全体の約 2 割）を使って `findings_added: 0`**、同じレビューの反証レイヤーは 6.2 分で 6 件中 4 件を較正しており、同じ 1 wave の使い方として非対称だった。仮説は「`small` 帯は reviewer が 3 体まで絞られるので**探す相手そのものが小さい**」:
  - **⚠️ 根拠は n=1 で、このリポジトリの通常の基準を下回る**（skeptic 昇格は n=8 / 反証縮小は n=19）。v2.59.0 自身が「段階 2（帯連動ゲートの採否）はデータが貯まってから」と書いた箇所を**一部踏み越えている**
  - **ロールバック条件つきの暫定措置**。`small` 帯で meta を意図的に起動した対照実行 5 件のうち `findings_added > 0` が **1 件でもあれば即差し戻す**（recall を削る方向の変更なので疑わしければ戻す側に倒す）。差し戻し時も `gate_schema` は `1` に戻さず **`3` を新設**する（版は単調増加）。経緯と条件の正本は `design-notes/triage-rationale.md`
  - **BLOCKER があれば帯に関わらず起動する**（meta の役目は高リスク変更の盲点検出なので、最もリスクが高い経路は残す）。**他の depth 層（skeptic / 反証）へ横展開しないこと**
- **Round 2 のスキップ判定を「repo 外」から「到達不能」へ**（`triage-dynamic-gates.md ## 8`）。二分を 3 分類に分け、**セッションから MCP / CLI で届く外部状態は Round 2 を起動する前にメインコンテキストで直接照会して解決してよい**とした（wave を 1 本使わず受け渡しロスも無い）。旧分類では「外部サービスの実挙動」が全件 repo 外に落ち、**取れる情報を「構造的に空振り」と誤判定して wave ごと捨てていた**
- **Phase 0 の surface 判定で `triage-dynamic-gates.md` を Read しない**（`SKILL.md ## 3.4`）。ダイジェストの `## surface` を直接読む。オーケストレーターの分冊 Read は **diff サイズと無関係な固定費**なので、小さい PR ではこれが支配的になる

### Fixed
- **`SKILL.md ## 3.4` と分冊の矛盾**: SKILL 本文は surface 判定のために `triage-dynamic-gates.md ## 8.5` の Read を指示していたが、**分冊側の冒頭は「`triage-signals.sh` が機械適用済みなので Phase 0 の時点で本ファイルを読む必要はない」と明記**しており、SKILL 側だけが不要な Read を強制していた

## [2.59.0] - 2026-08-12

残っていた計測基盤の 4 件（#121 / #115 / #120 / #110）をまとめて閉じた版。いずれも**削減は生まないが、削減の可否を判断できるようにする**もの。

### Added
- **`meta_reviewer` payload フィールド**（`fired` / `skip_reason` / `findings_added`。GitHub issue #121 段階 1）。`recall_skeptic` には `fired` / `findings_added` があるのに **meta は人間向けレポート行だけで `.claude/events.jsonl` から集計する手段が無く**、価値率が出せないため `triage-guide.md ## 6.3` の「meta-reviewer は帯に関わらず削らない」判断を再評価できなかった（`## 7` の「サンプルが無いうちは判断しない」に従うと永久に判断不能）:
  - 由来タグ **`[meta]` / `[meta:dup]`** をレポート契約に追加（`[recall-skeptic]` と同型）。タグを落とすと publish 時点で由来を再構成できず `findings_added` が記憶依存で 0 へ潰れる
  - **`findings_added` は meta の価値を捉えきらない**ことをフィールド定義に明記した。meta は「単独起動されなかった観点を自分で当たって『指摘なし』と閉じる」価値も出すが、それはこの数値に現れない。**価値率が低くても機械値だけで撤去判断をしない**
  - 段階 2（帯連動ゲートの採否）はデータが貯まってから。本版では**判断していない**
- **`recall_skeptic.gate_schema`**（GitHub issue #115）。`## 8.5` の監視クエリ①（「昇格後は `skip_reason="effort"` が消えるはず」）は、**昇格前のサンプルが永久に残るため常に「信号あり」を返し、本物の実装バグを検知できない**状態だった。`attribution_schema`（由来タグの版）は gate の版を識別しないため、publisher 自己申告の版マーカーを別に持たせた。監視クエリ①に `gate_schema >= 2` の絞り込みを入れた
  - **一般化して `## 16` の共通ルールに 1 行足した**: 「**ゲートを動かす変更には必ず版マーカーを足す**」。effort ゲート・起動条件・算出方法を変えると**フィールドの有無は変わらないのに意味が変わる**ため、「フィールドの有無で層別する」規約だけでは新旧を区別できない。今後 meta-reviewer や反証のゲートを動かすときも同じ穴に落ちる
- **反証 verdict 分布の偏り検知**（GitHub issue #110）。`X >= 5` かつ単一 verdict が実施件数の **80% 以上**なら、反証行の次行に注記を 1 行出す（`※ severity-inflated が 7/8（88%）と偏っています。降格の妥当性を検算する価値があります`）:
  - `## 10` 手順 2 のバッチ切り分けは**バッチ内汚染**を防ぐが、**プロンプト自体が特定 verdict へバイアスした場合は検知できない**（実測: 2 バッチが独立に `severity-inflated` 7/8）
  - **偏り = 誤りではない**。実測ケースは Playwright の実幅計測や mutation test を伴い質は高かった。注記は「検算する価値がある」までで、**自動で verdict を覆さない**
  - `X < 5` では注記しない（少数では偏りが偶然で起きやすく常時ノイズになる）。判定はメインコンテキストで数えるだけで agent の追加起動は不要

### Changed
- **`recall_skeptic` の価値率が既知の過少計上を含むことを `design-notes/triage-rationale.md` に記録**（GitHub issue #120）。dup を分子に入れない判断自体は妥当なので変えないが、**二値でしか見ていないため「独立到達かつ根拠・修正案が上位互換だった」ケースが 0 に計上される**（実測: dup 判定の skeptic 版だけが修正案の核を持ち、最終レポートに採用されたのにその回の `findings_added` は 0）:
  - **第 3 のタグは増やさない判断**。上位互換かどうかの判定に主観が入り、`findings_added` の機械的な明快さを損なう副作用の方が大きい
  - 歪みは**実態より低く出る方向にのみ**効くので、`## 8.5` のロールバック判断では **閾値を下回ったときだけ**レポート本文の確認を要する（上回ったなら追加確認は不要）と非対称に規定した
- `agents` の除外規定を「meta / skeptic は専用フィールドで観測する」に更新（`agents` は体数上限の効果測定用で、1 体固定の検証層を混ぜると上限との対応が崩れる）
- 両 SKILL の payload テンプレートに `pre_adjust_counts.schema` / `severity_threshold` / `gate_schema` / `meta_reviewer` を反映（v2.58.0 で `## 16` に定義した 2 つがテンプレート未反映だった）

## [2.58.1] - 2026-08-12

### Changed
- `triage-signals.sh` の lockfile コメントを self-review の `--base` 経路にも合う表現に直し、言い換えの重複を削った（quality-check セルフレビューのコメント推敲提案）

## [2.58.0] - 2026-08-12

`/quality-check` のセルフレビューが v2.53.0〜2.57.0 に対して出した指摘（BLOCKER 1 / MAJOR 7 + マトリクス外 8）を全件修正した版。**自分で入れた計測・注入の 3 つが、いずれも「欠測ではなく誤値」に倒れていた。**

### Fixed
- **取り込み内訳が `attachment` 経由を分母から落としており、Agent 占有が系統的に過大だった**（#118 の修正が別の誤配分を作っていた）。`type: "attachment"` のエントリ（hook stdout の注入・skill/agent listing・編集ファイルのスニペット）も同じくコンテキストに入るのに `tool_result` しか数えていなかった。実測で attachment は tool_result 合計の 0.6〜2.0 倍あり、**同一セッションで Agent 占有が 33.9% → 21.9% に是正**された。注入本文のフィールドは type ごとに異なるため allowlist（`content` / `stdout` / `stderr` / `snippet` / `addedLines` / `addedBlocks`）で拾い、どれも無いときだけ全体長にフォールバックする（黙って 0 にしない）
  - あわせて「`main.cache_write` はこれと参照 doc の合算」という断定を撤回した。**表の合計は cache_write の 1 割前後**にすぎず（大半はターンごとに再キャッシュされるプロンプト前半）、`Read` は既に表の中にあるので名指しも誤っていた。「取り込み全体に占める比率」に言い直し、**表は cache_write の分解ではない**（桁が合わないのが正常）と明記
  - **`cache_read` は「前後比較には使わない」から「単価は低いが総量は最大になりやすい。往復削減の効果はここに出る」に訂正**。`prompts/reviewer-common.md` 自身が「サブエージェント側のコストの 45% が `cache_read`」を根拠にツール使用規約を定めており、往復削減という主要な改善軸の効果が計測の読み方から丸ごと落ちていた
- **`main-root` の導出が誤値に倒れうる 2 経路を塞いだ**（#113 の対策が無シグナルで無効化される穴）。`--git-common-dir` の親は「メイン作業ツリー」ではなく、**submodule では `<super>/.git/modules`**（`.git` 内部）を、`--separate-git-dir` では gitdir 置き場の親を指す。さらに GCD が空のとき無警告で `pwd`（= review では worktree 側）に縮退していた:
  - 導出を `lib/review-paths.sh` の **`review_main_root()`（`git worktree list --porcelain` の 1 行目）に一本化**した。linked worktree からもメイン側を返すことを実測で確認済み。3 箇所に散っていた式の複製もこれで解消
  - **導出失敗時の縮退は「空」であって `pwd` ではない**。`main-root` 行ごと出力せず stderr に WARN を出す。orchestration-guide `## 1.1` にも「行が無ければ `{{MAIN_ROOT}}` を注入しない」を規定し、`prompts/reviewer-common.md` 側にも「未置換なら本節を適用しない」ガードを置いた（誤値を注入するより注入しない方が安全側）
- **`dep-dir` が symlink を辿ってリポジトリ外を「読んでよい依存 dir」として広告していた**（CWE-59）。対象名は全て gitignore 慣例名で実体が無いのが普通なため、同名 symlink がコミットされていても気づかれにくい。`[ -L ]` で除外し、実体が `main-root` 配下に収まることも `pwd -P` の prefix 一致で確認する。**反証レイヤーは「PR 由来の symlink は main clone に着地しない」（review は worktree 側に checkout する）を実測で示して BLOCKER → MINOR 相当と判定したが、欠陥自体は本物**なので塞いだ
- **`pre_adjust_counts` の算出方法が v2.54.0 で非可換に変わったのに層別できなかった**。フィールドの有無は変わらないため「フィールドの有無で層別する」という自リポジトリの規約下では新旧を区別する手段が存在しなかった:
  - **`pre_adjust_counts.schema`（欠落 = 1 / v2.54.0 以降 = 2）と `severity_threshold` を payload に追加**。schema 2 は `## below-threshold` 由来ぶんが **dedup されない**（reviewer 横断の生合計）ので、schema 1 と同じ列で比較すると重複計上で効果が過大に出る。監視 jq と版マーカー一覧も同時に更新した
  - `## below-threshold` の書式を **severity ごとの複数行に一般化**（`review_severity_threshold = "CRITICAL"` 運用では MAJOR も抑制対象になるのに `MINOR:` 1 行しか例示が無く、入れ先が未定義だった）。両 SKILL の集計手順も「**同名 severity のバケツへ**足す」と具体化
- **`{{SEVERITY_THRESHOLD}}`（両 skill 共通）が「review のみ」の `## 1` 配下にあり self-review 経路から辿れなかった**。独立節 `## 2` に格上げし、`## 0` の skill 差分表に `{{MAIN_ROOT}}` と `{{SEVERITY_THRESHOLD}}` の行を追加した。`## 1` 用の rationale ポインタが `## 1.2` 配下に取り残されていたのも戻した
- **`orchestration-dynamic-rounds.md` の 4 起動点（Round 2 / meta / skeptic fallback / 反証）に注入指示が反映されていなかった**。**Round 2 は #113 が塞ごうとした「依存が読めず検証不能」が最も起きる場所そのもの**で、ここで `{{MAIN_ROOT}}` が未置換だと再起動 reviewer が `ls {{MAIN_ROOT}}/...` をリテラル実行して失敗する
- **doc の版ラベルが実バージョンと不一致**（`v2.56.0` → `v2.57.0`。`triage-dynamic-gates.md` / `triage-rationale.md`）。**CHANGELOG の「両 SKILL に注入指示を置いた」も誤り**で、実際は review のみ（同エントリ末尾の「self-review は注入不要」と矛盾していた）。`triage-rationale.md` の母数矛盾（「有効な 13 件」と「13 件中 1 件欠測」の併存）も「取得を試みた 14 件のうち有効 13 件」に明確化した
- **実測値（`severity_inflated` 60% / `refuted` 6%）の 6 サイトへの複製をやめた**。実行時プロンプト（`reviewer-common.md` / `adversarial-verify.md`）と `scoring-guide.md` は**規範の記述**（「較正が主機能」）だけを持ち、比率は `design-notes/scoring-rationale.md` 1 箇所 + ポインタに集約する。n が増えるたび 6 箇所を同期する運用は機械検証もできず、既に版ラベルで同期漏れが 1 件出ていた
- `HEAD 検証:` 行の必須指示が新設節の配下に押し出されていたため、`### HEAD 検証結果の申告（worktree 起動時は必須）` の見出しを与えて所属を明示した

### Changed
- **`## below-threshold` が CLAUDE.md「Opus 5 足場③」に反する方向であることを `design-notes/scoring-rationale.md` に明記**した。**効果測定の盲点**（閾値を知った reviewer が *そもそも形成しなくなった* MINOR は `pre_adjust_counts` に現れない = この施策で最も起きやすい劣化が計測の死角に入る）と、切り分け方法（`review_severity_threshold = "MINOR"` の対照サンプル）、撤去条件を併せて記録した
- ルート CLAUDE.md のバージョニング規約に **bump 種別の判定基準**を追記（`docs` commit で変更が `*.md` + version/CHANGELOG のみなら PATCH。MINOR は `plugin-manager:update-all` の利用者に誤ったシグナルを送る）

## [2.57.0] - 2026-08-12

蓄積した `review:completed` で**保留していた 2 つの監視項目を判定して閉じた**版。どちらも実装は変えず、結論と根拠を doc に確定させる。

### Changed
- **v2.41.0 の反証レイヤー縮小（バッチ化 + effort 引き下げ）を「維持」で確定した**（GitHub issue #119。`triage-dynamic-gates.md ## 9`）。ロールバック条件が要求していた 2 指標が n=19 / 計 67 verdict で出そろい、どちらの戻し条件にも該当しなかった:
  - **`uncertain` 0 件（0%）** → effort を `max` に戻す根拠なし。判定を避けているのではなく**判定できている**と読む（プロンプトは根拠を出せない場合に `uncertain` を選ぶよう指示しており、実測 1 件では 9 件すべてに `file:line` 付き根拠が返っていた）
  - **`refuted` 4 件（6%）** → バッチサイズを 5 → 3 に下げる根拠なし
  - **再監視の条件を残した**: 反証プロンプト・ゲート・バッチサイズを変えたときは `uncertain` が 0 のままかを再確認する（この判定は現行の 3 つの組み合わせに対するもの）
  - **`orchestration-guide.md ## 5` の注記は閉じていない**（issue の指示どおり）。「不変条件（高 severity 非削除）を緩めるときは反証 effort を `max` に戻すか同時に判断する」は verdict 分布とは**独立の条件**なので、本判定に巻き込まない
- **`## 7`「体数削減が壁時計に効いた証拠は現時点で存在しない」を実測に置き換えた**（GitHub issue #116）。証拠が貯まり、**体数と `duration_fleet_min` は無相関で effort（= 直列 wave 数）が支配的**と示された。`size_tier` を medium に揃えて層別すると high 平均 32 分（n=4）/ xhigh 平均 61 分（n=6）と **1.9 倍**なのに体数レンジは 6〜10 と 6〜11 でほぼ重なり、`73 分 / 6 体` と `19 分 / 7 体` が併存する。**この記録の用途は「体数を削って時間を稼ごうとする誤った最適化を防ぐ」こと**:
  - 未確定として残した点も併記した（`design-notes/triage-rationale.md`）: ①13 件中 1 件が `duration_fleet_min: -1` で、並行セッション汚染（#99）かマーカー欠落か判別できない（**「体数が多いと測定不能」と読まないこと**）②上表は medium 帯のみで、wave 構成が変わる small / large に外挿できない
  - **本記録をもって帯連動ゲート（medium 以下では meta-reviewer をスキップ）を入れないこと**を明記した。meta-reviewer の収量が payload に無く価値率を出せないため判断材料が足りない（計測を足す議論は GitHub issue #121 に分離済み）

## [2.56.0] - 2026-08-12

### Fixed
- **`## 17` の `main.cache_write` が「参照 doc の読み込み」を測れていなかった**（GitHub issue #118）。doc はこの値で分冊・遅延読み込みの効果を判定するよう案内していたが、**参照 doc の読み込みと agent 出力の取り込みが同じバケツに入る**ため、fleet が大きい review では後者が支配的になりうる。**分冊を進めても値が下がらない / 体数が増えると値が上がる**という交絡した数字で判断してしまう状態だった（実測: agent 13 体で `main.cache_write` 1,501.9k、内訳は分離不能）:
  - **`measure-tokens.sh` に「取り込み内訳」を追加**して交絡を実際に分解できるようにした。main transcript の `tool_result` を **経由ツール別に集計**するので、`Agent` 経由の占有と `Read`（参照 doc）の占有が並んで出る。doc に注記を足すだけでは「どちらが支配的か」を毎回判断できないため、道具側で答えを出す
  - **文字数で出し、トークン換算をしない**。換算係数が内容種別（コード / 散文 / 日本語）で変わるため、係数を掛けた値は「もっともらしい誤差」を持ち込む。**経由別の比率**として読むよう出力とガイドの両方に明記した
  - `--since` を取り込み内訳にも効かせた（usage 表だけ絞られて内訳が全期間のままだと、区間比較で桁が合わない）
  - `## 17` の表で `main.cache_write` の定義を「参照 doc の読み込み **+ agent 出力の取り込み**」に訂正し、分冊の効果を見る確実な方法を 2 つ提示した（**`main.output` を一次指標にする** / **agent を起動しない経路で測る**）
  - **「同じ PR / 同じ diff で比較する」だけでは交絡は消えない**点を明記。体数は effort と規模キャップで変わるため、**effort を変える A/B ではこの交絡が直接効く**（v2.51.0 の `reviewer_effort_profile` A/B がまさにこの用途）
  - 検討して**採らなかった案**: 各サブエージェントの最終メッセージの `output_tokens` を「main への戻り値」として推定する方法。実データで検証したところ最終 usage メッセージが 1 token のサンプルがあり（全 output 4,295 に対して）、**推定が大きく外れる**ため破棄した。壊れた計測を直す変更で別の壊れた計測を入れない

## [2.55.0] - 2026-08-12

### Changed
- **severity 付与の前に base 状態（pre-existing / intended）を確認する手順を置いた**（GitHub issue #114）。反証レイヤーの verdict を全期間集計すると `severity_inflated` が **60%**（40/67）で `refuted` は 6% しかなく、過大評価が主要な失敗モードだった。`prompts/reviewer-common.md` には「退行指摘の invariant 検算」があるが **severity 付与の前段に置かれていない**ため、影響を先に見積もってから base を見る順序になっていた:
  - **追加コストゼロの判定を先に置いた**。issue の提案は指摘ごとに `git show <base>:<file>` / `git blame` を回す形だったが、それでは探索予算を圧迫する。**①指摘対象の行が diff の追加行にあるか**（`$DIFF_FILE` は手元にあるので探索ゼロ）→ 無ければ既存の除外対象ルールに合流、**②PR 説明・コミットメッセージが意図と説明しているか**（`$PR_CTX_FILE` は既読）→ intended として 1 段階降格、の順で判定し、**`git blame` の 1 往復は「行は触っているが不備は PR 前から同じ」と主張する場合だけ**に絞った
  - **pre-existing は「降格」ではなく「除外」になる場合がある**点を明示した。PR が触れていない不備は既存の除外対象ルール（「今回の変更で導入されたものではない既存の問題」）どおり報告しない。降格するのは PR がその行を触っている場合だけ
  - **二重降格を塞いだ**（`scoring-guide.md`「severity 調整ルール」）。reviewer が pre-existing / intended で 1 段下げた指摘に対し、反証レイヤーが同じ軸で `severity-inflated` を返しても追加調整しない。判別は理由欄の記載で行う（退行 invariant 検算の既存ガードと同じ方式）。同じ軸を 2 回引くと過小評価になる
- **反証レイヤーの位置づけを実測に合わせて書き換えた**（`triage-dynamic-gates.md ## 9` / `prompts/adversarial-verify.md` / 両 SKILL）。「偽陽性（false positive）を独立に潰す鏡像」→「独立読み直しで **severity を較正し、偽陽性を摘出する**」。`refuted` が 6% しかない以上、旧記述は期待と実挙動がずれており、反証エージェント側も「潰す」方に引っ張られる。**層の価値を否定するデータではない**（実測 1 件では 9 件中 6 件を降格して報告を 1 件に絞れている）
  - **上流ガードの根拠が n=1 である点を `design-notes/scoring-rationale.md` に明記した**。軸別の内訳（pre-existing 1 / intended 2 / misread 1 / 影響過大 2）は payload に無くレポート本文から手で数えた値で、集計値（n=19）とは信頼度が別。そのため**入れたのは prompt の手順追加という可逆な変更だけ**にし、`severity-inflated` の降格規則そのもの（不可逆側）は触っていない。効果の確認方法（反証の `severity_inflated` 比率が下がるはず / 下がらなければ主因は base 以外）も併記した

## [2.54.0] - 2026-08-12

### Changed
- **reviewer に実効報告閾値を伝え、閾値未満の列挙をやめさせた**（GitHub issue #117）。報告マトリクスと userConfig `review_severity_threshold`（既定 `MAJOR`）は**直列に掛かる 2 段のフィルタ**だが、reviewer は後段を知らされていなかったため、構造的にほぼ報告されない severity に出力予算を使い続けていた。実測（`pre_adjust_counts` を持つ 6 サンプル）では MINOR が調整前 60 件 → 報告 9 件の **85% 破棄**で、うち confidence 95+ が 7 件 — **報告マトリクスは通過したのに閾値で全滅**しており、reviewer の calibration ではなく構造の問題だった:
  - `{{SEVERITY_THRESHOLD}}` を reviewer プロンプトに注入する（`{{PR_NUMBER}}` / `{{MAIN_ROOT}}` と同じプレースホルダ方式）。規約の正本は `prompts/reviewer-common.md`「実効報告閾値」、注入規約は `orchestration-guide.md ## 1.2`
  - 閾値未満と判定した指摘は**本文を書かず `## below-threshold` に件数だけ**返す。**0 件でもブロックを省かない**（「観点が死んだ」と「該当なし」を 0 に潰さない）
  - **採ったのは issue の案 A**（reviewer に抑制させる）。案 B（MINOR を折りたたみ付録として出す）は main 出力が増えて削減目的に逆行するため見送った。ただし A の素朴な適用（MINOR を完全に禁止）は **severity 判定が MAJOR 側へ歪む**ため、**「判定はする・列挙だけしない」**形に限定した:
    - 「閾値未満だから」を理由にした severity の繰り上げを**明示的に禁止**（繰り上げれば報告に載るが、それは発見ではなく較正の破壊）。迷ったら本来の severity で数に入れる
    - `{{SEVERITY_THRESHOLD}}` が `MINOR` のとき、および**未注入のとき**は列挙を抑制しない（未注入を「抑制してよい」と読み替えると silent に指摘が消える）
  - **`pre_adjust_counts` は `## below-threshold` の件数を足して求める** よう規約を更新（`orchestration-measurement.md ## 16` / 両 SKILL のスコアリング手順 6）。足さないと「reviewer が検出しなかった」と「閾値未満なので列挙しなかった」が 0 に潰れ、**本施策の効果測定と再評価の根拠（この issue を起票できた計測そのもの）が同時に失われる**
  - **閾値の対象外**を明示: `## unmet_information` / `## related-observations`（`FYI:` 含む）/ `[surface:high-risk]` フラグ / self-review の B 系統 `## コメント推敲提案`（severity を持たない別枠経路。`review_severity_threshold` が効かないのは従来どおり）

## [2.53.0] - 2026-08-12

### Added
- **agent worktree に依存パッケージが無く、ディスク上の事実が「検証不能」に落ちていた問題を塞いだ**（GitHub issue #113）。`isolation: "worktree"` の子 worktree は gitignore 対象の `node_modules` / `vendor` / `.venv` を持たないため、依存の実装を読めば確定できる事実を agent が `unmet_information` として申告していた。実測では初回 wave で 3 件が「検証不能」になり、**Round 2 で全件解決して MAJOR 1 件がそこで初めて出た** — wave 1 本（約 10 分）を、最初からディスク上にあった事実の回収に費やしていた。Round 2 は effort / userConfig でスキップされうるため既定パスの保険にならない:
  - `triage-signals.sh` に **`## host-deps` セクション**を追加。`main-root`（`--git-common-dir` 由来のメインリポジトリ絶対パス）/ `dep-dir`（メイン側に実在する依存 dir）/ `lockfile-changed`（PR が lockfile を変更しているか）を機械的に出す。**LLM にパス組み立ても lockfile 判定もさせない**
  - `prompts/reviewer-common.md` / `prompts/explorer-common.md` に `{{MAIN_ROOT}}` プレースホルダと「**『依存を読めないので検証不能』と申告する前に必ずここを試す**」の指示を追加（`{{PR_NUMBER}}` / `{{HEAD_SHA}}` と同じ方式）
  - `orchestration-guide.md ## 1.1` を新設し、注入を **`## 1` の PR 番号・HEAD SHA と同格の必須項目**として規定。`review` SKILL の explorer 起動（Step 4）・reviewer 起動（Step 5）の両方に注入指示を置いた（self-review は下記のとおり注入不要）
  - **`{{MAIN_ROOT}}` は「依存を読むための逃げ道」であって、レビュー対象を読む場所ではない**点を prompt / guide の両方に明記した。メイン側はユーザーの作業ツリーで PR と無関係な未コミット変更を含みうるため、そこからレビュー対象コードを読むと偽陽性になる（#56 で checkout 指示を入れた理由と同型の罠を、逆向きに作らないため）
  - **lockfile を変更する PR ではメイン側の依存が PR 後の状態と一致しない**。`lockfile-changed` が出ている場合は根拠にする際に「メイン側の依存で確認（PR 後の状態とは異なる可能性）」と明記し confidence を下げるよう規定した（「読めた」と「PR 後の状態を読めた」を同一視しない）
  - self-review は `isolation: "worktree"` を使わない（依存はそのまま読める）ため**注入不要**。prompt 側にもスキップ可と明記

## [2.52.1] - 2026-08-12

### Fixed
- **`measure-tokens.sh` が worktree 内から main transcript を解決できず、review 経路では引数なし実行が必ず FATAL で落ちていた**（GitHub issue #112）。transcript の slug は**セッションを開始した**ディレクトリ由来だが、探索側は `ROOT=$(pwd)` で cwd 由来の slug しか見ていなかった。review skill は Step 0 で必ず `EnterWorktree` するため、実行時の cwd（worktree 側）の slug 配下にメインループの transcript は存在しない:
  - issue #104 の対応は**サブエージェント側の glob 化のみ**で、main transcript の入口は cwd 由来のまま残っていた。結果として sub は解決できるのに main で先に落ちる状態だった
  - **cwd 側とメインリポジトリ側（`--git-common-dir` 由来）の両方を候補**にし、横断で最も新しい `.jsonl` を採る。実行中のセッションの transcript が最新であることを使う。**どちらかに決め打ちすると片方で必ず欠測する** — dev-workflow の作業用 worktree 内で開始したセッションは逆に cwd 側にあるため
  - `ls -t` には候補ディレクトリ横断で全件を渡す（ディレクトリごとに `head -1` すると候補間の順序が失われる）
  - 導出は `publish-review-event.sh` / `lib/review-paths.sh` と同じ `--git-common-dir` 手法。**`GCD` が空のとき `cd "$GCD/.."` を実行しない**分岐も踏襲した（`/` に降りる）
  - 見つからないときの FATAL と `--list` は**探索したディレクトリを全件表示**する（ユーザーが `--session` に渡すパスを自力で探さずに済む）
  - `orchestration-measurement.md ## 17` に worktree 経路の注記を追加。「引数なし実行」を第一の用途として書いている doc とスクリプトの前提の食い違いを解消した

## [2.52.0] - 2026-08-07

冷や読み skeptic を **high 起点に昇格**した版。`triage-dynamic-gates.md ## 8.5` が自ら定めていた昇格基準を、蓄積した `review:completed` が両方とも満たしたため。

### Changed
- **冷や読み skeptic（Phase 5.8 / 4.8）の effort ゲートを `xhigh / max 起点` → `high 起点` に昇格**（`triage-dynamic-gates.md ## 8.5` + `orchestration-guide.md ## 5` の層別テーブル + 両 SKILL のスキップ条件）。5 リポジトリ横断の `review:completed` **50 件**（`attribution_schema >= 2` は 33 件）を集計した結果:
  - **需要**: surface=true 24 件のうち **15 件（63%）が `skip_reason="effort"` で未起動**。基準の「継続的に発生」を満たす
  - **価値**: `fired=true` 8 件のうち **4 件（50%）が `findings_added > 0`**。基準の「明確に非ゼロ」を満たす
  - **待機のコスト**: 価値率 50% が正しいなら、effort skip した 15 件で**約 7〜8 件の fleet 共通盲点を取り逃していた**計算になる
  - **昇格コストが小さい**: skeptic は v2.41.0 で reviewer wave への相乗りになっており、**直列 wave を増やさない**（壁時計への影響は wave 内最長を更新したときだけ）。増えるのは opus 1 体ぶんのトークンで、しかも surface=true のときだけ
  - **meta-reviewer は xhigh/max 起点のまま据え置いた**。meta は reviewer 全結果に依存するため相乗りできず**直列 wave を 1 本足す**。壁時計が wave 数に支配される以上、skeptic と同じ扱いにはできない
  - 以前 design-notes に記録していた「`fired=true` 4 件すべてが `findings_added=0` だが、価値ゼロと帰属の喪失を区別できない」は、**schema 2 のサンプルで決着した** — 帰属が壊れていただけで実際には半分が盲点を破っていた。**壊れた計測を根拠に撤去しなくて正解だった事例**として design-notes に残した
- **`## 8.5` の「high 昇格の判断基準（計測後）」を「昇格後の監視とロールバック条件」に差し替えた**。昇格判断が n=8 の価値率 50% だったことを踏まえ、**戻す条件を先に決めてある**: `fired=true` かつ `attribution_schema >= 2` が **15 件貯まった時点で価値率が 25% を下回ったら** high をスキップに戻す（n を倍にしても半分を切るなら昇格根拠が崩れたとみなす）。あわせて「実装が効いているか」の確認 jq（昇格後は `skip_reason="effort"` が消えるはず。消えなければ SKILL 側の更新漏れの信号）も置いた

## [2.51.0] - 2026-08-07

### Added
- **reviewer effort profile の A/B スイッチ**（userConfig `reviewer_effort_profile`、既定 `uniform`）。「Opus 5 の素性能なら低密度観点は `medium` でも recall が落ちないのでは」という仮説を計測で検証するための実験フラグ:
  - `differentiated` を指定すると **high 帯に限り**低密度観点（comment-accuracy / pattern-consistency / config / dependency / type-design / ui-quality / cross-cutting / doc-substance / test-quality / api-design）の reviewer を `medium` で起動する。高密度観点（bug-detection / security / spec-compliance / claude-md-compliance / error-handling / migration / performance）・specialist・最小保証 2 体は `high` 維持。**xhigh/max は明示 escalation なので profile を無視**して全 reviewer を `xhigh` のまま。検証層（meta / skeptic / 反証）と explorer は対象外
  - effort が cache（コスト全体の 83%）ではなく output/thinking（~17%）側に効くため**節約は modest** と分かったうえで、recall を落とさず取れる分だけ取る位置づけ。マップの正本は `triage-guide.md` `## 7.1`
  - `review:completed` payload に `reviewer_effort_profile` を追加（A/B の arm を層別する暫定フィールド。存在が v2.51.0 マーカー）。**同一 PR で uniform / differentiated を流し、blocker+critical recall が落ちないことを必要条件に採否を判定する** A/B 手順・判定基準・結論後の撤去条件を `design-notes/pending-optimizations.md` `## 5` に記載
  - 既定 `uniform` は現行挙動と完全一致（下流に影響なし）

## [2.50.2] - 2026-08-07

### Changed
- **`scripts/triage-signals.sh` の issue-ids 抽出が大文字限定である意図をコメントで明示**（GitHub issue #107）。`grep -oE '[A-Z]+-[0-9]+'` は Linear の慣例（大文字 Issue ID）に合わせた意図的な絞り込みで、ignore-case にすると `utf-8` / `sha-1` / `base-64` 等がブランチ名から誤マッチする。小文字 ID の backend を追加するときの見直しポイントも併記した（コードの挙動は不変）。

## [2.50.1] - 2026-08-07

### Fixed
- **反証 `severity-inflated` による MAJOR/MINOR 降格が silent に脱落していた**（GitHub issue #109）。`refuted` で取り下げた MAJOR/MINOR は取り下げ理由を「🔁 反証で取り下げた指摘」付録に記録していたのに対し、`severity-inflated` で 1 段階降格した結果 `review_severity_threshold`（既定 MAJOR）を割って脱落する指摘は**どこにも記録されず**、レビュアーが「なぜ消えたか」を追えなかった。反証由来の脱落 2 経路で透明性が食い違っていた:
  - `scoring-guide.md`「反証レイヤーの verdict 反映」の `severity-inflated` MAJOR/MINOR 行に、降格で報告閾値を割って脱落する場合は `refuted` と同じく 🔁 付録へ記録する規約を追加（verdict 種別・軸名・反証 file:line を含める）
  - 両 SKILL のスコアリング手順 4 と「🔁 反証で取り下げた指摘」セクションの条件を「`refuted` 専用」から「反証で報告閾値を割った MAJOR/MINOR 全般（`refuted` の −40 と `severity-inflated` の降格の両方）」へ拡張。付録の取り下げ理由行に verdict 種別を明示させ、2 経路を区別可能にした
  - 高 severity（BLOCKER/CRITICAL）は従来どおり降格で消さず係争注記付きで本文に残す不変条件は不変（付録にも出さない）。本修正はレポート出力のみの変更で wave / 体数を増やさない

## [2.50.0] - 2026-08-07

### Added
- **`scripts/cleanup-agent-worktrees.sh`**（GitHub issue #105）。agent は `isolation: "worktree"` で起動するため体数ぶんの worktree がレビュー用 worktree の配下に残り、**その状態では締めフローの `ExitWorktree(remove)` が state 検証に失敗して worktree を畳めない**（実測で 13〜23 個が残留、`agent-*` ブランチは 45 本まで蓄積していた）:
  - **原因はプラグイン自身にある**。Agent tool の worktree は「変更が無ければ自動削除」される仕様だが、`prompts/reviewer-common.md` の必須セットアップ（`git fetch origin refs/pull/N/head` + `git checkout --detach FETCH_HEAD`）が作業ツリーを丸ごと入れ替えるため対象外になる。detach をやめれば自動削除に任せられるが、それは issue #98 で「子 agent が base branch を読む」偽陽性を潰すために入れた機構なので戻せない。残留を作っているのがプラグインである以上プラグインが片付ける（判断の詳細と却下した代替案: `design-notes/orchestration-rationale.md`）
  - **削除は 3 条件をすべて満たすものだけ**: ①現在の worktree の配下 ②未コミット変更なし ③自分自身ではない。並行する別レビューや開発用 worktree には触れない
  - **メインリポジトリ上では実行を拒否する**（`--git-dir` と `--git-common-dir` の一致で検出）。そこで「配下の worktree」を対象にするとレビュー用 worktree 自体と開発用 worktree を巻き込むため
  - `agent-*` ブランチは「どの worktree にも checkout されていない」ものだけ削除する（生きた worktree のブランチは保護される）。agent はコミットしないのでブランチが指すのは PR head そのもので、削除で失われるコミットは無い
  - `--dry-run` で対象の列挙のみも可能。**件数は必ず報告する**（silent skip で「片付いたつもり」を作らない）
  - review SKILL の締めフローに 5 として挿入し、以降を 1 つ繰り下げた（ExitWorktree は 6、teardown 案内は 7）

### Changed
- **未実装の最適化案を `design-notes/pending-optimizations.md` に記録**。meta-reviewer と反証の並列化（直列 wave −1）/ main 側のツール呼び出しバッチ化 / `reviewer-common.md` の圧縮 / explorer wave の廃止 の 4 件について、見積もり・トレードオフ・「今は採らない理由」・判断に必要な計測を残した。あわせて v2.49.0 の agent ツール規約を入れる**前**の実測値（23 体・バッチ率 1.00・Read 範囲指定率 16%・`cd` 始まり 61%）を基準値として記録し、次の実 review と比較できるようにした

## [2.49.0] - 2026-08-07

実 PR に review を走らせたフィードバック（GitHub issue #104 / #106）への対応と、そのセッションの
transcript を分解して分かった**サブエージェント側のコスト構造**への打ち手。

### Fixed
- **`measure-tokens.sh` が review skill では常に `sub: 0` になっていた**（GitHub issue #104）。`review` は Step 0 で `EnterWorktree` するため、セッションが **2 つの project slug に割れる** — メインループは元リポジトリ側の slug に、サブエージェントは worktree パス由来の slug に格納される。スクリプトは前者しか走査していなかった。**v2.48.1 の修正は self-review（`EnterWorktree` を使わない）でしか検証しておらず、review 経路が未検証だった**:
  - **session-id は全 slug を通じて一意**なので、`~/.claude/projects/*/<session-id>/subagents/` と slug をまたいで引き当てる形に変更した。`--claude-worktrees-*` という命名規則に依存しないので、`EnterWorktree` の実装が変わっても効く
  - 実機の 42 slug で確認: 同一 session-id がメイン側（`tool-results` のみ）と worktree 側（`subagents/`）に分かれている。修正前は 0 体だった実セッションで 23 体を正しく集計できるようになった
  - 警告文の「CC 側の格納場所が変わった可能性がある」は本経路を想定しておらず誤った切り分けに誘導するため、実在確認のコマンドを示す文言に変えた
- **skill frontmatter の `effort` と実行時 `${CLAUDE_EFFORT}` の二層構造が読み取りにくい**（GitHub issue #106）。frontmatter は skill を開けば真っ先に目に入るが、それが**オーケストレーター専用**で reviewer にも動的ラウンドにも効かないことは orchestration-guide まで辿らないと分からず、「high 運用のつもりが xhigh で meta-reviewer・skeptic・反証拡大が全部走った」という取り違えが起きていた。**規模キャップが先に効くケースでは体数が変わらないぶん気づきにくい**:
  - 両 SKILL の「前提」節に二層構造を明記（self-review には「前提」節が無かったので新設）
  - Step 7 / Step 6 レポートの「実効上限」行に「実行時 effort が reviewer と動的ラウンドを支配する」注記を追加

### Changed
- **agent 側にツール使用の規約を追加**（`prompts/reviewer-common.md` / `prompts/explorer-common.md`）。issue #104 のセッション（23 体）の transcript を分解したところ、**サブエージェント側コストの 45% が `cache_read`**（= 往復回数 × その時点のコンテキスト量）で、往復が減ればトークンと壁時計の両方に効くことが分かった。実測に基づく 4 項目:
  - **独立したツール呼び出しは 1 メッセージにまとめる**。実測では **558 回のツール呼び出しが 100% 単発**（1 メッセージ 1 件）で、往復ごとに文脈全体が読み直されていた。オーケストレーター側には「同一メッセージ内で一括発行」を課していたのに、agent 側には何も書いていなかった
  - **`Read` は範囲を指定する**。実測では **84% が範囲指定なしの全文 Read**。500 行超は `Grep` で当たりを付けて `offset` / `limit` で読む
  - **探索は `Grep` / `Glob` ツールを優先し `Bash` の `grep` / `find` を使わない**
  - **`Bash` は絶対パスを使い先頭に `cd` を付けない**。実測では **Bash 297 回のうち 181 回（61%）が `cd` 始まり**で、複合コマンド中の `cd` はパーミッション確認を誘発しうる
- **探索予算に「読む量」の上限を追加**（同）。従来は「diff 外の追加 Read は 10 ファイルまで」とファイル数しか縛っておらず、大きいファイルを 10 個読めば数十万トークンになる。実測では **1 体あたり 334k tokens を新規に読み込んでいた**

## [2.48.2] - 2026-08-07

### Fixed
- **PR ブランチ名がシェル行に補間される経路を塞いだ**（`scripts/detect-dev-worktree.sh` + review SKILL 締めフロー 6）。ブランチ名は PR 作者が完全に制御する外部入力で、git の ref 名規則は `$` / バッククォート / `;` / `|` を禁じていない（`feat/$(...)` は有効な ref 名）。SKILL 本文が `detect-dev-worktree.sh "<PR ブランチ名>"` と書いて LLM に実値を埋めさせる形だったため、その文字列がレビュアーのシェルで評価されうる状態だった。**この構造は v2.46.0 より前から存在し（self-review の反証レイヤーが pre-existing と判定）本改修が導入したものではない**が、スクリプト化で公開契約として再固定するタイミングなので塞いだ:
  - スクリプトを `--pr <N>` 受けに変更し、ブランチ名の取得を内部の `gh pr view` に閉じた。**LLM が触るのは数値だけ**になる（`--pr` は数値のみ受理）
  - `--branch <name>` も残すが、SKILL からは使わない。比較は `awk -v` + 文字列等価でシェル再評価を経ない
  - 検証: `--pr 'x$(touch /tmp/PWNED)'` は exit 2 で弾かれ、`--branch 'feat/$(touch ...)'` でもファイルは作られないことを確認
- **担当ファイル名のクォート規約を agent 側に明記**（`prompts/reviewer-common.md` / `prompts/explorer-common.md`）。`diff-slice.sh` に渡すパスはレビュー対象由来＝信頼できない入力なので、シングルクォートで囲むよう指示した（ダブルクォートだと `$(...)` が評価される）
- **`detect-dev-worktree.sh` のマーカー判定に frontend を追加**。`envs/.backend.env.worktree` のみを見ており、frontend だけの worktree で検出漏れになっていた（`dev-workflow` の cleanup-checklist は両方を条件にしている）

### Added
- **削減効果の実トークン実測を `design-notes/orchestration-rationale.md` に記録**。同一指示の subagent 2 体に旧セット / 新セットを Read させ、transcript の `usage` から比較した（fleet を回さず、変えた変数だけを分離できる）。**doc がコンテキストに積む実トークンは 135,433 → 75,342（−44.4%）**、Read 呼び出しは 9 → 5 回。あわせて **`bytes/3` の概算が絶対値を約 25% 過小評価する**ことが判明したので、実測係数 ≒ 0.44 tokens/byte を記録した（従来 CHANGELOG に書いてきた「103.5k → 54.9k」は削減率としては妥当だが絶対値は低め）

## [2.48.1] - 2026-08-07

v2.46.0〜v2.48.0 の再編を `/self-review`（explorer 2 + reviewer 6 + specialist 2 + 反証 1）にかけて見つかった**自分で入れた退行**を潰した版。反証レイヤーが BLOCKER 2 件を pre-existing / 環境依存として却下したので、確定した分だけを直している。

### Fixed
- **publish の payload が複数行で `events.jsonl` の JSON Lines を壊していた**（`scripts/publish-review-event.sh`）。両 SKILL のテンプレートは整形済みの複数行 JSON で、`event_bus_publish` は `printf '...%s\n'` で 1 行 1 イベントとして追記するため、**1 イベントが 4〜6 物理行に割れ、どの行も単独ではパース不能**になっていた。`json.load` は改行を空白として受理するので、直前に足した妥当性検証がこの破壊だけをすり抜けていた（再現確認: 4 行 / 4 行ともパース失敗）。subscriber は `issue-workflow:issue-maintain`:
  - sed によるテキスト合成（`duration_*` 除去 → `{` 直後へ注入 → カンマ正規化）を**廃止し、python3 で parse → update → 再シリアライズ**に置き換えた。`separators=(",",":")` で改行が構造的に混入しない
  - これで同時に消えた 2 つの欠陥: ①除去 sed が値を整数リテラル前提で見ており、`"duration_min": 42`（コロン後に空白）や `null` が漏れると重複キーの**後勝ちで注入値が負ける** ②カンマ正規化 sed が JSON の**文字列値の中身まで書き換える**（`"x,,y"` → `"x,y"`）
  - `python3` を**必須依存に格上げ**（`command -v` での条件付きスキップをやめた）。「壊れた 1 行が集計を壊す」ための検証が、python3 不在で黙って無効化されていた
- **`size_tier` の帯判定が triage-guide `## 6.2` の定義と逆だった**（`scripts/triage-signals.sh`）。`else if (cf<=10 || cl<=500) medium` は「ファイル > 10 **または** 行数 > 500 なら large」を満たさず、**`15 files/50 lines` や `12 files/100 lines` が medium に落ちて規模キャップで fleet が無言で半減**していた（ガイドが large の worked example に挙げる `2 files/600 lines` も medium）。large → medium → small の順判定に修正。あわせて `CLASSIFIED` が空のときは `size_tier=unknown` + `numstat=failed` を出す（取得失敗を「変更 0 件」と同じ small に潰さない）
- **`diff-slice.sh` が空出力 + exit 0 でレビュー対象を無言で落としていた**。パス抽出が `diff --git` の `$4` だったため、**スペース入りパスと rename（`{old => new}`）で必ず取りこぼす**うえ、0 件マッチを成功として返すので reviewer は「担当ファイルに変更なし」と解釈していた（`reviewer-common.md` の「切り出しに失敗したら明記する」ガードが空出力を失敗と判別できない）:
  - パス抽出を `+++ b/<path>` 行（行末までが 1 パス）ベースに変更し、`/dev/null` 側は `--- a/<path>` で補う
  - **マッチ 0 件は `exit 3` + stderr の WARN** にした。スペース入り・rename・0 件の 3 ケースで再現確認済み
- **`measure-tokens.sh` がサブエージェントを 1 つも数えていなかった**。`isSidechain` は top-level transcript では常に `false` で、サブエージェントは `<slug>/<session-id>/subagents/agent-*.jsonl` という別階層にある。**`sub` 行が常に 0 になるため、プロンプト複製の削減で main → sub へ移動しただけのコストまで「削減」に見える**（削減幅の系統的な過大評価）:
  - 集計対象を `subagents/*.jsonl` に拡張し、main / sub の判定を**ファイルの所在**に変更（実測でこのセッションの sub = 11 体 / output 516k / cache_write 4,682k を計上できるようになった）
  - slug 導出を `sed 's#/#-#g'` → `s#[^a-zA-Z0-9]#-#g` に修正（`.claude/worktrees/` 配下＝ **review が実際に走る場所**で必ず不一致になっていた）
  - sub が 0 件のときに自己診断メッセージを出す（前提が壊れたときに黙って 0 を返さない）
- **diff 取得に失敗すると前回実行の古い diff を再利用していた**（`scripts/triage-signals.sh`）。「成功時のみ `mv`」は空ファイル対策であって stale 対策ではなく、`$OUT` に前回の中身が残っていると `[ ! -s ]` を通過して `exit 0` していた。取得前に `rm -f "$OUT"` し、`gh pr diff` / `git diff` の終了ステータスを直接ゲートにした
- **`base..HEAD` の失敗が握り潰されていた**（同上）。`{ A; B; C; } > out && mv` はブレースグループの終了ステータスが**最後のコマンド**のものになるため、base ref が解決できず 1 本目が fatal でも未コミット分だけで成功扱いになり、**コミット済みの変更が丸ごと欠落したまま完走**していた。`git rev-parse --verify` で先に解決を確認し、3 系統を個別に検査する
- **`prompts/session-context.md` の規約が誰にも届かなくなっていた**。中身がオーケストレーター向けの「プロンプト末尾に本文を展開せよ」テンプレートのままで、パス渡しに切り替えた後は orchestrator も agent も読まない孤立 doc になり、**「意図的な設計判断は confidence −30」が消えていた**。reviewer 向けの指示に書き換え、両 SKILL の「必ず Read させる」リストに条件付きで追加した
- **`${CLAUDE_PLUGIN_ROOT}` が子 agent の環境に存在しない**ため、プロンプトテンプレート内の `${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh` が解決できず、diff の切り出しが失敗して**全文 Read にフォールバック**していた（対策 2 の効果が消える）。テンプレートを `{{PLUGIN_ROOT}}` プレースホルダに変え、両 SKILL の「可変部」に実パスの明記を必須項目として追加
- **`angles.md` が high 既定では誰にも渡らなかった**。Read 条件が「冗長ペア時」で、冗長ペアの実起動は xhigh/max 専用のため、「ペアを削った代償を angle 内挿で補う」という縮小の前提が空振りしていた。条件を「ペア条件が成立したとき（high 以下の内挿を含む）」に変更
- **分割による参照の張り替え漏れ 21 箇所**。`reviewer-prompts.md ## 6 / ## 8 / ## 2` など旧構造を指す参照が残っていた。**v2.47.0 の「全参照を張り替えた」は誤り**で、検証スクリプトが書き換えスクリプトと**同じ正規表現の盲点**（`` `file.md ## N` `` のようにバックティックが filename の前に来る形）を持っていたため 0 件と報告していた
- **`xargs -n1 dirname` が `it's.ts` のようなパスで `unterminated quote` を起こし、`## agents-md` セクションが途中で落ちていた**（`triage-signals.sh`）。while ループに置換
- **`wc -l < "$f"` を `-f` チェックより前に実行していた**（同上）。レビュー対象が `evil.js -> /dev/zero` のような symlink を含むとハングする。順序を入れ替えた
- **`review-timing.sh` が未知引数を黙殺していた**。`--PR` のような綴り違いで `start` と `mark` が別ファイルを掴み、計測が全欠測になる経路があった。`exit 2` に変更し、`--pr` の値も数値のみ受理する
- **`python3` が未宣言の必須依存だった**（`_requirements` / `check-deps.sh`）。jq で直したのと同じ穴を同じ改修で作っていた
- **`fetch-pr-context.sh --save` の PR 番号が位置依存**で、`--save 123` の順で呼ぶと保存先が `-pr--save` になり削除側と食い違っていた。`--save` 除去後の第 1 引数から取るよう修正。あわせて `bash "$0"` の自己再実行を `${BASH_SOURCE[0]}` 基準に変え、空配列展開を bash 3.2 でも落ちない形にした

### Changed
- **一時ファイルのパス導出を `scripts/lib/review-paths.sh` に集約**。同じ式が 4 スクリプト + ガイドのスニペットに散っており、`fetch-pr-context.sh` だけ空値ハンドリングが違う（`-pr${1:-0}` vs `${PR:+-pr$PR}`）という乖離が既に発生していた。あわせて**一時ファイルを `$TMPDIR/claude-code-review-<uid>/`（0700 / umask 077）に閉じ込めた** — `$TMPDIR` 直下に 0644 の固定名で置くと、`TMPDIR` 未設定の環境（Linux / CI の多く）で world-writable な `/tmp` に落ち、symlink 先置きによる上書きと未コミットコードの読み取りが成立する
- **`## files` セクションに 80 件の上限**（`triage-signals.sh`）。ファイル数に比例して伸びる唯一のセクションで、800 ファイルの PR ではここだけで約 19k tokens に達し「ダイジェストを compact に保つ」目的を打ち消していた。超過分は件数のみ表示し、全件は `diff-slice.sh --list` で取る
- **`## hunks` から funcname コンテキストを落とした**（同上）。`@@ -a,b +c,d @@ <直前の行の実内容>` の形式なので、`API_KEY=...` のような代入行が stdout に載りうる（再現確認済み）。範囲情報だけを出す
- `prompts/focus/*.md` 15 ファイルの冒頭から移行残骸（「現行 #N から移行。」）を削除。分割で「reviewer が最初に読む行」に昇格したが、`#N` を解決できる doc は現存しない

## [2.48.0] - 2026-08-06

SKILL 本文の bash をスクリプトへ切り出し（**LLM に手続きを書かせるのをやめる**）、これまで一度も測っていなかった**トークン消費を実測できる**ようにした版。

### Added
- **`scripts/measure-tokens.sh`**: セッションの transcript からトークン消費を集計する。`review:completed` payload は所要時間しか持たず、トークンは skill 実行中に自己観測できないため、**事後に transcript から取る**のが唯一の手段。Claude Code の transcript（`~/.claude/projects/<slug>/*.jsonl`）は各アシスタントメッセージに `usage` を持ち、`isSidechain` でメインループとサブエージェントを分離できる:
  - `main.output`（オーケストレーターが**書いた**量。プロンプト複製の効果はここ・単価最大）/ `main.cache_write`（**新規に読んだ**量。参照 doc 分冊の効果はここ）/ `sub.*`（サブエージェント側）を分けて出す
  - `cache_read` は再利用ぶんで単価が低いため**前後比較の指標には使わない**旨を出力に明記
  - `--list` / `--since` でセッションと時間窓を選べる（1 セッションで複数レビューを回した場合の切り出し用）
  - 仕様は orchestration-measurement.md `## 17`。**v2.46.0 / v2.47.0 の削減効果はバイト数からの概算のままで、実測はこれから**
- **`scripts/review-timing.sh`**: 区間マーカー（`start` / `mark t1|t1b|t2` / `durations` / `cleanup`）。`TS_FILE` のパス導出（worktree ルート + PR 番号での並行セッション分離）を 1 箇所に閉じた
- **`scripts/publish-review-event.sh`**: `review:completed` の publish。書込先のメインリポジトリ固定・所要時間の算出と注入・一時ファイルの掃除をまとめて担当する
- **`scripts/detect-dev-worktree.sh`**: PR ブランチを保持する開発用 worktree の検出（パス除外 + worktree-setup マーカーの 2 条件）
- **`fetch-pr-context.sh --save`**: 出力をファイルへ原子的に保存してパスを stdout に出すモード

### Changed
- **SKILL 本文の bash をスクリプト呼び出しに置換**（両 SKILL）。残る bash はほぼ 1 行呼び出しだけになった。**トークン削減は SKILL.md で約 1.3k と見込みより小さかった**（本文の大半は bash ではなく手順の散文だったため）が、副次的な効果の方が大きい:
  - **LLM が毎回 30 行の bash を書き下ろす**必要がなくなった（転記ミスの余地が消える）
  - **所要時間の算出を LLM にさせない**。`duration_*` は payload で渡さず、スクリプトが計測ファイルから注入する
  - **publish 前に payload の JSON 妥当性を検証**するようになった。不正なら publish せず `FATAL:` で落ちる（**壊れた 1 行は events.jsonl 全体の集計を壊す**ため、これは実質的なバグ修正）
- orchestration-measurement.md `## 13` / `## 13.1` / `## 14` の bash を**仕様の記述に置き換え**、実装はスクリプトが正本であることを明記した（二重管理の解消）

### Fixed
- **`jq` が未宣言の必須依存だった**。`fetch-pr-context.sh` は `require_cmd jq` で必須としているのに `_requirements` にも `check-deps.sh` にも無く、**未導入環境では review Step 1 が理由不明で落ちる**状態だった。両方に追加した（SSoT 検証で対応が担保される）
- **品質検証器が publisher を見失う穴を塞いだ**（`.claude-plugin/scripts/validate_plugin_quality.py`）。`EVENT_PUBLISHER_GLOBS` が `*/skills/**` `*/commands/*` `*/hooks/scripts/*` だけを見ていたため、**publish 処理をプラグイン同梱スクリプトへ切り出すと publisher が検出できなくなり**「表に載っているが publish されていない」の偽陽性が 3 件出た（本改修で実際に踏んだ）。`*/scripts/*.sh` を走査対象に追加した

## [2.47.0] - 2026-08-06

v2.46.0 の続き。残っていたオーケストレーター側の読み込みコストを、**規範と根拠の分離**（実行時に読むのは「何をせよ」だけ）と**遅延読み込み**（条件付きフェーズのガイドはそのフェーズが走ると決まってから読む）で削った版。仕様・閾値・判定ロジックは変えていない。

### Changed
- **ガイドを利用タイミング別に分冊**（`orchestration-guide.md` 554 行 → 170 行 / `triage-guide.md` 566 行 → 348 行）。従来はどちらも実行手順の冒頭で全文を読んでいたが、内容の大半は条件付きフェーズ用で、既定 effort ではスキップされるフェーズの手順まで毎回読み込んでいた:
  - `orchestration-dynamic-rounds.md`（`## 6` Round 2 / `## 7` meta-reviewer / `## 9` skeptic / `## 10` 反証）— いずれかを**実行すると決まってから** Read
  - `orchestration-measurement.md`（`## 13` publish 先固定 / `## 13.1` `TS_FILE` パス / `## 14` 区間計測 / `## 16` payload 契約）— **publish の直前**に Read
  - `orchestration-optional-flows.md`（`## 2` Issue 必読 / `## 11` Vault / `## 12` 訂正の伝播前ガード / `## 15` embed JSON）— 各フローの**適用条件を満たしたとき**だけ
  - `triage-dynamic-gates.md`（`## 8` 動的ラウンド / `## 8.5` skeptic / `## 9` 反証の起動ゲート）— **起動可否を判断する段**で Read。Phase 0 の構成決定には不要（surface 判定は `triage-signals.sh` の `## surface` が機械適用済み）
  - **節番号は分割前のものを維持**（外部からの参照を切らないため）。他ファイルの節を指すときはファイル名を前置する規約にし、全参照を張り替えた
  - 各分冊と両ガイド冒頭に「いつ Read するか」の表を置き、両 SKILL.md の実行手順冒頭にも同じ表を追加した（**Read 指示を書き換えないと分割の効果が出ない**ため）
- **規範と根拠を分離し、根拠を `references/design-notes/` へ退避**。実測値・失敗の履歴・却下した代替案・判断待ちの観測ログは、**Opus 5 が規範に従うためには不要**（規則があれば従える）だが**将来の編集者が規範を壊さないためには必要**。読者が違うのでファイルと読み込みタイミングを分けた:
  - `orchestration-rationale.md`: 並列発行の 3.5 倍実測（#95）/ ブランチ名 checkout が構造的に必ず失敗する経緯（#98 / #69）/ HEAD 検証行を必須にした理由 / ファイル経由渡しの実測（#100 A）/ reviewer effort を `xhigh`→`high` に下げた根拠と層別の切り分け / 観点カバレッジ検算の前倒し（v2.39.0）
  - `triage-rationale.md`: 規模キャップの実測（17 体 / 130 分・#96）/ wave 可視化の理由（#100 B）/ 縮小のロールバック条件と監視 jq / 「体数を壁時計のレバーとして扱わない」の全文 / **未解決の観測（review 経路の MAJOR がゼロに張り付いている）**
  - `scoring-rationale.md`: 2 軸が必要な理由 / `severity-inflated` の穴（v2.41.0 で塞いだ）/ パネル運用の将来拡張
  - `pr-context-format.md`: `fetch-pr-context.sh` の出力フォーマット（オーケストレーターは知る必要がない）
  - **根拠を消したのではなく移した。** ガイド本体には「→ 根拠: `design-notes/...`」のリンクを残し、**将来の編集を縛る制約だけは本体に残した**（例: 反証 effort の引き下げが scoring-guide の不変条件に依存している点 / 「時間が長いから体数を減らす」をロールバック判断に混ぜない点 / `pre_adjust_counts` が貯まるまで scoring 規約を変えない点）
  - `design-notes/README.md` に読者と読むタイミングを明記し、**規範を変更する PR では対応する design-note も同時更新する**ことを規約化した

### 効果

オーケストレーターが常時読み込む参照ドキュメントは **103.5k → 55.6k tokens**（v2.46.0 のプロンプト分割ぶんを含む）。条件付きの分冊（動的ラウンド 4.2k / 起動ゲート 7.8k / 任意フロー 3.4k）はスキップされれば読まない。

**残る最大項は SKILL.md 本体（18.7k / 536 行）** で、常時読み込みの中で最大になった。bash ブロックのスクリプト化が次の打ち手（`skill-size` warning も 500 行超で出ている）。

## [2.46.0] - 2026-08-06

トークン消費の残る 2 大要因（**プロンプトテンプレートの体数ぶん複製**と **diff の (1+N) 重複**）を、v2.43.0 で PR コンテキストにだけ適用していた「ファイル経由渡し」（issue #100 A）の横展開で塞いだ版。メインコンテキストは **diff 全文もプロンプト本文も一度も載せない**。

### Changed
- **プロンプトテンプレートをパス渡しに変更**（`references/prompts/` 新設 + 両 SKILL の explorer / reviewer 起動手順）。オーケストレーターがテンプレート本文をプロンプトへ転記していたため、**同一テキストを起動体数ぶん出力していた**。共通指示だけで約 7.3k tokens あり、6 体構成では約 44k tokens の出力複製になっていた（出力トークンは単価が最も高い）:
  - `reviewer-prompts.md`（1,142 行）と `explorer-prompts.md`（240 行）を **1 観点 1 ファイル**に分割し `references/prompts/` へ移設。`reviewer-common.md` / `focus/<focus>.md` / `specialist/<key>.md` / `explorer-common.md` / `explorer/<focus>.md` / `meta-reviewer.md` / `adversarial-verify.md` / `recall-skeptic.md` / `angles.md` / `bundle-rules.md` / `session-context.md` / `pr-context-rules.md`
  - 旧 2 ファイルは**索引**として残す（`## 1`〜`## 8` の旧節番号 → 新パスの対応表 + プロンプトの組み立て方）。他プラグインからの参照（`guardrail-protect` §5 等）を切らないため
  - **オーケストレーターはテンプレートを Read しない**。agent プロンプトは「Read させるパスの列挙 + 可変部（PR 番号 / 期待 HEAD SHA / diff パス / 担当ファイル / 各種パス / explorer 結果）」だけで構成する。1 体あたり約 9k tokens → 約 0.4k tokens
  - agent が Read を怠った場合は既存の出力形式検証（orchestration-guide `## 5`）が `### レビュー結果` 見出し・`[confidence:]` タグ・`HEAD 検証:` 行の欠落として検出し 1 回だけ auto-retry する（新しい検知機構を足していない）
  - **分割は機械的に行い本文は改変していない**（85,559 → 84,754 bytes。差分は節区切りの `---` と索引へ移した intro のみ）。内部の節番号相互参照（`## 3` の Focus テンプレート等）だけをファイルパス参照に書き換えた
- **diff をパス渡しに変更**（両 SKILL + orchestration-guide `## 3.5` / `## 5`）。従来は main が `gh pr diff` を 1 回読み、さらに各 reviewer プロンプトへ**転記**していた（`diff サイズ × (1 + N)`）:
  - `triage-signals.sh` が diff を `$DIFF_FILE` に保存する。**リダイレクトで書くので main は中身を見ない**
  - agent には `$DIFF_FILE` のパスと担当ファイル名を渡し、`diff-slice.sh` で自分の担当ハンクだけを切り出させる（実測: 199KB の diff → 1 ファイル 4.5KB）
  - 担当を絞れない観点（cross-cutting / pattern-consistency / spec-compliance 等）には `--list` で全ファイル名を渡す
  - `## 3.5` に**判断基準「複製係数」**を明記した（係数 1 に近いものはインラインが安い / 体数ぶん立つものはパス渡し）。explorer 結果は従来どおりインライン
- **Phase 0 の入力を signal digest に変更**（両 SKILL Step 2 / Step 1 + triage-guide `## 2`）。生 diff ではなく決定的なシグナル表で構成判断する:
  - `## meta`（diff パス）/ `## size`（core 規模・`size_tier`・モード判定用の比率）/ `## files`（class × 増減）/ `## hunks`（core の `@@` 関数コンテキスト）/ `## focus-signals`（観点判定表のヒット数と根拠ファイル）/ `## red-flags` / `## surface` / `## explorer-signals` / `## agents-md` / `## issue-ids`
  - **スクリプトは policy を持たない**。モード決定・観点採否・体数は従来どおり triage-guide が決める（スクリプトが出すのは事実のみ）。語彙は triage-guide `## 3` / `## 8.5` に一致させる
  - 従来 SKILL 本文に散っていた bash（core 規模カウント / AGENTS.md 階層探索 / Issue ID 抽出）を本スクリプトに集約した。`## agents-md` は orchestration-guide `## 4` の探索結果を兼ねる

### Added
- **`scripts/triage-signals.sh`**: diff の保存とシグナルダイジェスト出力。`--pr <N>`（review） / `--base <ref>`（self-review: base..HEAD + staged + unstaged） / `--staged`（staged のみ）
- **`scripts/diff-slice.sh`**: 保存済み diff から指定パスぶんのハンクを切り出す。`--list` で含まれるファイル一覧

### Fixed
- **self-review の diff 収集から staged 分が落ちる経路を塞いだ**。ダイジェスト化にあたり 3 系統（`base..HEAD` / `--cached` / unstaged）を集約する実装にし、**同一パスが複数系統に現れたときはパス単位で合算**する（集約しないとファイル数が重複計上され `size_tier` が実態より大きく出る）。従来 SKILL の awk も `f[$3]=1` でファイル数だけは dedup していたが、スクリプト側で行数も含めて一貫させた

## [2.45.0] - 2026-08-06

self-review に**コメント推敲**を組み込んだ版。毎回手で頼んでいた作業をスキル側に載せる。

### Added
- **コメント推敲（B 系統）を self-review に追加**（reviewer-prompts.md `### コメント推敲（B 系統）` + self-review SKILL.md Step 4 / Step 5 手順 1・7 / Step 6 / Step 6.4 + triage-guide 観点判定表）。diff で追加・変更されたコメントを **①読み手にとって必要な情報のみか ②冗長表現が排除されているか** の 2 観点で推敲し、`before` → `after` の最小差分でレポートの「✏️ コメント推敲」セクションに出す:
  - **severity マトリクスを通さない別経路にした**。`comment-accuracy` はチェック項目に「冗長コメント」「what ではなく why」を持つが、推敲提案は**構造上 2 段のフィルタを通過できない**: ①報告マトリクスは MINOR を confidence 95+ でしか通さない ②scoring-guide の好みクランプが「CLAUDE.md / style guide / 計測データ / file:line の具体的不具合」の 4 つのいずれの根拠も持たない指摘を confidence 40 に落とす（文体規約を持たないプロジェクトの推敲提案がこれに該当）。**どちらもバグ指摘の precision を守るための正しい機構**なので、推敲側をパイプラインから外す。severity / confidence を付けず、手順 1〜6 と反証レイヤーをすべてバイパスする
    - **根拠は構造であって計測ではない**: payload は focus 別の属性を持たないため「報告ゼロだった」を実測で示すことはできない（v2.44.0 の 43 件集計でも focus 別の内訳は取り出せない）。doc 側にも実測断定を書かない旨を明記した
  - **体数は増やさない**。既存の `comment-accuracy` reviewer に相乗りさせる（起動条件も共用）。バンドルで束ねられた場合も出力契約は削らず、`comment_polish.fired` は `true` を記録する（専任 reviewer の有無で切ると high 既定で常に false になる）
  - **過剰修正の抑制**: 対象は diff で追加・変更されたコメントのみ / 意味が変わらない同義変換は出さない（短くなる・曖昧さが減る、のどちらかが無い提案は却下）/ 非自明な why・TODO の背景・regex や境界条件の意図・外部制約への言及・ハマりどころの警告は残す（迷ったら残す側に倒す）
    - **件数上限は reviewer にかけない**（発見段階の重要度による自己間引きは CLAUDE.md「Opus 5 世代で逆効果になる足場」③に該当する）。掲載上限 10 件はオーケストレーター側（Step 6）で切り、`suggested` には切る前の総数を入れる
  - **二重掲載の除去は「報告マトリクスを通過して残った指摘」とだけ突合する**。「A 系統が指摘として挙げた」を条件にすると、A で MINOR 95+ に阻まれ B でも dedup される二重落ちが起き、B 系統を作った理由そのものを打ち消す
  - **review 側には入れない**。他人の PR に文面の推敲を投稿するのは越権になりやすく、review の返答ドラフトは PR コメントとして投稿される前提のため。B ブロックは Focus テンプレートと同格の見出しに置きつつ「Focus テンプレートではない」と明示し、**両 skill の Step 4 に連結可否を 1 行ずつ書いて**混入と不発の両方を塞いだ（散文 1 行のガードだけでは、両 skill の起動指示が同一文言のため review 側に混入する経路が残る）
  - **embed mode の findings JSON には含めない**（severity を持たず、auto-fix の対象にしない。採否は人間が決める）
- **`comment_polish` を `review:completed` payload に追加**（self-review のみ。`{fired, suggested}`）。「起動したが提案 0 件」（打ち手＝観点の効き・プロンプトの具体性）と「そもそも起動していない」（打ち手＝ triage の起動条件・Step 4 の連結漏れ）は対処が正反対なので 2 フィールド持つ。本機能は *チェック項目に書いてあるのに報告まで到達しない* という失敗の再発防止が目的であり、**出力ゼロが観測できないと同じ穴に落ちる**:
  - `fired` は**観点として起動されたか**で判定する（単独／バンドル相乗りを問わない）。`suggested` は reviewer が挙げた**総件数**（掲載上限・dedup の前）で、レポート掲載数とは一致しない。reviewer が `## コメント推敲提案` ブロックごと落とした場合は `-1`（測定不能）とし `missing_coverage` に記録する — 「該当なし」と「ブロック欠落」を 0 に潰さないため
  - 版マーカー: `comment_polish` の存在が v2.45.0 以降（self-review のみ）

## [2.44.0] - 2026-08-06

蓄積済み 43 件（`review` 12 / `self-review` 31）を実際に集計して、**計測が答えられない問い**と**規約と実データの乖離**を 3 つ見つけて塞いだ版。仕様（scoring / 報告マトリクス）には手を入れていない — 切り分けデータが無い段階で precision に関わる不可逆な変更をしないため。

### Added
- **`pre_adjust_counts` を `review:completed` payload に追加**（orchestration-guide `## 16` + 両 SKILL のスコアリング手順 1）。スコアリング手順 1 完了時点（統合・dedup 後、verdict 反映・加減算・降格・フィルタの**前**）の severity 別件数。既存の `*_count` は報告マトリクス通過**後**の値しか持たないため、**「reviewer が検出しなかった」と「検出したが調整で消えた」を事後に区別できなかった**:
  - 動機は下記の観測（triage-guide `## 7` の「未解決の観測」に記録）。**review 経路 12 件すべてで `major_count`=0** の一方 self-review は 31 件で MAJOR 78 件。MAJOR と MINOR は報告マトリクス上どちらも confidence 95+ の同一閾値なのに review では MINOR だけ 27 件通っており、しかも review は `recall_skeptic.surface` が 10/10 で true（= surface-aware 閾値で MAJOR が 85+ に**緩和されている**状態）でゼロ。両 SKILL の scoring 規約は同一であることを確認済みで、仕様差では説明がつかない
  - **一段目（検出由来 / 調整由来）だけを切るフィールド**。降格（`severity-inflated` / `[scope:out]`）と confidence 落ちは同じ差分に合流するので内訳は分離できない。二段目が必要と分かってから内訳フィールドを足す（LLM が手で組む JSON なのでフィールド数自体がコスト）
  - 版マーカー: `pre_adjust_counts` の存在が v2.44.0 以降

### Fixed
- **`missing_coverage` の語彙を固定**（orchestration-guide `## 16` + 両 SKILL のレポート出力）。要素を **識別子のみ**（`<focus 名>` / `<phase 名>` / `<phase 名>:<focus 名>`）に限定し、理由・件数・finding id・自由文の混入を禁止した。理由はレポート本文の「⚠️ 欠損観点」セクションに書く。実データでは同一概念が `adversarial-verify:finding-A` / `adversarial-verify-finding3` / `adversarial-verify: F2 未反証` / `adversarial-verify: 対象が実証済み` の **4 通りに分裂**しており、`group_by` 集計が成立していなかった（欠損観点の偏りを見るのが本フィールドの唯一の用途なので、綴りが割れると計測目的そのものが消える）
- **`result_grid.error` = `len(missing_coverage)` の一致要件を撤回**（orchestration-guide `## 16`）。`missing_coverage` は agent 失敗だけでなく「観点未起動（reviewer 上限超過・条件不成立）」「フェーズスキップ」も含むため、正しい関係は `error ≤ len(missing_coverage)` の包含。**実データ 43 件中 11 件で不一致**（うち 10 件は `error=0` で `missing_coverage` が非空）。一致を仮定した検算をしない旨を明記した

## [2.43.0] - 2026-08-04

`review` 経路で 2 つの構造的な壊れ（子 agent が base branch を読む / 計測が並行セッションに汚染される）を塞ぎ、壁時計の残る主因である「メインコンテキストのプロンプト複製」と「直列 wave 数」に手を入れた版。

### Fixed
- **子 worktree の `gh pr checkout` が構造的に必ず失敗し、agent が base branch のファイルを読んでいた**（GitHub issue #98。explorer-prompts / reviewer-prompts の共通指示 + orchestration-guide `## 1`）。review skill は Step 0 で `EnterWorktree`、Step 1 で `gh pr checkout` するため**親 review worktree が PR ブランチを保持している**。子 worktree は親 branch を継承せず origin/default から派生するので `HEAD != {{HEAD_REF}}` が常に成立し、else 分岐の `gh pr checkout` が git の二重チェックアウト禁止で失敗する。テンプレートは失敗時に続行するため、**テンプレート自身が「深刻な偽陽性の原因」と警告している状態のままレビューが走っていた**。issue #69 の `{{HEAD_REF}}` ガードは「親が checkout 済みなら子でスキップ」の意図だったが、子の HEAD が PR ブランチになることはないため review 経路では一度も発火しない:
  - ブランチ名での checkout を廃止し、`git fetch origin refs/pull/<N>/head` + `git checkout --detach FETCH_HEAD` に変更（detach なら親と競合しない）
  - 検証を **期待 HEAD SHA（`{{HEAD_SHA}}`）との突合**に変更。`{{HEAD_REF}}` はブランチ名なので detach 後の検証には使えず、プロンプト冒頭の文脈情報としてのみ残す。オーケストレーターは Step 1 の `gh pr view --json headRefOid` で取得して全 agent に注入する
  - 不一致時は「レビュー結果の冒頭に warning を明記し confidence を下げる」を明示（silent に続行させない）
- **`TS_FILE` が worktree 間で衝突し `duration_*` が「もっともらしい誤値」で publish されていた**（GitHub issue #99。orchestration-guide `## 13.1` + 両 SKILL）。`--git-common-dir` は linked worktree からもメインリポジトリの `.git` を返すため、publish 先をメインルートに固定する目的（#96）には正しい一方、**同一リポジトリの全 worktree で `MAIN_ROOT` が同一**になり `TS_FILE` が 1 本に collapse していた。Step 1 は `>` の truncate で書くので後発セッションが先行のマーカーを消し、締めフローの `rm -f` は走行中の他セッションのマーカーを削除していた。**汚染が欠測（`-1`）ではなく過小値として入る**ため、ロールバック判断の一次指標 `duration_fleet_min` が静かに壊れる（実測: 52 分のレビューが約 8 分）:
  - **パスの識別子を `git rev-parse --show-toplevel`（その worktree 自身のパス）から作る**。`--git-common-dir` が全 worktree で同じ値を返すのに対しこれは worktree ごとに異なるので、1 つで並行セッションを分離できる。review はさらに PR 番号を混ぜる。識別に失敗したときの縮退先は「別ファイル ＝ 欠測」であって誤値ではない
  - **ブランチ名は識別子に使わない**。`git rev-parse --abbrev-ref HEAD` は **detached HEAD でも `HEAD` を返す**ため `${VAR:-fallback}` が発火せず、detached な worktree がすべて同じ slug に collapse する（`git bisect` 中に発生）。切り詰めによる長いブランチ名の接頭辞衝突も同様。初版はブランチ slug を使っていたが、セルフレビューで両方の反例が実測されたため差し替えた
  - `rm -f` を `t2` マーカーの存在確認つきに変更。ただし**これは所有権チェックではなく近似**（ファイル内容に書き手の識別子が無い）。衝突自体は上記のパス識別子で塞ぎ、このガードは万一の衝突時に掃除より他セッションの計測を優先する二段目、という位置づけを doc に明記した
  - v2.43.0 未満の `duration_*` は汚染を受けうるため、ロールバック判断の基準側に使わない旨を doc に明記

### Added
- **大きい共有コンテキストのファイル経由渡し**（GitHub issue #100 A。orchestration-guide `## 3.5`）。Step 2.5 の「LLM による再構築・要約・編集は禁止」は正しいが、素直に実装するとオーケストレーターが同一ブロックを N 体ぶん**書き出す**設計になっていた（実測: PR コンテキスト約 15,000 字 × 6 体。52 分のレビューのうち agent 実時間 29 分を除いた約 20 分がメインコンテキスト）:
  - `fetch-pr-context.sh` の出力を `$PR_CTX_FILE`（`$TMPDIR` 配下・PR 番号入り）に保存し、reviewer には**パスのみ**渡して自分で Read させる。**忠実性はむしろ上がる**（バイト同一で転記リスクがゼロ＝「再構築禁止」を機械的に保証）。子 worktree でも `$TMPDIR` は同一ホストなので読める
  - AGENTS.md / CLAUDE.md の階層注入も**元ファイルのパス渡し**に変更（既にディスク上にあるのでコピーも不要）
  - explorer 結果は**従来どおりインライン**（選択的注入で複製係数がほぼ 1。ファイル化すると explorer 体数ぶんの Write が増えて逆効果）
  - ファイル書込に失敗した場合はインライン注入にフォールバックする（レビュー本体をブロックしない）
  - パス導出の `WT` は**それを使う bash ブロック内で導出する**。別ブロックの変数は消えており、空のまま `printf %s "" | cksum` を通すと**エラーにならず定数 `4294967295` が返って**パスが「ホスト上の全リポジトリで共有される固定値」に潰れる（＝別リポジトリの PR コンテキストを掴む誤値縮退）。初版はこれを踏んでおり、セルフレビューで 4 体が独立に検出した
  - 保存は**一時ファイルに書いて成功時のみ `mv`** する。`>` はスクリプト失敗時も空ファイルを残し、空ファイルは「読める」ため reviewer の「読めなかった場合」ガードをすり抜けて「過去指摘なし」と誤判定される
- **Phase 0 の構成テーブルに「直列 wave」行を追加**（GitHub issue #100 B。triage-guide `## 5` / `## 5.1`）。ユーザーに見えていたのは体数だけで、壁時計を決める直列 wave 数は最後まで見えなかった。**体数はトークンコストのレバー、wave 数は壁時計のレバー**という `## 7` の切り分けをそのまま表示する（下限＝ Phase 0 で確定している wave / 上限＝条件付き wave が全部発火した場合、wave あたりの目安時間つき）
- **`duration_explore_min` の計測**（GitHub issue #100 D。orchestration-guide `## 14`）。`t1` を explorer 発行直前に置いた v2.41.0 の修正の副作用で、fleet 区間に「explorer wave + reviewer wave + プロンプト構築 + scoring」が全部入り、どの wave が何分かかったか分からなくなっていた。explorer 回収直後に `t1b` を置き、`t1`→`t1b` を explorer wave の実時間として切り出す（`duration_fleet_min` の内数。explorer 未起動時は `-1`）。triage-guide `## 5.1` が Phase 0 で提示する「wave あたり目安 6〜16 min」を実測で裏付けるフィールド（実測: explorer 2 体で 5.9 分）
  - **「メインコンテキストのプロンプト構築時間」はマーカーでは測れないと確定した**（同節）。プロンプトのテキストを書く行為がそのまま Agent call の発行であり、「書き終わったが未発行」の瞬間が存在しないため、マーカーを発行より前に置けば書く前に発火し、後ろに置けば agent が既に走っている。初版では `t1c` / `duration_prep_min` でこれを測ろうとしたが、セルフレビュー実測で**発行直前マーカーが 7 秒**（同じ fleet 区間は 22 分）を記録して構造的に不可能と判明したため撤回した。`## 3.5` の外出し効果は `duration_fleet_min` を `size_tier` × `agents.reviewer` × `effort` で層別して見る
- **HEAD 検証の機械的回収**（GitHub issue #98 の未達分。orchestration-guide `## 5` + 両プロンプトテンプレート）。SHA を注入しても、検証結果を報告する必須欄が無ければ「検証を怠った / 一致した / 不一致だが warning を書き忘れた」がオーケストレーターから区別できず、issue #98 が名指しした「自己申告に委ねている」構造が残る。出力フォーマットに **`HEAD 検証: <実測 SHA> / 期待 <SHA> / 一致|不一致|未実行` の必須 1 行**を置き、不在・不一致なら `missing_coverage` へ記録し当該 agent の指摘全件に `[unverified: HEAD 不一致]` を付ける。`review:completed` payload に `head_verified: {ok, mismatch, unknown}` を追加し、「何体が正しい HEAD を見ていたか」を事後集計できるようにした。**行の不在自体が信号**になるので agent の善意に依存しない
- **xhigh / max の反証ゲートと非対称ゾーン論の緊張を明文化**（GitHub issue #100 補足。triage-guide `## 9`）。xhigh / max のゲートは「報告ゾーン全体 + MAJOR」なので confidence 95+ の最も取り下がりにくい層が全件対象になり、直列 wave 1 本（6〜16 min）を要する。据え置く理由（明示 escalation での偽陽性コストの非対称性）と、壁時計を縮める必要が出たときの最初の候補（MAJOR 95+ をゲートから外す）を記録した

### Changed
- **Round 2 のスキップ条件に「unmet が全件 repo 外」を追加**（GitHub issue #100 C。triage-guide `## 8` + orchestration-guide `## 6` + 両 SKILL）。実測では unmet 8 件のうち 7 件が構造的に到達不能だった（DB / 本番の実データ、外部サービスの実挙動、repo に存在しない旧実装、意図的にスキップした lint 実走）。target の分類は文字列を読めば決まるのでメインコンテキストで判定でき、agent を要さない。**ただし無条件スキップは有害**なので「全 target が repo 外のときだけ」に限定する — 実測で到達可能だった 1 件（DB 制約）を Round 2 が repo 内 doc で解決した結果、指摘 1 件の severity が MAJOR → MINOR に変わっている。判定に迷う target は repo 内側に倒す。スキップ時は `missing_coverage` とレポートの「動的ラウンド」行に理由を出す
- **`duration_triage_min` を「メイン思考量の代理指標」として使うのをやめた**（issue #100 D）。`duration_fleet_min` の説明に「プロンプト構築を含む（分離できない）」を明記し、triage-guide `## 7` の打ち手③（壁時計を縮めるときにまず触る箇所）も「メインコンテキストの思考量（`duration_triage_min` で観測）」から「プロンプト複製量（`## 3.5` のファイル経由渡し。効果は `duration_fleet_min` の層別で見る）」に差し替えた — 定義変更が消費サイトに伝播していなかった
- **agent の checkout ブロックに dirty tree ゲートを追加**（両プロンプトテンプレート）。`git checkout --detach` は**未コミット変更があっても exit 0 で成功し変更を持ち越したまま detach する**（実測）。隔離 worktree はレビュー開始時点で必ず clean なので、dirty なら「ユーザーの作業ツリー」と自己判定して checkout をスキップする。散文の「self-review からは PR 番号が渡らないためスキップ可」という許可形だけでは、PR 番号が紛れる経路が 1 つでもあればユーザーの作業ツリーを silent に detach しうる
- **`git fetch` と `git checkout` の失敗を切り分け**（両プロンプトテンプレート）。`A && B || C` の結合では fetch 失敗でも checkout 失敗でも同じメッセージが出て、agent が誤った原因を報告していた
- **`gh pr checkout`（親 worktree・review Step 1）の失敗時に中止**するよう明記。子 agent は detach で正しい HEAD に入るため、続行するとメインコンテキストだけが base branch を読む非対称が生じる（規模判定・Phase 0・締めフローが全部 base 基準になる）
- **`HEAD_SHA` が空のまま agent を起動しない**よう明記（orchestration-guide `## 1`）。空を注入すると detach が成功していても全 agent が恒常的に「不一致」warning を出して confidence を下げ、`git rev-parse` 自体が失敗する環境では空同士が一致して checkout をスキップしたうえ「一致」と判定する
- `grep ... && ...` 形のマーカー記録・掃除を `{ ...; } || true` で包み、正常系（explorer 未起動・`t2` 欠測）でブロックが exit 1 を返して「失敗」と誤読されるのを防いだ
- triage-guide `## 5.1` の worked example を `2〜5` → `2〜6` に修正し、上限の算式（表の各行の最大値の総和）を明記。括弧内に 6 本を列挙しながら上限を 5 と書いていた
- `orchestration-guide` `## 14` の見出し・導入文と INDEX.md の説明を「3 分割」から実体に合わせて更新

## [2.42.0] - 2026-08-03

### Changed
- **投稿コメントの署名を `— Created by Claude` に変更**（reply-tone-guide `## 0.1`。GitHub issue #97 提案 1）。旧署名「— Claude Code によるレビュー」は、このガイドが扱う文面の主対象が**レビューではなくレビューへの返答**（著者として対応・釈明・据置を返す文面）であるため実態と食い違っていた（実例: 著者としてレビューコメント 11 件に返答した際、全件で「対応しました」の末尾に「レビュー」が付いた）:
  - **voice を問わず 1 本**（レビュアー発信の 2.6 / 2.7 も含む）。voice で分ける案も検討したが、レビュアー発信でも「レビューによる」と名乗る必要はなく、voice の情報はメタ行（0.5）が既に運んでいるため、分岐を増やさず中立な 1 本に寄せた
  - **リポジトリ規約が署名文言を定めている場合はそちらを優先**する旨を明記（`CONTRIBUTING.md` が特定の文言を要求するケースとの衝突を解消）。根拠にできるのは Step 2 のコンテキスト収集で**実際に読んだ**規約ファイルに限る（PR テンプレートは収集対象外である点も明記）
  - 2.1〜2.7 のテンプレート全件と 5 章の例外に署名を明示（一部にしか無いと生成時に落ちるため。簡潔さが正の 5 章ほど落ちやすい）
- **署名 literal の複製点を 1 つ減らした**（closing-flow-guide `## 3`）。SKILL.md が締めフローの正本として指す `closing-flow-guide.md` にも署名文言が literal で書かれており、**reply-tone-guide だけ更新して旧署名 4 箇所・旧締め文言 1 箇所・旧チェックリスト文言 2 箇所が取り残された**（セルフレビューで 3 体が独立に検出）。few-shot 例が旧文言で揃っていると規則文より強く効くため、この状態では変更が実運用でほぼ効かない:
  - closing-flow-guide の出力例 3 件の署名と 2.1 例の締め（**新ルールで「避ける」に指定した文言そのものだった**）を更新
  - 規則本文からは literal を除去し「reply-tone-guide `0.1` の正本に従う」の参照に変更。0.6 チェックリストの項目複写も「0.6 を読む」に置換（複写がある限り片方だけ更新される事故が再発する）
- **「いかがでしょうか」系の許可範囲を番号列挙から原理に変更**（reply-tone-guide `## 1.1` / `## 1.2`）。旧文は 2.4 / 2.5 に限定していたが、**2.6 の部分対応**（残存指摘があり対応要否の判断が要る＝メタ行に「マージブロッカー: はい」が入りうる）を取りこぼしており、規則とテンプレート（2.6）が矛盾していた。判定基準を「**相手の応答がなければ次に進めない場合**」に置き換え、番号は例示に降格
- 2.2（部分対応）の締めを明示し、`## 3` の必須要素に 0.6 と同じ適用除外（2.7 承認・5 章は締めの一文を持たない構成が正）を追記
- **締めの既定形を「応答不要な形」に変えた**（reply-tone-guide `## 1.1` / `## 1.2` / `## 2.1` / `## 2.3`。issue #97 提案 2）。従来は判断委譲として「ご確認いただけると助かります」「いかがでしょうか」を既定にしていたが、**対応が完了している報告にこれを付けるとレビューの往復が 1 回増える**（レビュアーは必要なら再度コメントする）:
  - 既定形を **「認識に誤りがあればご指摘ください。」** に統一（誤りがなければ相手は何もしなくてよく、誤りがあれば指摘できる＝判断委譲の意図を保ったままラウンドトリップを増やさない）
  - **「いかがでしょうか」系は相手の判断が実際に必要な場面（2.4 意図確認 / 2.5 反証・両論提示）に限定**。2.3 で判断を委ねたくなったらそれは据置報告ではなく両論提示なので 2.5 を使う、という切り分けも明記
  - 0.6 チェックリストと `## 3` の生成手順（必須要素）にも反映

## [2.41.0] - 2026-08-03

壁時計時間の主因が「体数（breadth）」ではなく「**1 体あたりの探索量・直列 wave 数・メインコンテキストの思考量**」にあると特定し、そちらを削る版。v2.39.0 / v2.40.0 の体数縮小はトークンコストには効いたが、並列発行が効いている限り fleet 区間の実時間は wave 内最長の 1 体で決まるため壁時計には構造的に効かなかった（実測: 3 体・210 分のサンプル）。

### Changed
- **reviewer 共通指示の契約を圧縮し、1 体あたりの探索予算を明示**（reviewer-prompts.md `## 1`）。指示に忠実な世代のモデルでは、指摘 1 件あたりに課した 10 個超の契約をすべて律儀に実行するため、思考時間とツールループが「契約数 × 指摘数」で膨らんでいた:
  - **評価原則 1 を「PASS が証明されるまで FAIL」→「未確認は SKIP と書く」に改訂**。旧文は「問題なし」に証拠を要求することで探索を無限定に延長させていた。求めているのは「未確認を PASS と偽らないこと」であって「PASS を証明しきること」ではない
  - **探索予算を新設**: diff 外の追加 Read は 10 ファイルまで / 1 つの主張の裏取りは 1 往復まで（届かなければ confidence を下げるか `unmet_information` へ）/ 予算を使い切ったらその時点で確定する。**予算は探索にかけ、報告にはかけない**（指摘の件数・severity に上限は設けない。発見段階の自己間引きは recall を落とすため従来どおり禁止）
  - invariant 検算・claim grounding を**手順（やり方の記述）から出力要件（根拠欄が埋まらなければ confidence を下げる）へ格下げ**。`[unverified:]` タグ等の機構は据え置き
  - 「静的検査優先の自己問い」を指摘ごとの自問プロセスから、該当時のみ 1 行併記する出力規約へ縮小
- **冷や読み skeptic を reviewer wave に相乗り発火**（triage-guide `## 8.5` / orchestration-guide `## 9`）。skeptic は findings 非注入が設計の核で reviewer 出力に一切依存しないにもかかわらず、Phase 5.8/4.8 に直列配置されていたため、依存関係が無いのに opus 1 体分の実時間を積み増していた。surface 判定（正規表現 + PR 自己申告）を Phase 0 に前倒しし（review Step 3.4 / self-review Step 2.4）、ゲート通過時は reviewer 一括発行に含める。結果の統合・dedup は従来位置のまま。**fallback**: reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になった場合のみ従来どおり直列で単独起動する
- **反証レイヤーをバッチ化し effort を `max` → `high` に引き下げ**（triage-guide `## 9` / orchestration-guide `## 5`・`## 10`）。反証は既定パスで走り体数が指摘数に比例する**唯一の変動費**で、既定パスのコストの主要項だった:
  - **1 体あたり最大 5 件**のバッチ（上限 3 体 = 15 件）。反証が要求する独立性は「指摘を出した reviewer と別コンテキスト」であって「指摘同士が別コンテキスト」ではない。同一 diff の読み直しを N 体で重複させる意味がないため束ねる
  - effort 引き下げの根拠は、誤判定コストの非対称性を **verdict の扱い側**で既に吸収していること（BLOCKER / CRITICAL は refuted でも消さず係争注記＝ scoring-guide の不変条件）。扱い側で保険が効いている層に effort でも保険をかけるのは二重。**体数が 1 体固定の meta-reviewer / 冷や読み skeptic は `max` 据え置き**
  - バッチ内の相互汚染（1 件の verdict を別件の根拠にする）を reviewer-prompts.md `## 7` の鉄則で禁止。全 finding_id に verdict を返させ、欠落は verdict なし扱いで突合する
  - 対象が 15 件を超えた場合は severity → confidence 順で上位 15 件のみ反証し、溢れた件数をレポートに明示する（silent に落とさない）

### Added
- **所要時間を 3 分割して計測**（orchestration-guide `## 14`。payload に `duration_triage_min` / `duration_fleet_min` / `duration_closing_min` を追加）。`duration_min` 単独では agent 実行時間・メインコンテキストの思考時間・人間の応答待ちが 1 個の数字に潰れ、どの改善が効いたか判定できなかった（210 分のサンプルが 1 件あるだけで内訳不明だった）:
  - `TS_FILE` に区間マーカー（`t0` 開始 / `t1` reviewer 一括発行の直前 / `t2` 初回レポート出力の直後）を追記し、publish 時に awk で 4 値を算出する。欠測はすべて `-1`（0 と区別する）
  - `duration_triage_min` = メインコンテキストの思考時間の代理指標 / `duration_fleet_min` = agent wave の実時間 / `duration_closing_min` = 大半が人間の応答待ち（**効果測定に使わない**）
  - `duration_min`（全体）は後方互換のため意味を変えない。3 区間の和は全体と一致しないことがある（マーカー欠測時）ため一致を仮定しない
  - **`duration_triage_min` の存在が v2.41.0 以降の publish マーカー**（日付では切らない＝配布ラグに耐える。`agents` フィールドと同じ流儀）
- `agents.verify_findings`（反証の**対象指摘数**）を payload に追加。バッチ化で `agents.verify`（体数）と件数が分離したため別フィールドにする

### Fixed
- **`severity-inflated` verdict で高 severity 指摘が silent に消える穴を塞いだ**（scoring-guide）。旧規約は「全 severity で 1 段階下げる」だったため、**BLOCKER 60-79 → CRITICAL（要 80）/ CRITICAL 80-94 → MAJOR（要 95）** が報告マトリクスを割って消え、係争注記も残らなかった。`refuted` 経路しか塞いでいない不変条件を「反証 effort を下げてよい唯一の根拠」に昇格させていたため、この修正なしでは effort 引き下げの前提が成立しない。高 severity は**降格後にマトリクスを割る場合は severity 据え置き + 反証メモ**に変更
- **`duration_triage_min` に explorer wave が混入していた**。`t1` を reviewer 発行直前に固定していたため、explorer（最大 4〜6 体）の実時間が「メインコンテキストの思考時間の代理指標」に計上され、explorer を配置したレビューで「思考量が主因」という誤診に誘導していた。`t1` を**最初の agent 一括発行の直前**（explorer があればその直前）へ移し、`grep` ガードで二重記録を防ぐ。**agent wave はすべて fleet 側**に入る
- **self-review の `duration_closing_min` が構造上 ≒0 になる問題**。self-review は publish（Step 6.4）が Step 7 の修正方針確認より前にあるため t2→t3 に人間待ちが入らない。0 を publish すると「人間待ちが無かった」と誤読されるため **`-1`（測定不能）** を入れるよう変更し、`duration_min`（全体）の意味が publisher 間で非対称であることを両 SKILL と orchestration-guide に明記
- **review Step 3.4 の skeptic 相乗りゲートが `--emergency` / `skip-mode` を取りこぼしていた**。相乗りで起動が前倒しされる以上、Phase 5.8 に到達してからスキップ判定しても手遅れ（緊急モードで `effort: max` の skeptic が余計に走る）。条件の個別列挙をやめ Phase 5.8 の定義への単一参照に変更
- 反証バッチの切り方を「同一ファイルを寄せる」から**「同一ファイル・同一 reviewer 由来は散らす」に反転**。バッチ化で失うのは reviewer からの独立性ではなく**反証者側の誤読の独立性**で、1 体の誤読が同一ファイルの指摘を束で `refuted` にしうる（MAJOR は −40 で実質消える）
- 探索予算の**適用範囲を reviewer / specialist に限定**（独立検証レイヤーは対象外）。打ち切り時の痕跡を選択式から **AND**（confidence を下げる場合も `unmet_information` に `予算切れ:` を必ず記録）に変更し、探索予算経由の recall 低下が事後に検出できるようにした。low / medium では Round 2 が走らず回収経路が無いことも明記
- triage-guide `## 7` のロールバック条件が `duration_min`（全体）で所要時間を見ていたため、締めフローの人間待ちに支配されて体数調整の効果を検出できなかった。**jq スニペット本体を `duration_fleet_min` に修正**（散文での置換指示をやめた）。あわせて「体数は壁時計に効かない（実測）」という断定を、**「効いた証拠が現時点で無い（旧サンプルは内訳不明で判定不能）」**に緩めた（同じサンプルを一方で使用不能・他方で結論の根拠にしていた循環の解消）。「時間が長いから体数を減らす」判断を混ぜない規範は維持
- 反証の 2 縮小（バッチ化 + effort 引き下げ）に**ロールバック条件を追加**（`adversarial_verify` の `uncertain` 比率と MAJOR/MINOR の `refuted` 比率を版マーカーで層別して監視）
- `adversarial_verify` に **`severity_inflated`** を追加（4 つ目の verdict が集計から漏れていた）。`agents.verify_findings` の定義を「ゲート対象数」から**「実際に verdict が返った件数」**に明確化し、レポートの反証行の書式を orchestration-guide `## 10` に一本化。`agents.verify` は v2.41.0 前後で意味が変わるため層別が必要な旨を明記
- orchestration-guide `## 9` 手順 2 に**「相乗りで発火済みなら実行しない」ガード**を追加（skeptic の二重起動と `recall_skeptic.fired` の計測汚染を防ぐ）
- 反証 effort 引き下げ後も「補償層はいずれも `max` 据え置き」という旧前提が同一セクションに残り、新表と矛盾していたのを解消。triage-guide から orchestration-guide への effort 方針の参照（存在しない `## 7` 引用）も修正

## [2.40.0] - 2026-07-31

### Fixed
- **`review:completed` が worktree ごと消えて review 経路の計測が 1 件も残っていなかった問題を修正**（GitHub issue #96 B）。`event_bus_publish` は `CLAUDE_PROJECT_DIR` 未設定時に cwd 相対で書くため、review では Step 0 の `EnterWorktree` 後に publish → 締めフロー 5 の `ExitWorktree(remove)` で worktree ごと消えていた（self-review も作業用 worktree 内から実行された場合は Step 8 teardown で同型の消失）。publish 先をメインリポジトリのルートに固定する:
  - 導出は `git rev-parse --path-format=absolute --git-common-dir` の親。**worktree 内の `--show-toplevel` は worktree 自身を返すため使えない**（`--git-common-dir` は linked worktree 内でも main の `.git` を返す）
  - publish 呼び出しに `CLAUDE_PROJECT_DIR="$MAIN_ROOT"` を前置して環境値より導出値を優先する
  - `duration_min` の開始時刻ファイル（`TS_FILE`）のパス導出も `pwd` 基準から同じ `MAIN_ROOT` 基準へ変更（worktree 進入前後で `pwd` が変わり欠測になるのを防ぐ）。publish 後に `rm -f` で掃除し、中断したレビューの残骸が次回を汚さないようにする
  - `GCD` が空（git 2.31 未満 / 非 git）のときだけ `pwd` へフォールバックする。無条件に `cd "$GCD/.."` と書くと `/` に cd して `/.claude/events.jsonl` へ書きに行くため、この分岐は必須。導出式と落とし穴の正本は orchestration-guide `## 13`
  - **影響**: v2.39.0 で追加した計測フィールドは review 経路では 1 件も蓄積されていなかった。v2.39.0 の high 既定縮小の効果測定は本修正以降のサンプルで行う（triage-guide `## 7` のロールバック条件に注記）

### Changed
- **体数上限を「effort 上限 × 規模キャップ」の 2 系統 min に変更**（GitHub issue #96 A）。従来は effort 上限しか効かず、9 ファイル `+116 -22`（うち本番コード 3 ファイル `+22 -13`、残りはテスト 5 + doc 1）の PR に xhigh で 17 体が起動しレポートまで 95 分・締めまで 130 分かかっていた。旧 `## 6` の規模別構成は「Phase 0 が明確な判断を下せない場合」限定のフォールバックだったため、diff シグナルが読めると規模が上限に一切効かなかった:
  - **規模キャップ**（triage-guide `## 6.2`）: small = explorer 0 / reviewer 3 / specialist 1、medium = 2 / 5 / 2、large = キャップなし。最小保証の 2 体はキャップより優先。収まらない観点は `missing_coverage` に「規模キャップ: <帯>」として記録（脱落を silent にしない）
  - **帯は core で判定する**（`## 6.1`）: lock / 生成物 / vendor を除外し、さらにテスト・doc を除いた本番コードで数える。テスト・doc は観点の起動根拠にはなるが体数を押し上げる根拠にはしない。判定用の `git diff --numstat` + フィルタを両 SKILL に同梱
  - **削るのは breadth だけ**（`## 6.3`）: reviewer 個々の effort・meta-reviewer（5.6）・冷や読み skeptic（5.8）・反証レイヤー（5.9）は帯に関わらず effort 指定どおり動かす。規模キャップが effort 上限を下回った帯では Round 2 を effort に関わらず 1 段圧縮経路にする。「effort は 1 体あたりの深さの指定であって並べる体数の指定ではない」を設計原則として明記
  - 旧 `## 6` のフォールバック構成は `## 6.4` に温存（キャップではなく初期値としての役割は変わらない）

### Added
- **`review:completed` payload に `size_tier` を追加**（`small` / `medium` / `large`）。規模キャップの効果測定と `duration_min` の層別に使う。所要時間は規模と体数の両方に効かれるため、帯を混ぜた中央値ではキャップの効果と PR 規模の分布変化を分離できない（triage-guide `## 7` のロールバック jq に層別の注記を追加）
- レポート冒頭に **`size:` と `実効上限` 行**を追加（review / self-review 共通）。effort 上限と規模キャップのどちらが効いたかを人間が事後に検証できるようにする

## [2.39.0] - 2026-07-30

### Changed
- **high 既定のレビュー構成を縮小し、直列 wave を圧縮**（レビュー時間・トークン削減。品質側の補償層＝反証 / skeptic / 最小保証 / specialist トリガー感度は据え置き、xhigh/max のフル構成は現行維持で深さは明示 escalation に残す）
  - **effort 適応上限の正本を triage-guide `## 7` に集約**: high は explorer 4 / reviewer 6 / specialist 3、xhigh・max は従来どおり 6 / 10 / 6。上限超過の観点は近接観点バンドル（1 体 3 観点まで。bug-detection / security / spec-compliance / claude-md-compliance は単独維持）で可能な限り吸収し、容量（単独 4 + バンドル枠 = high 最大 10 観点）を超えた分は missing_coverage として欠損観点セクションに明示する。バンドル時の出力規約（focus キーは原観点・観点ごと独立列挙・自己フィルタ禁止）を reviewer-prompts `## 3` 冒頭に規定
  - **冗長ペアを xhigh/max 専用化**: high 以下はペア条件成立時も 1 体とし Angle A/B を両方内挿（reviewer 1 体あたりの固定注入コンテキスト＝diff + PR コンテキスト + AGENTS.md の複製数が減る）。反証 confirmed による補償は報告マトリクス通過見込み帯に限られ、**閾値直下の指摘をペアの +15 が押し上げていた効果は補償されない**（この帯の recall 低下は縮小のコストとして許容し severity 別件数で監視。「ペア合意 +10」「片方のみ -5」は angle 内挿 1 体に適用しないことを scoring-guide に注記）
  - **specialist の束ね起動**: high 以下は複数 red-flag ヒット時に 1〜2 体へテンプレート連結注入（guardrail-bypass のみ単独維持）。トリガー感度（検出正規表現）は不変
  - **Phase 5.5/4.5 を high で 1 段圧縮**: 追加 explorer を廃し、再起動 reviewer（最大 3 体）が unmet ターゲットを自力探索してから confidence を再評価（sonnet 経由の要約受け渡しロスも解消）。xhigh/max は現行 2 段を維持
  - **観点カバレッジ検算を Phase 0 直後へ前倒し**（orchestration-guide `## 8` を 8a 起動前検算 / 8b 事後突合に分割）: 漏れ focus は本隊 wave に合流し、旧 5.7/4.7 の事後補完起動（直列 wave 1 本）を廃止。事後は logging のみの突合に（issue #69 の常時検査の意図は 8a で維持）。`default-mode` 以外（emergency / doc-review / dba / supply-chain / skip）では検算による構成追加を行わず missing_coverage 記録のみ（モード構成の優先を維持）。旧 5.7 の「失敗 reviewer の補完起動」は wave 削減とのトレードオフで廃止（8b に明記。失敗 focus は欠損観点として必ず可視化）

### Added
- **`review:completed` payload に計測フィールドを追加**: `effort`（実行時 effort での層別用）/ `duration_min`（Step 1 で開始時刻を TMPDIR 配下のファイルに記録し publish 時に算出。シェル変数受け渡しは Bash 呼び出し間で消えて epoch/60 のゴミ値になるため禁止と明記。欠測は -1）/ `agents`（explorer / reviewer / specialist / round2 / verify の実起動体数）。縮小のロールバック判断は `agents` フィールド存在を版マーカーに、xhigh/max 明示実行を対照群として縮小後サンプル内で比較する（旧 payload は effort 層別不能のため基準に使わない。判定 jq を triage-guide `## 7` に同梱）

## [2.38.2] - 2026-07-29

### Changed
- **review SKILL.md の締めフロー 1〜3 を `references/closing-flow-guide.md` に分割**（skill-size warning 対応: 本文 506 行 → 377 行）。精査（1）は指摘ありのときのみ実行、1・2 は `--emergency` でスキップ、ドラフト生成（3）は Approve 系でも到達するが AskUserQuestion で opt-out できる末端フローであり、progressive disclosure の押し出し対象（docs/skill-writing.md の branch 判定）。SKILL.md 側には実行条件・実行順・「残存」確定集合の定義を残し、AskUserQuestion 文言・3 分類基準・パターン×voice 表・writing-polish 推敲手順を reference 側へ移した。挙動の変更なし。reply-tone-guide の writing-polish 正本参照も追随

## [2.38.1] - 2026-07-29

### Fixed
- **並列起動の実現手段を明文化**（GitHub issue #95）。「並列起動する」という指示に対し実現手段（**同一アシスタントメッセージ内に対象フェーズの全 Agent call を並べて一括発行する**）が未記述で、orchestration-guide `## 0` の同期起動ルール（`run_in_background: false`）を素直に読むと 1 体ずつの逐次実行が仕様準拠に見えていた（実測: 12 体レビューが相内最長 20.9 min で済むところ逐次合計 72.9 min、約 3.5 倍）。`## 0` に「並列発行の明示」段落を追加し、取りこぼし防止（`run_in_background: false`）と並列性（同一メッセージ一括発行）が直交する独立の要件であることを明記。review / self-review 両 SKILL の explorer / reviewer 起動 bullet と guide `## 6`（追加 explorer）/ `## 10`（反証）の起動手順にも一括発行の 1 行を追加。単体起動フェーズ（meta-reviewer / 冷や読み skeptic = issue 記載の `## 9`）は適用対象がないため対象外と明記

## [2.38.0] - 2026-07-28

### Added
- **worktree teardown 連携を追加**（worktree 削除の独立した 2 トリガー点のうち「レビュー完了後」側。Issue 完了後側は issue-workflow:issue-maintain 1.3.0 が担う）
  - self-review Step 8: 非 embed・worktree 内・worktree-setup マーカー（`envs/.backend.env.worktree`）あり・clean tree・dev-workflow 有効（enabled-only 判定）の全条件成立時、修正方針フロー完了後に AskUserQuestion（残す / 削除する）で確認し、削除選択時は `dev-workflow:worktree-teardown` を Skill 起動する。allowed-tools に Skill を追加（command 側も同期）。embed 契約（Step 1）にも Step 8 skip を明記
  - review 締めフロー 6: ExitWorktree 後に PR ブランチへ紐づく開発用 worktree を「ブランチ一致 + `.claude/worktrees/` 除外 + worktree-setup マーカー」の 3 条件で検出し、`/worktree-teardown` の実行を案内する（ブランチ一致だけではレビュー用一時 worktree を誤検出するため。teardown は worktree 内からしか実行できないため自動起動せず案内のみ・非ブロッキング）
  - `_requirements` / check-deps.sh に dev-workflow（optional plugin）を追加

## [2.37.5] - 2026-07-28

### Changed
- **reviewer fan-out の effort を実行時 `${CLAUDE_EFFORT}` 連動に変更**（review / self-review 共通）。従来の固定 `xhigh` から、既定パス（low/medium/high）は `high`、明示 escalation（xhigh/max）時のみ `xhigh` に。reviewer は全レビューで必ず走る最大コスト項のため最大のコストレバー（max→xhigh に続く 2 段目）。根拠は Opus 5 のレビュー系低 effort 耐性 + 反証/skeptic/meta の補償層（これらの `max` は据え置き）。Round 2 再起動・カバレッジ補完起動は「初回 reviewer と同 effort」に統一。効果は review:completed メトリクスで監視し悪化時は差し戻す

## [2.37.4] - 2026-07-28

### Changed
- orchestration-guide のオーケストレーター effort 説明を Opus 5 基準に更新（既定 `high` は Opus 4.8 と同値のため運用は不変。ドキュメント上の世代表記のみ）

## [2.37.3] - 2026-07-23

### Changed
- Issue ファイル必読フローの併用プラグイン参照を linear-workflow / indie-workflow から issue-workflow に更新（統合プラグインへの移行。dir スキャン（.claude/indie・.claude/linear）はデータ dir 温存により無改修）

## [2.37.2] - 2026-07-22

### Fixed
- **triage-guide.md の Phase 参照 typo を修正**（skeptic の effort ゲート説明が「既存 5.6/5.8 と対称」となっていたが 5.8 は skeptic 自身。SKILL.md と同じ「5.6/5.9」に統一）
- **緊急モードのスキップ対象列挙を 5.7〜5.9 追加後の実態に更新**（triage-guide と SKILL.md 本文が「Phase 5.5 / 5.6」のみ列挙していたが、5.7 カバレッジ self-check / 5.8 冷や読み skeptic / 5.9 反証レイヤーも各スキップ条件で --emergency を含む）
- **最小保証の reviewer 名に focus 語彙の対応を併記**（reviewer-bugs = bug-detection / reviewer-claude-md = claude-md-compliance。findings JSON の focus 語彙との二重語彙による混乱を防止）
- **self-review レポート例の MAJOR 指摘の連番重複を修正**（CRITICAL 例と同じ「3.」だったのを「4.」に。連番は findings JSON の id と 1:1 契約のため例の誤りが伝播しやすい）
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [2.37.1] - 2026-07-22

### Fixed
- **`scoring-guide.md` の surface-aware 閾値の根拠 ADR 参照が廃版を指していたのを修正**。`ADR-20260703155637` は同日に `ADR-20260703204045`（Enforcement 訂正版）へ supersede されており `status: superseded` だが、現行仕様書が旧 ID を引用したままだった。参照先を accepted 側の `20260703204045` に更新した（CHANGELOG 内の過去エントリは当時の記録として旧 ID のまま残す）
  - supersede 時に**被参照側の更新が漏れる**構造的な穴の実例。adr-keeper の supersede 機械化は「新規作成 + 旧 ADR の 4 フィールド更新」までで、外部からの被参照を追跡していない

## [2.37.0] - 2026-07-17

### Added
- **投稿コメントドラフトに重大度・確信度・マージブロッカー可否のメタ行を必須化**（GitHub issue #88）。レポート本体には `[confidence][severity]` が載るが投稿コメントには引き継がれず、著者が対応の優先度を判断する材料が届いていなかった。reply-tone-guide `0.5` を新設し、締めフロー 3 の生成手順と出力例にも反映:
  - 書式は本文冒頭に 1 行（`**重大度: CRITICAL / 確信度: 90 / マージブロッカー: はい**`）。値はレポートの確定値（精査で降格していれば降格後）を引き継ぐ
  - マージブロッカー可否は severity から**決定的に導く**（BLOCKER / CRITICAL → はい、MAJOR / MINOR → いいえ）。scoring-guide「レビュー結論（総合判定）」と同じ導出で、文面ごとに判断しない
  - **適用範囲は「レビュアーとして自分の指摘を著者に伝える文面」に限る**。判定はパターン番号ではなく **voice（文面の声）** で行い、voice は指摘の出所で決める（こちらのレポート由来＝レビュアー発信 / 他者の review comment への返答＝著者発信）。同じ 2.5 でも `[re-flag]` 経由はレビュアー発信・本来の用法は著者発信に分かれるため、パターン番号だけでは決まらない。締めフロー 3 のパターン選択表に voice 列を追加して対で決めさせる
  - 対象外は著者発信の文面（相手の指摘を自分がスコアリングして返す形になり `0.2` の敬意と衝突する）/ 承認コメント（Approve 確定でブロッカーが存在しない）/ 5 章の例外 / 2.6 の全面解決の確認文（残存指摘がなく埋める確定値が存在しない）
  - confidence 80 未満・反証メモ付きの指摘は未確定である旨を 1 文添える（数値だけ出して断定で押し切らない）
- **著者への配慮をドラフト提示前のチェックリストとして明示**（issue #88）。方針は `0.2` / `1.1` / `1.3` に既出だったが生成時に一貫適用されていなかったため、reply-tone-guide `0.6` に自己点検項目（謝辞 / 敬称 / 判断委譲の余地 / 既存対応への言及 / 人でなくコードへの指摘 / 良い点 1 文 / 署名）として列挙し、1 つでも欠けたら直してから提示することを締めフロー 3 に規定した
  - **適用範囲は 0.5 と同じ**（承認コメント・5 章の例外は署名のみ必須）。0 章は「1〜5 章より優先する」ため範囲を書かないと、5 章の「緊急性の高い指摘への返信は感謝表現を最小化」「typo 返信は 1 文で十分」という特則を 0.6 の謝辞・判断委譲の必須化が無効化してしまう

### Changed
- **ドラフト提示前に `writing-polish` を通すことを必須化**（issue #88）。締めフロー 3 に推敲規定がなく冗長な初稿がそのまま提示され、ユーザーが都度短縮を指示していた。pr-creator と同方式の dormant 連携（`--embed --tone review`）で soft 委譲し、未インストール時のみ skip して従来どおり提示する（プラグイン独立性・後方互換 100%）。推敲結果がメタ行・署名・謝辞・敬称・判断委譲を落としていたら破棄して元案を使う
  - `_requirements` に `writing-polish`（`required: false`）を追加、review skill / command の allowed-tools に `Skill` を追加

## [2.36.1] - 2026-07-16

### Fixed
- **fanout した agent の結果取りこぼしを修正**。CC 2.1.198 で Agent tool の既定が background 実行に変わり、`run_in_background` 未指定の explorer / reviewer / meta-reviewer / skeptic / 反証エージェントがすべて background で飛んでいた。オーケストレーターは「完了を待つ」つもりでも同期的には待てず、完了前に次フェーズへ進んで agent の出力を取りこぼしていた（「反応が返ってこない agent」問題。結果自体は tool result として後から返るが、消費するフェーズが先に走ってしまう順序の問題）。orchestration-guide `## 0` に「全 agent 起動で `run_in_background: false` を必ず明示する」横断ルールを追加し、review / self-review の explorer・reviewer 起動手順にも明記した

## [2.36.0] - 2026-07-15

### Changed
- **reviewer 本体の effort を `max` → `xhigh` に変更**（review / self-review）。**reviewer は全レビューで必ず走り体数も最大（典型 2〜10 体）＝総コストの最大項**なのに対し、v2.34.0 が既定 opt-in 化した meta-reviewer / 冷や読み skeptic は内容条件を満たしたときだけ 1 体走る層で、その内容条件（BLOCKER/CRITICAL 検出）の充足率も 20 件中 6 件＝30% にとどまる `[unverified: gist 集約のうち adversarial_verify 規約追加(2026-06-24)以降の 20 件。events.jsonl は gitignored のため repo からは検証不能]`。つまり v2.34.0 の変更は**削減量が小さいまま、high-risk 変更での見落とし側の保険だけを落としていた**。`max` からの 1 段引き下げは全レビューに効く**最大の**コストレバーになる:
  - adaptive deepening の reviewer 再起動（orchestration-guide `## 6`）と観点カバレッジ・セルフチェックの追加 reviewer（`## 8`）も初回 reviewer と同 effort に揃えて `xhigh` に変更（非対称な深さの指摘が同じ confidence 軸で合流するのを避けるため）
  - **独立検証レイヤー（meta-reviewer / 冷や読み skeptic / 反証エージェント）は `max` 据え置き**。据え置きの根拠は体数ではなく**誤判定コストの非対称性**（反証の誤却下は指摘を落とし＝消えるのは MAJOR/MINOR のみ、BLOCKER/CRITICAL は係争注記が機械保証される／skeptic の見落としは recall 補強そのものを無効化する）。**下げるのは全レビューで必ず走る常時レイヤー、据え置くのは誤判定コストが非対称な検証レイヤー**という切り分け
  - CLAUDE.md モデルルーティング規約「判断・検証は `opus` + effort 引き上げ」は維持（`xhigh` は既定 `high` からの引き上げであり、規約は `max` を要求していない）。偽陽性は従来どおり confidence ≥80 フィルタと反証レイヤーで刈り取る
  - **次点の変動費は反証（既定 high でも起動し、体数は指摘ごと 1 体＝指摘数に比例）と specialist（reviewer 枠とは別枠で上限 6 体）**。コストが再び問題化したらこの 2 つが次の検討対象（reviewer の effort が「唯一の」レバーではない）
  - **既知の制約**: `review:completed` payload に `effort` フィールドが無いため、この変更が指摘の質に与えた影響は**事後に相関できない**。効果測定を要する場合は payload への `effort` / `agent_count` 追加が前提になる

## [2.35.1] - 2026-07-15

### Fixed
- **`recall_skeptic.findings_added` の帰属が失われ、skeptic の価値率が系統的に 0 へ潰れていた問題を修正**。実測（gist 集約 69 件）で `fired=true` 4 件すべてが `findings_added=0` だったが、これは「skeptic に価値がない」ことの証拠になっていなかった。由来の帰属チェーンが 3 箇所で切れており、**「価値ゼロ」と「帰属の喪失」を区別できない**状態だった:
  - **レポート書式に由来タグの居場所が無かった**。`reviewer-prompts.md` は skeptic に「各指摘の冒頭に `[recall-skeptic]` タグを付ける（由来を追跡するため）」と指示していたのに、Step 7 / Step 6 のレポート書式のタグ枠は `[confidence][severity][カテゴリ]` の 3 つだけで、由来タグはレポートを書いた時点で消えていた。書式に由来タグを明記し、実例も追加してレポート契約の一部と位置づけた
  - **dedup でタグごと消えうる**。`orchestration-guide` の「重複は dedup（同一ファイル ±5 行 + 類似内容）」はどちらが生き残るか未規定で、reviewer 指摘と重なると skeptic の寄与が不可視になった。**残す側へタグを引き継ぐ**ことを規定
  - **publish が計測点から遠すぎた**。Phase 5.8 → Step 6 scoring（計測点）→ 締めフロー 4 publish と 200 行以上離れ、間に精査・解説・ドラフト生成という指摘リストを書き換える対話ステップが 3 つ挟まる。かつ payload は LLM が手で JSON を組む。両フィールドを「**Step 7 で最初に出力したレポート本文のタグ付き指摘を数えて求める**」と再定義し、記憶からの再構成をやめた。計測点（報告マトリクス通過時点＝精査の前＝ Step 7 の初回レポート。精査が再出力する調整後レポートではない）を明示し、精査で取り下げた分を減算しないことを規定。「動的ラウンド」行の `実行（N 件追加）` の N と `findings_added` は同値であり、本文確定後に数えてヘッダへ反映する（二重管理にしない）ことも明記
- **由来タグを 2 種に分離し、価値率の分子から重複を排除**。上記の「dedup 時にタグを残す」規定だけでは、**過少計上（0 潰れ）を過大計上へ反転させるだけ**だった。dedup 規定は重複を残す理由を「fleet 共通盲点でなかったことの記録」と自ら述べており、**重複＝ skeptic が recall を足していない事例**である。それを `findings_added`（＝ triage-guide が読む「価値率」の分子）に混ぜると、skeptic は generalist 一頭で reviewer 最大 10 体と同じ diff を読むため**重複が常態**となり、価値率が 100% に張り付いて「`findings_added=0` が続くなら縮小」の分岐が原理的に発火しなくなる:
  - `[recall-skeptic]` = **skeptic 単独由来**（dedup で重複しなかった＝実際に破った盲点）→ `findings_added` に計上。**価値率の分子はこれのみ**
  - `[recall-skeptic:dup]` = **重複 survivor**（reviewer も到達していた）→ 新設の `findings_overlap` に計上。独立到達の記録として残すが**価値率には算入しない**
- **`attribution_schema` 版マーカーを `recall_skeptic` payload に追加**（常に `2`）。当初は「修正日より前のデータは使えない」と日付で切る注記にしていたが、**日付では原理的に切れない**。マーケットプレイス配布のため未更新マシンは修正日以降も schema 1 の payload を publish し続けるからで、`plugin-manager` による一括更新が前提＝**ラグは常態**（本リポジトリ自身、修正当日まで pre-commit hook が未設定のマシンが存在した）。publish 側が自己申告する版マーカーだけが配布ラグに耐えるため、この方式に変更。`triage-guide` の価値率 jq に `attribution_schema >= 2` フィルタを**式として埋め込み**（散文の警告だけでは、コピペ実行時に汚染データで判断してしまうため）
- review / self-review 対称に反映。self-review 側の publish は Step 6.4（Step 6.5 は構造化 JSON / Step 7 は修正方針確認）

## [2.35.0] - 2026-07-14

### Added
- **返答ドラフト生成の前に「PR・指摘の解説」ステップを追加**（review SKILL.md の締めフロー）。従来は精査の直後にいきなり返答ドラフトの要否を訊いていたため、指摘の背景を理解しないまま返答方針を決める必要があった。締めフローを `1. 指摘の精査 → 2. 解説 → 3. 返答ドラフト → 4. Event Bus publish → 5. ExitWorktree` に組み替え、解説を判断材料の供給ステップとして挟む（既存の 2〜4 を 1 つずつ繰り下げ。全ステップ番号を記すのは、次回の挿入時に繰り下げ漏れを CHANGELOG 側から検知できるようにするため）:
  - **解説対象は AskUserQuestion の複数選択（`解説不要` / `PR について` / `指摘について`）**。`指摘について` は残存・降格した指摘が 1 件以上あるときのみ提示するため、指摘 0 件でも 2 択が成立し PR 単体の解説は可能。`解説不要`（既定）が選ばれたら他と同時選択でも優先して 3 へ抜ける
  - **選択肢は指摘件数に比例させない（最大 3 択）**。AskUserQuestion の選択肢上限（4 個）と衝突するため「指摘ごとに選択肢を並べる」形は採らず、`指摘について` 選択時に指摘番号を free-text 入力（例: `1,3,5` / `all`）させる 2 段構えにした。既存の返答ドラフト「個別選択」と同じ入力パターンで揃えている。`all` = 残存・降格した指摘の全件（取り下げ済みは含まない）、範囲外番号・空入力は対象なしとして扱う
  - **指摘の解説は `なぜ問題か` / `直し方` / `取り下げ材料` の 3 点**。取り下げ材料は「取り下げを推す」のではなく、著者が指摘を覆すための材料を対称に置く目的（Step 1 の必要性ゲートと同じく人間が覆せる形を保つ）。PR の解説は `変更の全体像` / `設計意図` / `変更の流れ` / `影響範囲`
  - **解説はチャット出力のみで投稿コメントではない**ため `reply-tone-guide.md` は適用しない（Claude 署名・敬語テンプレは不要）。Step 1 と同じ断定抑止ルール（`file:line` 典拠 / 外部状態は「要確認」/ `[unverified:]` の引き継ぎ）は継承する
  - 解説の結果ユーザーが取り下げ・降格を望んだ場合は Step 1 の 3 分類に差し戻して調整後レポートを再出力し、以降の返答ドラフト・publish は再確定値を使う
  - `--emergency` 時はスキップ（Step 1 と同じ扱い）。self-review は締めが「修正方針確認」で返答ドラフトを持たないため対象外（review / self-review の意図的な非対称）

### Fixed
- **返答ドラフトの AskUserQuestion が `Approve with nits` の全ケースで選択肢 5 個になり仕様上限（4 個）を超えていた問題を修正**。`scoring-guide.md` の総合判定表は `Approve with nits` を「BLOCKER/CRITICAL なし・MAJOR が 1 件以上」または「MINOR のみ残存」と定義しており、**`Approve with nits` ≡ 残存指摘 ≥ 1** が成り立つ。このため `承認コメント`（Approve 系のみ提示）と `重要指摘のみ` / `全件` / `個別選択`（残存指摘ありのみ提示）の条件が常に同時成立し、`不要` と合わせて 5 個が提示条件を満たしていた。エッジケースではなく最頻の承認経路の全ケースで発生し、LLM は仕様エラーを避けるためどれか 1 つを独断で落とすしかなく、どれが消えるかは非決定的だった（silent degradation）:
  - 修正は `重要指摘のみ` の提示条件を「残存指摘があるとき」→「**BLOCKER / CRITICAL が 1 件以上あるとき**」に締める 1 行。`Approve with nits` は定義上 BLOCKER/CRITICAL を持たないため、この選択肢はそもそも空振りする死に選択肢だった。上限超過と死に選択肢が同時に解消し、`承認コメント` を Approve with nits に残せる（`承認コメント` 側を落とす案より選択肢の意味が保たれる）
  - 再発防止として options 直下に**選択肢数の不変条件テーブル**（Approve=2 / Approve with nits=4 / Needs work=4）を明記。提示条件を変更する際の再検算を強制する
  - self-review 側の AskUserQuestion は 3 択固定・無条件のため同種の超過なし（確認済み）
- **Step 1 で「そのまま」（精査なし）を選んだ場合の「残存」の定義を明示**。後続ステップ（解説の `指摘について` 提示条件・返答ドラフトの実行条件）が「残存・降格した指摘」を参照するが、精査を行わなかった経路ではこの語が未定義で、指摘が N 件あっても条件を満たさない読みが成立しえた。「精査を行わなかった場合は報告マトリクス通過後の全指摘を残存とみなす」と定義を追記した

## [2.34.0] - 2026-07-14

### Changed
- **既定 effort を `xhigh` → `high` に変更**（review / self-review 両 SKILL.md）。frontmatter の `effort: xhigh` は Opus 4.7 向け orchestrator 調整（`097e4f7`）の名残で、その後に追加された effort ゲート付きレイヤー（meta-reviewer / 冷や読み skeptic）の設計上の既定「`high`」と矛盾し、本来 opt-in のはずの高コスト独立レイヤーが常時起動していた。triage-guide が一貫して呼ぶ「high（既定）」に実装を揃える:
  - **meta-reviewer（Phase 4.6/5.6）と冷や読み skeptic（Phase 4.8/5.8）が既定で不発**になる（従来通り xhigh/max を明示すれば escalation として起動）。反証レイヤー・adaptive deepening（high で起動）と reviewer 本体（`effort:max`）は不変のため、偽陽性フィルタ・レビュー品質のコアは落ちない。落ちるのは high-risk 変更での見落とし側の保険のみ
  - 副次効果として issue #77 の計測前提（skeptic の `skip_reason="effort"` 蓄積による high 昇格判断）が復活する。実効既定が xhigh だと skeptic は毎回起動し `skip_reason="effort"` が永久に貯まらなかった
- **モデルルーティングから `fable` を全廃し `opus` に統一**（プロジェクト方針）。meta-reviewer を `model: fable` → `model: opus` に変更（review / self-review / orchestration-guide）。design doc `20260703` が「独立検証は強モデル＝opus」と結論済みの方針とも整合。plugin description の `meta-reviewer(fable)` 表記も更新

## [2.33.2] - 2026-07-08

### Fixed
- **冷や読み skeptic の silent skip を修正**（issue #85）。high-risk surface HIT なのに Phase 4.8/5.8 が effort/config/scope スキップで畳まれた際、その事実が Step 6/7 の human レポートにも `missing_coverage` にも出ず観測不能だった問題を修正:
  - Step 6/7 レポートの「動的ラウンド」行に **冷や読み skeptic の起動有無を明示**（実行＝追加件数 / 未起動＝skip 理由 / 非該当＝surface なし）。従来は Meta-reviewer と反証のみで skeptic 項目が欠落していた
  - Phase 4.8/5.8 のスキップ条件に該当しても、surface 判定（正規表現・grep で安価）は Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** し、surface=true なら未起動事実と skip_reason を human レポートに必ず出す契約を追加（`--embed` / event 発火の有無に依存しない observability）
  - orchestration-guide `## 9` / triage-guide `## 8.5` の「失敗時のみレポート」文言を「失敗・スキップのいずれでも」に拡張
  - これにより #77（high 昇格判断）の `recall_skeptic.skip_reason` 計測が headless 通常実行でも成立する

## [2.33.1] - 2026-07-07

### Changed
- **review / self-review SKILL.md を references/ に分割**（review 531→418 行 / self-review 477→397 行）。実行フェーズの共通詳細（PR 番号注入・Issue ファイル必読フロー・AGENTS.md 階層動的選択・部分失敗耐性・auto-retry・動的ラウンド 5.5〜5.9 / 4.5〜4.9 の実行手順・Vault 照合・訂正の伝播前ガード）を新設の `references/orchestration-guide.md` に正本として集約し、SKILL.md 本文は高レベルワークフロー（Phase 一覧・スキップ条件・スコアリング規則・レポート契約・AskUserQuestion 仕様）に絞った。挙動の変更なし

## [2.33.0] - 2026-07-05

### Added
- **`review:completed` payload に `recall_skeptic` 実行記録を追加**（`surface` / `fired` / `skip_reason` / `findings_added`）。冷や読み skeptic（Phase 5.8/4.8）を effort=high へ昇格するかの計測基盤:
  - skeptic が effort / userConfig でスキップされた場合も**正規表現部分の surface 判定だけは必ず実施して記録**する（「surface=true なのに effort ゲートで走らなかった頻度」が昇格判断の核心メトリクスのため）
  - `triage-guide.md` §8.5 に「high 昇格の判断基準」を追記（events.jsonl の jq 集計 2 本 + 判断の目安）
  - review / self-review 両 publisher で同一フィールド名（subscriber が publisher を区別せず集計可能）。新規フィールド追加のみで旧 subscriber への影響なし

## [2.32.0] - 2026-07-03

### Added
- **high-risk コードでの recall 補強 Tier1（冷や読み skeptic + surface-aware 閾値・GitHub issue #75）**。段階投入（Tier3→2→1）の最終段。トリアージが絞り込んだ結果 fleet 全員が同じ盲点（層跨ぎ値フロー）を共有して high-risk バグを見落とす false negative を、recall 側の独立レイヤーで救済する:
  - **冷や読み skeptic ラウンドを新設**（review=Phase 5.8 / self-review=Phase 4.8）。high-risk surface を含む変更に限り、findings も reviewer 推論も渡さない独立 skeptic を `model: opus` で 1 体起動し、fleet 共通盲点を冷や読みで破る。反証レイヤー（false-positive 潰し）の鏡像＝ false-negative hunter。テンプレートに敵対的入力逆算の核を内挿し独立性に「破り方」を持たせる（`reviewer-prompts.md` `## 8`、`triage-guide.md` `## 8.5`）
  - **surface-aware 報告閾値を追加**（`scoring-guide.md`、ADR-20260703155637）。high-risk surface（DB 書込 / 金銭・数量 / 認可、または PR 自己申告 D1-High）に限り CRITICAL 80→70 / MAJOR 95→85 に緩め、recall を非対称補正。precision の本丸（≤40 好みクランプ・高 severity 非削除・specialist 反証除外）は不変で、緩和は適用順序 手順 7 の一点のみ
  - **surface 判定ロジック**: performance 観点の INSERT/UPDATE 正規表現を surface 判定に転用 + ORM 書込 API + D1-High 検出（`reviewer-prompts.md` `## 2.5`）。ORM 抽象越えの偽陰性は reviewer の `[surface:high-risk]` フラグを保険に OR 判定
  - **F4 吸収整合**: surface-aware で新規報告化する CRITICAL 70-79 / MAJOR 85-94 帯を high でも反証レイヤーの対象に含める例外ゲートを追加（`triage-guide.md` `## 9`）
  - **反証レイヤーを Phase 5.9 / 4.9 にリナンバリング**（skeptic を 5.8/4.8 に挿入したため）。userConfig に `enable_recall_skeptic`（既定 true、effort xhigh/max で動作）を追加。skeptic 失敗時は `missing_coverage` に記録し起動条件を満たしたのに未実行だった事実をレポートに必ず出す
- 設計は design doc `.claude/designs/20260703-code-review-recall-high-risk-surface.md`（Tier1 完了で phase: current）

## [2.31.0] - 2026-07-03

### Added
- **high-risk コードでの recall 補強 Tier2（explorer/reviewer プロンプト・GitHub issue #75）**。段階投入の 2 段目として層跨ぎバグの捕捉手段を追加:
  - **value-flow-trace explorer focus を新設**（`explorer-prompts.md`）。1 つの値が schema→domain→DB / FE→BE をどう通るかを入口から末端まで辿り、前提がズレる境界を判定せず可視化して bug reviewer に集約注入する。`triage-guide.md` の explorer 判定（層跨ぎの値フロー）に dispatch 導線を追加
  - **explorer 出力に「要注意シグナル」欄を追加**（`explorer-prompts.md`）。判定禁止のまま suspicion を落とさず reviewer に運ぶ
  - **bug-detection に「敵対的入力逆算」を追加**（`reviewer-prompts.md`）。受理入力の端点（`''` / 0 / null / 最大長 / 部分入力）を末端の DB 制約まで前進させて素通り経路を探す（#1 直撃）
  - **claude-md-compliance に「帰結接続の義務化」を追加**（`reviewer-prompts.md`）。パターンの有無でなく共有機構が実際に呼ばれ帰結を生むかまで見る（#7 直撃）
- Tier1（冷や読み skeptic + surface-aware 閾値）は未実装。設計は `.claude/designs/20260703-code-review-recall-high-risk-surface.md`

## [2.30.0] - 2026-07-03

### Added
- **high-risk コードでの recall 補強 Tier3（プロンプトのみ・GitHub issue #75）**。実レビューで xhigh フルパイプラインが high-risk な DB 書込 PR の実バグ（空文字が numeric 列へ INSERT → 500）を見落とした事例を受け、段階投入（Tier3→2→1）の先行分として reviewer プロンプトを補強:
  - **CRITICAL 以上に「発現シナリオ / テスト未検知理由」を必須化**（`reviewer-prompts.md` 出力フォーマット）。端点の具体値と既存テストが捕まえられない理由を書けなければ severity 過大評価を疑う自己較正欄
  - **spec-compliance に「契約の前提を呼び出し側で実地検証せよ」を昇格**（既存の「整合性の罠」注記を focus プロンプトへ）。宣言と整合の確認を正しさの確認の代用にしない
  - **comment-accuracy に「メッセージ時制 × 制御フロー照合」を追加**。ログ/エラーメッセージの主張する事後状態とコードが実際に到達する状態のズレを検出
- 設計は design doc `.claude/designs/20260703-code-review-recall-high-risk-surface.md`（Tier1/2 は未実装。ADR-20260703155637 で surface-aware 報告閾値の判断を記録）

## [2.29.1] - 2026-07-02

### Fixed
- **allowed-tools に `Agent` 未宣言を修正**。review / self-review の各 SKILL.md とペアの command（`commands/review.md` / `commands/self-review.md`）は explorer / reviewer / meta-reviewer / 反証エージェントを並列起動するのが核心なのに `Agent` を allowed-tools に宣言していなかった。4 ファイルすべてに追加
- **`/review` command の argument-hint に `--emergency` を追記**。skill 側では受け付けているが command のヒントに載っていなかった
- **AGENTS.md 階層選択の実装不一致を修正**。review Step 4.9 / self-review Step 3.9 の「Glob で発見」記述を、直後のコード例（`git diff | dirname` の bash ループ）に合わせて「Bash で探索」に修正

### Changed
- **plugin.json の description を圧縮**。変更履歴が約 3000 字堆積していたのを、機能を端的に説明する数行に圧縮（履歴は CHANGELOG が正本）

### Added
- **コスト×精度 10 原則の採用/不採用を SKILL.md に明記**。review / self-review に採用原則（1 ファネル / 2 二軸スコア / 3 段階予算 / 4 モデルルーティング / 7 敵対的独立検証）と捨てた判断（5/6/8）の宣言行を追加（ルート CLAUDE.md 指針に準拠）
- **kvault を `_requirements` に宣言**。self-review Step 1.5 の Vault 照合で使う任意の外部 CLI を `cli_tool` / `required: false` として宣言し、`hooks/scripts/check-deps.sh` に `check_cli "kvault"` を追加（未導入時は skip、後方互換）

## [2.29.0] - 2026-06-26

### Added
- **指摘の精査ゲート（必要性の第3軸 / review skill Step 7）**。返答ドラフト生成の選択肢を出す前に、報告された指摘を「**本当に著者の対応に値するか（必要性 = signal/noise）**」の観点で精査するか AskUserQuestion で確認するステップを追加。Step 6（severity×confidence の機械フィルタ）・Phase 5.8 反証レイヤー（正しさ＝偽陽性の独立検証）と直交する第3軸を人間に委ねる
  - **既存機構との非重複**: 反証は「正しいか」、精査は「正しいとして対応に値するか」。settled な設計判断の蒸し返しや既存コード由来の nit は反証では refuted にならない（事実は正しい）が必要性軸では取り下がる。≤40 好みクランプを擦り抜けた残滓を人間ゲートが補う
  - **再評価ロジック**: 取り下げ（純粋な好み / settled な蒸し返し / 実害極小 MINOR nit / 既存コード由来）/ 降格（severity 過大 → 1 段階下げ + Optional:・Nit:）/ 残存（実害・規約違反の根拠あり）の 3 分類。**BLOCKER / CRITICAL は降格はあっても取り下げない**（反証レイヤーの「高 severity 非削除」不変条件を継承）。取り下げは理由明示で人間が覆せる reversible 設計
  - **下流反映**: 精査後（post）の確定件数を返答ドラフト対象・総合判定再導出・`review:completed` publish に反映。指摘 0 件・`--emergency` 時はスキップ
- **投稿コメントのトーン徹底（reply-tone-guide.md `## 0 必須ルール`）**。返答コメント・承認メッセージの両方に適用する最上位ルールを新設
  - **Claude の署名**: Claude 作成のコメント（ドラフト含む）末尾に署名 1 行 `— Claude Code によるレビュー` を付す（**絵文字なし** — 既存の emoji 禁止規約に準拠。標準の `🤖 Generated with Claude Code` は使わない）。人間が大幅に書き換えた場合は不要
  - **PR 作成者・他レビュアーへの敬意**: 敬称を添える / 他レビュアーの指摘を否定せず議論を立てる方向で書く
  - **簡潔さ**: 要点を先頭に・1 コメント 1 論点・専門用語を噛み砕く
  - **良い点を 1 文で称賛**: 中身のない称賛は禁止、file:line に紐づけ、SKILL.md「良かった点」と同基準
- **承認メッセージパターン（reply-tone-guide.md `### 2.7`）**。総合判定が Approve / Approve with nits のとき投稿する承認コメント（簡潔な承認 + 良い点 1 文 + nits は任意と添える + 署名）のテンプレを新設。Needs work では出さない。返答ドラフト step を「投稿コメントドラフト」に拡張し、Approve 系では指摘 0 件でも承認コメントを生成可能に

## [2.28.0] - 2026-06-26

### Added
- **doc-substance を 2 軸に拡張（文書としての成立性 = B 軸を追加）**。従来の doc-substance は `comment-accuracy` の「主張⇔コード一致」を doc 本文へ一般化したもので、**「書かれた主張が正しいか」（A 軸）だけ**を見ており、「**書かれるべきことが書かれ、読み手が目的を達成できる構造か**」という文書としての構造的妥当性が素通りしていた（完全性・doc 種別適合・読み手前提・WHY 根拠・ナビゲーションがどのツールにも担当されない gap だった）。Diátaxis / Write the Docs の functional quality 観点を取り込み、prose polish（語句・トーン）では捕まらない構造欠陥を検出可能にした
  - **B 軸の検出対象（reviewer-prompts.md `doc-substance`）**: 完全性（missing content: 手順の前提・成功条件・失敗時挙動の欠落、パラメータ網羅、**コードに追加された新 API / フラグに対応する doc の不在**、ユースケース例の不在）/ doc 種別適合（how-to に理論混入・reference に手順混入・design doc に代替案比較なし・ADR に context/帰結なし）/ 読み手前提・順序（prerequisite 後出し・対象読者/前提環境の不明示）/ 判断根拠 WHY（規約・閾値・制約に「なぜ」がない）/ ナビゲーション（新規ページ・ADR の index/上位リンクからの孤立）。A 軸にも「例の整合（コード例 vs 現行 API、code:line）」を追加
  - **2 軸で裏取りの相手が違う**: A 軸は code:line（内部矛盾は doc:line ×2）、**B 軸は doc:line（欠落・誤配置・孤立の発生箇所）＋ 破られた期待（doc 種別の契約 / その doc が宣言する対象読者・スコープ / 手順が参照する未記載の前提）**。B 軸はコード照合不要（triage-guide.md grounding 節に分岐を追加。新 API 追加に対する doc 不在の完全性指摘のみ A 軸同様コードを読む）
  - **scoring の好みクランプを 2 軸対応に修正（最重要 / load-bearing）**: 従来は「code:line または doc:line ×2 で裏取りできない doc 指摘は表現の好みとみなし ≤40 クランプ」だったため、**code:line で裏取りできない B 軸（完全性・doc 種別適合等）が生まれた瞬間に好み扱いで除外されていた**。`scoring-guide.md` の doc-substance クランプ条項を 2 軸に分け、**B 軸は doc:line + 破られた期待を示せていればクランプ対象外**に。逆に「語句を最小差分で言い換えれば済む」だけの指摘（writing-polish の領分）は B 軸を騙ってもクランプ
  - **prose polish との分界**: 判別線は「**語句を最小差分で言い換えれば済むか**」。済む → writing-polish、内容の追加・再配置・根拠補完・例修正が要る → doc-substance（triage-guide.md 境界記述に明示）。decided 系 doc（`.claude/adr/**` / `.claude/designs/**`）は既存の design-review soft 委譲が優先
  - **反証レイヤー統合**: `reviewer-prompts.md` `## 7` の doc-substance 反証ブロックに **B 軸の読み替え**を追加（pre-validated=欠落情報が別箇所に実在 / intended=明示的スコープ外 / misread=doc 種別の誤判定 / pre-existing=base から既存。ただし新 API 追加に対する doc 不在は diff が生んだ乖離なので pre-existing としない）。review skill は effort=xhigh 既定のため B 軸 MAJOR も Phase 5.8 で独立検証され、クランプ（一次抑制）＋ 反証（偽陽性摘出）の二段構えになる
  - **severity 目安**: B 軸の致命欠落（手順書の必須 prerequisite/step 欠落で読者が実行不能・コード例が現行 API と食い違い動かない）= CRITICAL、doc 種別不適合・WHY 欠如・完全性の重大欠落・孤立 doc = MAJOR

## [2.27.0] - 2026-06-24

### Added
- **doc-substance 観点（ドキュメント内容妥当性）**。review 系スキルが docs を含む PR を整合性（リンク / 構造 / コード片安全性）だけでレビューし、書かれた内容の本質的な妥当性を見ていなかった問題に対応。`comment-accuracy` の「主張⇔コード一致」を doc ファイル本文へ一般化した観点を追加（`reviewer-prompts.md` `## 3` Focus テンプレート）
  - **検出対象**: ground-truth 正確性（主張がコードと食い違う、code:line 裏取り）/ 規範の正しさ（規約 doc の指示で動かない・既存ルールと矛盾）/ 論理的健全性（自己矛盾）/ 有用性（曖昧・hand-wavy）/ 意味の陳腐化（リンク切れでなく内容の陳腐化）。表現・語句・トーンは対象外（writing-polish の責務）
  - **重要度ゲート（triage-guide.md）**: 起動を「変更ファイル数比率」でなく **doc の意味的重要度**で判定。`doc-review-mode`（`*.md` ≥ 80%）に doc-substance を追加し整合性のみから「整合性 + 内容妥当性」へ。混在 PR（`*.md` < 80%）は観点判定表に `doc-substance` 行を追加（高価値 doc パス〔CLAUDE.md / AGENTS.md / CONTRIBUTING / README / .claude/adr / .claude/designs〕の prose 変更 OR 実質 prose ≥10 行）。ファイル数では小さいが意味的に重要な doc（ADR 1 件 / CLAUDE.md 1 行）の取りこぼしを防ぐ
  - **effort 別起動制御**: low=skip / medium=高価値 doc のみ / high+=全面（反証レイヤーが効かない effort では起動自体を抑制し偽陽性の素通りを防ぐ）
  - **grounding**: 専用 explorer を必須化せず既存の条件付き起動に乗せ、読み取り対象を **diff 変更 doc が参照するコード ∩ リポジトリ実在パス**に限定（信頼できない doc 本文に任意パスを選ばせない）
  - **scoring（scoring-guide.md）**: 裏取り報酬は新規 +15 を作らず既存「explorer 裏付け +10」に統合。根拠なしの論理 / 有用性指摘は既存 ≤40 クランプで除外（doc-substance の MAJOR は既定 effort で反証対象外のためクランプが主たる抑制機構）。裏取りできた内容誤りは CRITICAL 昇格、ただし `git blame` で doc 変更とコード変更の前後関係を検算しコードが doc より古い場合は昇格しない（doc 先取り・コード未追従での誤昇格と高 severity 非削除不変条件への直撃を防ぐ）
  - **反証レイヤー統合**: doc-substance の裏取り CRITICAL は既存 Phase 5.8/4.8 の反証対象に自動的に含まれる（specialist でないため）。反証軸に doc 向け読み替え（misread / pre-validated / intended / pre-existing は git blame でコードと doc のどちらが現在の正かを判定）を追加
  - **dormant 連携**: 決定系 doc（ADR / design doc）は `design-doc` 導入時のみ design-review の minimal / risk チェックリストを内挿（settings.json grep 判定、未導入時は内製代替、スキル間呼び出し非依存）。境界は doc-freshness（frontmatter / link）/ writing-polish（語句）/ doc-substance（本文の主張）で機械的に分離

## [2.26.0] - 2026-06-23

### Added
- **反証レイヤー（adversarial verification / Phase 5.8 / self-review Phase 4.8）**。reviewer が出した指摘を、それを形成していない独立エージェントが報告前に反証する工程を追加。観点カバレッジ self-check の後・スコアリングの前に挿入。meta-reviewer（見落とし＝false negative を足す係）の鏡像で、偽陽性（false positive）を独立に潰す。人間が「これ本当？」と詰めて取り下がる指摘を先回りして摘出する
  - **対象選定（triage-guide.md `## 9`）**: 「詰めると取り下がる」非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）を high 既定で狙い撃ち、xhigh/max で報告ゾーン全体 + MAJOR に拡大。**security specialist 由来（injection / secret-handling / destructive-op / input-validation / guardrail-bypass）は全 effort で対象外**（誤反証で人間の警戒度を下げる代償が非対称）
  - **反証エージェント（reviewer-prompts.md `## 7`）**: reviewer の推論を渡さず（アンカリング防止）コードを独立に読み直す。両方向に file:line 証拠を要求し、「たぶん大丈夫 / おそらく問題」は uncertain 止まり。反証軸は独立性が効くもの（unreachable / pre-validated / misread / pre-existing / intended）に限定し、既存自己検算（invariant 検算 / `[unverified]` クランプ）と重複する軸は再利用。`pre-existing` / `intended` 鮮度は LLM 前に `git show <base>` / `git blame` で機械判定
  - **verdict→scoring 統合（scoring-guide.md `## 反証レイヤーの verdict 反映`）**: 適用順序の冒頭で機械適用。**高 severity（BLOCKER/CRITICAL）の `refuted` は confidence/severity を据え置き本文に `⚠️ 反証メモ:` を付すのみ＝報告から消さない**（false-negative の構造的防止をプロンプトでなく手順で保証）。MAJOR/MINOR の `refuted` のみ confidence −40 で取り下げ（理由をレポート付録に記録、人間が覆せる）。`confirmed` は既存「複数エージェント +15」の発火源として扱い二重計上を排他。`severity-inflated` は既存 severity 調整ルールに統合し二重降格しない
  - **計測**: `review:completed` payload に `adversarial_verify`（confirmed / refuted / uncertain / contested 件数）を review / self-review 両 publisher で追加。後から偽却下率を計測して verdict→delta を調整
  - **userConfig `enable_adversarial_verify`**（デフォルト true、effort high 以上で動作）。`enable_meta_reviewer` と同型運用で無効化可能
  - レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」サマリ行と「🔁 反証で取り下げた指摘」付録を追加。embed JSON は schema_version 据え置き（反証効果は severity/confidence に反映済み、係争指摘は `title`/`impact` に反証メモ）

## [2.25.1] - 2026-06-15

### Changed
- README の confidence 説明を severity × confidence 2 軸マトリクスに更新、主要引数（--emergency / base branch / --staged / --focus / --exclude / --embed）を記載、Version 行を撤去

## [2.25.0] - 2026-06-10

### Added
- **事実主張のツール接地（claim grounding）**（GitHub issue #71）。`reviewer-prompts.md` 共通指示に「事実主張のツール接地」を追加。指摘の load-bearing な事実主張を confidence 確定前に検証可能性で 3 分類（① repo 検証可 → `file:line` 引用必須 / ② 正本 doc 検証可 → spec・PR・Issue・ADR の典拠引用必須 / ③ repo 検証不能 = DB・本番状態・外部数値・運用設定 → 事実として断定禁止）。③ を根拠にする指摘は「要確認（典拠=X）」と明示し confidence ≤75 + `[unverified: ...]` タグを付け、単独根拠で severity を上げない。「内部的に一貫しているが実態と異なる」主張が整合性レビューを素通りする罠も明記
- **scoring の未検証クランプ**（GitHub issue #71）。`scoring-guide.md` に「上限クランプ: 未検証の外部状態主張」を追加。`[unverified: ...]` タグ付き指摘は confidence を `min(値, 75)` に機械クランプ（BLOCKER 級の疑いのみ報告マトリクスを通過、CRITICAL 以下の未検証断定は自動除外）。好みベースクランプ（min 40）と両該当時は低い方を採用。適用順序に未検証クランプのステップを挿入
- **findings 反映段の over-correction ガード**（GitHub issue #71）。`self-review` Step 7 に「訂正の伝播前ガード」を追加。findings をコード/文書本文に反映する前に load-bearing な事実主張を一次ソースで再確認（repo 確認可は Read/Grep で現物確認、repo 確認不能は「要確認」マーカー保持）、暫定入力（「〜かも」）を確定として複数箇所へ伝播しない、訂正は 1 箇所先行確認 → 確証後に展開、複数観点の独立一致は高信頼として扱う。`review` Step 7 の返答ドラフト生成にも未検証主張の断定抑止（`[unverified]` の不確実性を返答に引き継ぐ）を追記

## [2.24.0] - 2026-06-10

### Changed
- **meta-reviewer (Phase 5.6 / self-review Phase 4.6) を `model: opus` → `model: fable` に変更**。全 reviewer の指摘を統合して最終判断する単一インスタンスの判断スロットに、Opus 上位ティアの Fable 5（claude-fable-5）を割り当て、知能上限を最終判定に集中させる。入力は蒸留済み findings、出力は verdict のため Fable の出力単価 2 倍（$50/1M）はトークン量で bounded。並列起動する reviewer (opus) / explorer (sonnet) はコストがボリューム × 単価で効くため据え置き。`effort: max`（adaptive thinking 前提）は維持（Fable は `thinking:{type:"disabled"}` が 400 だが本スロットは該当しない）

## [2.23.0] - 2026-06-08

### Added
- **reviewer 非レビュー出力の検知 + auto-retry**（GitHub issue #69）。`review` Step 5 / `self-review` Step 4 で各 reviewer 出力を機械検証し、`### レビュー結果` 構造と（指摘ありの場合）`[confidence][severity]` タグを欠く非レビュー出力（空応答・system-reminder / skill 案内の断片・tool_use ゼロでの早期終了）を検出したら同一プロンプトで 1 回 auto-retry。retry も非レビュー出力なら `missing_coverage` に記録して欠損観点扱いにし、フィルタ素通りを防ぐ
- **観点カバレッジ・セルフチェックの常時化**（GitHub issue #69）。`review` Step 5.7 / `self-review` Step 4.7 を新設。meta-reviewer の厳しい起動条件（effort=xhigh/max かつ高 severity あり）に依存せず、`triage-guide.md` の観点判定表を実際の diff シグナルに対してメインコンテキストで再評価し、「条件を満たすのに未起動の focus」を検出して `missing_coverage` に追記する（high effort 以上なら 1 体だけ追加起動可）。`--emergency` / `skip-mode` / `--focus`・`--exclude` 指定時はスキップ
- **`self-review` Step 1.5「Vault 照合」**（GitHub issue #68）。`kvault recall` / `/vault-recall` skill を検出（未導入なら no-op skip / 後方互換）、変更ファイルのパス・識別子・技術語で過去のレビュー指摘・落とし穴を retrieval し、`similarity` + gap で関連判断して各 reviewer に `## Vault prior findings` セクションとして注入する。`--embed` 呼び出し（feature-dev Phase 6 等）でも動作。feature-dev Phase 1.6 Vault Recall と同一 retrieval 基盤を呼ぶ対の改善

### Fixed
- **EnterWorktree 配下での `isolation:worktree` agent の二重 checkout 衝突**（GitHub issue #69）。`explorer-prompts.md` / `reviewer-prompts.md` の開始時セットアップを、`{{HEAD_REF}}` と現在 HEAD を比較して一致時は `gh pr checkout` をスキップする形に変更。親 review worktree が PR を checkout 済みのとき、子 worktree での再 checkout が "already checked out at <親worktree>" で失敗する問題を解消（fallback の `git log` 確認に頼らず衝突自体を回避）。`review` SKILL Step 4/5 のプレースホルダ注入に `{{HEAD_REF}}` を追加

### Changed
- **退行（regression）指摘の invariant 検算**（GitHub issue #69）。`reviewer-prompts.md` 共通指示に「退行指摘の invariant 検算」を追加。「旧挙動が失われた → 退行」と判断する前に、その挙動が隣接コード経路（類似関数・兄弟ハンドラ）でも一貫強制される invariant か検算し、特定経路だけの偶発的副作用（incidental）なら confidence / severity を下げる。`scoring-guide.md` の severity 調整に incidental 退行の 1 段階降格ルールを追加。単一経路の旧挙動を invariant とみなして severity を過大評価する誤判定を抑制

## [2.22.1] - 2026-06-05

### Fixed
- `check-deps.sh` の `check_mcp` が user スコープ（`claude mcp add -s user` で `~/.claude.json` の `.mcpServers` に書かれる MCP）を検知できず、設定・接続済みでも「未設定」と誤検知していた問題を修正。既存の `~/.claude/mcp.json` / `.mcp.json` の grep 近似チェックの前に、`jq` で `~/.claude.json` の `.mcpServers` を厳密に確認する処理を前置（grep ではなく `has($n)` を使うのは、`~/.claude.json` に会話ログ等が含まれ単純 grep だと無関係箇所に誤マッチするため）。github を user スコープ追加済み環境で ERROR になる誤検知を解消

## [2.22.0] - 2026-06-04

### Added
- **`modern-web-checklist.md` 同梱 reference**（Chrome [Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance) を [Baseline](https://web.dev/baseline) ベースで照合可能にしたチェックリスト）。`ui-quality` Focus に「自前実装 → ネイティブ API 置き換え」（自前モーダル→`<dialog>`、自前ツールチップ→Popover API + Anchor Positioning、viewport メディアクエリ→Container queries 等）と **Baseline ゲート判定**（Limited availability 機能のフォールバックなし本番投入を MAJOR で検出 / widely available 化で不要になった polyfill 削除提案）を追加。ネイティブ API 化の任意改善は `Optional:` prefix・confidence ≤ 60 に抑え、好み抑制ルール（reviewer-prompts.md「好みではなく原則」+ scoring-guide の confidence クランプ）と整合させた。a11y / セマンティック HTML は既存 ui-quality 本体が担当し二重指摘しない棲み分けを明記

### Changed
- **`web-design-guidelines` 公式 skill 参照のローカル化**。`reviewer-prompts.md`（ui-quality Focus）と `triage-guide.md`（React/Next.js 判定）が参照していた `~/.agents/skills/web-design-guidelines/SKILL.md`（現環境に存在しない dangling 参照・WebFetch 前提）を、同梱の `${CLAUDE_PLUGIN_ROOT}/references/modern-web-checklist.md` に差し替え。外部 fetch 依存と参照切れを解消し、`${CLAUDE_PLUGIN_ROOT}` でポータブル化
- **`context7` の dangling skill 参照を MCP 参照に修正**。`reviewer-prompts.md`（外部ライブラリ最新仕様の確認）が参照していた `~/.agents/skills/context7/SKILL.md`（同じく現環境に存在しない dangling 参照）を、context7 MCP（`resolve-library-id` → `query-docs`）経由の記述に差し替え

## [2.21.0] - 2026-06-03

### Added
- **`--emergency` 緊急レビューモード**（Google eng-practices "Emergencies"）。`review` skill に `--emergency` 引数を追加し、本番ホットフィックス向けに reviewer-bugs + reviewer-security の最小 2 体のみで実行（explorer / 冗長ペア / Phase 5.5 / 5.6 をスキップ、specialist は red-flag 検出時のみ起動）。レポート冒頭に `⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること` バナーを必須化。`triage-guide.md` に緊急モード定義（緊急の定義 / 他モードより優先 / レビューは省略しない原則）を追記
- **`self-review` の修正指針「Fix the code, not the reviewer」**（eng-practices "Handling reviewer comments"）。Step 7 の修正フローに、「分かりにくい / 誤解を招く」系の指摘は説明コメントで取り繕わずコード・命名・型・構造そのものを直して解消する原則を追加（将来の読み手も同じ箇所でつまずくため）。feature-dev Phase 6 の自動 fix にも委譲経由で波及

## [2.20.0] - 2026-06-03

### Added
- **総合判定（レビュー結論）の導出**（Google eng-practices "The Standard of Code Review" の continuous improvement 原則）。`scoring-guide.md` に「レビュー結論（総合判定）」セクションを追加し、報告マトリクス通過後の残存指摘から `Approve` / `Approve with nits` / `Needs work` を決定的に導出する（BLOCKER/CRITICAL 残 → Needs work、MAJOR/MINOR のみ → Approve with nits、ゼロ → Approve）。`review` / `self-review` のレポート冒頭に `総合判定` 行を追加。「完璧でなくともコード健全性が向上すれば Approve」とし、nit の積み残しで承認を保留しない（LGTM with comments）
- **severity プレフィックス規約**（`Nit:` / `Optional:` / `FYI:`、eng-practices "How to write code review comments"）。`reviewer-prompts.md` の出力フォーマットに、必須指摘と任意改善を著者が一目で区別できる文面マーカーを定義。MINOR 非ブロッキング → `Nit:`、任意改善 → `Optional:`、focus 外の教育的共有 → `FYI:`（related-observations に最大 2 件）。BLOCKER/CRITICAL/MAJOR の必須指摘には付けない

### Changed
- **好みベース指摘の confidence 上限クランプ**（eng-practices "principles over personal preference"）。`reviewer-prompts.md` の評価原則を 5 → 6 原則に拡張し「好みではなく原則」を追加。`scoring-guide.md` の適用順序に、CLAUDE.md / style guide / 計測データ / file:line のいずれの根拠も伴わない個人的スタイル選好は confidence を `min(値, 40)` に制限するルールを追加。LLM レビューの偽陽性（根拠なき好み指摘）を半機械的に刈り取る

## [2.19.0] - 2026-06-02

### Added
- `self-review` に **`review:completed` Event Bus publish（Step 6.4）** を追加（Workflow 監査 2026-06-01 の rollout Step3-C 計測仕込み）。embed / 非 embed の両モードで `.claude/events.jsonl` に集計を fire-and-forget で追記し、review skill と同じ `review:completed` イベントで集計を揃える。LLM 駆動 fan-out の「観点取りこぼし」「severity / confidence のパース安定性」を後から定量化するための計測データ蓄積が目的
  - `SAFE_HOOK_NAME=code-review:self-review` で publisher を識別、`pr` は `"local"` 固定。payload 規約（`missing_coverage` / `result_grid`）は review skill と同一
  - 副作用のみで標準出力にレポート文字を足さないため、embed mode の出力フォーマット（Step 6.5 の findings JSON → marker の順序）に影響しない

## [2.18.0] - 2026-06-01

### Added
- **self-review `--embed` の構造化 findings JSON 出力（schema_version: 1）**。embed mode 時に Step 6 の markdown レポート直後へ、`<!-- FINDINGS_JSON_START -->` / `<!-- FINDINGS_JSON_END -->` で囲んだ機械可読な findings ブロックを出力する（dual format）。呼び出し元（feature-dev Phase 6 等）が `severity` / `confidence` / `focus`（安定 focus キー）/ `file` / `line` / `suggested_fix` を決定的にパースでき、markdown の正規表現パース依存を解消する
  - Step 6.5 として SKILL.md にフィールド契約を明文化（findings は Step 6 報告と 1:1、`focus` は triage-guide の英語 focus キーを使用）
  - 後方互換: 非 embed 実行（`/self-review` 単独）では JSON ブロックを出力せず従来通り

## [2.17.1] - 2026-05-29

### Changed
- **剪定 (Opus 4.7→4.8)**: review / self-review SKILL.md の effort 設計意図にあった「Opus 4.7 のコーディング向け推奨設定」という stale な世代参照を更新。Opus 4.8 では `high` が既定 effort のため、オーケストレーターの `xhigh` を「demanding task 向けに一段引き上げた設定」と明記し直した。reviewer の `effort: max`（Confidence ≥80 フィルタで偽陽性を刈る意図的設計）は維持（cc-catch-up Phase P 剪定レビューで「文言更新のみ」を選択）

## [2.17.0] - 2026-05-29

### Added
- `self-review` skill に **`--embed` フラグ** を追加（GitHub issue #57）。他 plugin（feature-dev Phase 6 等）からプログラム的に呼び出される場合に、Step 7 の修正方針確認 AskUserQuestion を skip して findings をそのまま return するモード
  - `commands/self-review.md` の `argument-hint` と本文に `--embed` を反映
  - SKILL.md Step 1 の引数解説に embed mode の return 仕様（Step 6 レポート + 末尾 marker `[embed-mode: findings-only, no-prompt]`）を明文化
  - SKILL.md Step 7 冒頭に embed mode 分岐を追加（指定時は本ステップを skip）
  - 後方互換: `--embed` 未指定の `/self-review` 単独実行は従来通り Step 7 まで完走

### Notes
- 動機: feature-dev v2.0.0 (#52, commit 655987d) で Phase 6 が self-review 呼び出しに変わった際、self-review の Phase 7 AskUserQuestion がユーザー操作を 1 回追加してしまう UX 負債が残っていた。本変更で feature-dev / 将来の linear-workflow / indie-workflow 等が同じ汎用 IF で findings を集約できる

## [2.16.0] - 2026-05-28

### Fixed
- **worktree branch 継承バグ修正**（GitHub issue #56, Critical）。`isolation: "worktree"` で起動された子 worktree は親 branch を継承せず origin/default-branch から派生していたため、explorer / reviewer が古い main を見て深刻な偽陽性を量産していた（Vue プロジェクトで BLOCKER 3 件 + CRITICAL 1 件の偽陽性が観測済み）
  - `references/explorer-prompts.md` / `references/reviewer-prompts.md` の共通指示先頭に「開始時の必須セットアップ」セクションを追加。worktree 起動時は最初の Bash 呼び出しで `gh pr checkout {{PR_NUMBER}}` を実行し、`git rev-parse --abbrev-ref HEAD` で PR ブランチ名と一致することを確認する
  - `skills/review/SKILL.md` Step 4 / 5 / 5.5 / 5.6 で agent 起動箇所に PR_NUMBER と head ref の prompt 注入を必須化（`{{PR_NUMBER}}` プレースホルダを実数値に置換）
  - `skills/self-review/SKILL.md` は `isolation: "worktree"` を使わないため修正不要

### Added
- **PR 種別分岐ルール表**（GitHub issue #43, High）を `references/triage-guide.md` に追加。Stage 1 より先に `## 2.5 PR 種別分岐ルール` で doc-only / migration / lockfile / generated code 等の特殊 PR を判定し、即興構成での skill スキャフォールド無視を防ぐ
  - `doc-review-mode`: `*.md` 比率 ≥ 80% → リンク健全性・コード片安全性・構造整合性に絞った 1〜2 reviewer
  - `dba-mode`: SQL migration ファイル含む → migration reviewer + specialist-destructive-op
  - `supply-chain-mode`: lockfile 主体 → dependency reviewer 1 体に絞る
  - `skip-mode`: vendor / generated code 主体 → AskUserQuestion で確認後 spec-compliance のみ
  - `default-mode`: 上記いずれでもない場合のみ通常の Stage 1 / Stage 2 へ
- **Issue ファイル必読フロー**（GitHub issue #43, High）を `skills/review/SKILL.md` Step 1 に追加。PR head / base branch 名から `[A-Z]+-\d+` パターンで Issue ID を抽出し、`.claude/linear/` / `.claude/indie/` 配下の Issue ファイルを探索して spec-compliance reviewer の prompt に同梱する。親 Issue リンクは 1 段だけ追跡（深い再帰禁止）
- **適用モードのレポートヘッダ表示**（GitHub issue #43, Low）。レビュー結果冒頭に `[mode: doc-review, agents: [doc-reviewer]]` 形式の 1 行ヘッダを表示し、レビュー判断のコンテキストをユーザーに透明化

### Changed
- `skills/review/SKILL.md` Step 3 に Stage 0（PR 種別分岐の先行判定）を追加し、triage-guide.md `## 2.5` の参照を明示
- `plugin.json` の description を 2.16 機能反映に更新

### Notes
- issue #56 の 🟡 High 項目（既存バグ自動除外 / effort 動的調整）および 🟢 Medium 各種は本リリースのスコープ外（別 issue として残置）
- issue #43 の Medium / Low 項目のうち「出力テンプレート標準化」「gh コメント投稿フラグ」は scope creep のため別 issue として残置
- `plugin.json` の userConfig 追加（`force_checkout_pr_branch` 等）は今回スコープ外

## [2.15.0] - 2026-05-28

### Added
- `reviewer-prompts.md` の共通指示節に **評価 5 原則** を追加（GitHub issue #51）。PASS が証明されるまで FAIL / 自己交渉禁止 / 証拠ファースト / spec が真実 / 関心の分離。reviewer・specialist・meta-reviewer 全てに共通の判断基準として明文化
- `reviewer-prompts.md` に **静的検査優先の自己問い** を追加。指摘出力前に「linter / ast-grep / 型検査に落とせるか」を自問する原則を明記
- `triage-guide.md` Red-flag pattern table に **ガードレール骨抜き検出**（lint/hook/static check 設定の削除・無効化・severity 降格・適用範囲縮小・ブロック判定反転）を追加。BLOCKER 固定で `specialist-guardrail-bypass` を自動起動
- `reviewer-prompts.md` §5 Specialist テンプレートに **specialist-guardrail-bypass** を新規追加
- `review/SKILL.md` Step 4.9 と `self-review/SKILL.md` Step 3.9 に **AGENTS.md 階層動的選択** を追加。変更ファイルパスから対応する `{dir}/AGENTS.md` / `{dir}/CLAUDE.md` を遡って Glob で発見し、該当層だけを reviewer プロンプトに同梱（入力 token 30〜50% 削減）
- `review:completed` event payload に **`result_grid`** フィールドを追加（high/medium/low/skip/error の 5 値集計）。後段 hook / PR コメント自動投稿の dispatch ロジックが分岐爆発しない標準スキーマ

## [2.14.0] - 2026-05-26

### Added
- `skills/review/SKILL.md` のレポートに「良かった点」セクションを追加（Google Engineering Practices の looking-for「Good things」由来）。著者が意図的に良くした箇所を 0〜2 件、該当ファイル:行つきで具体的に挙げ、指摘偏重を避けてメンタリング効果を持たせる。中身のない称賛はノイズになるため禁止、特筆点がなければ省略。PR レビュー専用（self-review は品質ゲート用途のため対象外）

## [2.13.0] - 2026-05-25

### Added
- `self-review` skill に `--focus <観点>` / `--exclude <観点1,観点2>` 引数を追加（GitHub issue #40）。同一セッションで既に reviewer agent を走らせた後の再実行時に、既検証の観点を再報告しないようレビュー対象を絞り込み・除外できる
  - `--focus`: Phase 0 で該当観点の reviewer のみ構成（最小保証も focus に含まれない限り起動しない）
  - `--exclude`: 該当観点の reviewer を構成から外す
  - reviewer プロンプトに `review focus:` / `already verified (do not re-report):` を注入
- `commands/self-review.md` の `argument-hint` と本文に `--focus` / `--exclude` を反映

## [2.12.0] - 2026-05-19

### Added
- **Red-flag pattern による specialist 自動起動**（Idea 3-a）。triage-guide.md の `## 3 Red-flag pattern による specialist 自動起動` で diff の危険パターンを検出し、対応する specialist reviewer を Phase 0 で自動追加起動する
  - `specialist-injection`: `eval(` / `child_process` / `exec(` / `subprocess.run` / `shell=True` 等のコード/コマンドインジェクション
  - `specialist-destructive-op`: `fs.unlink` / `rm -rf` / `DROP TABLE` / `TRUNCATE` / WHERE 句なし DELETE/UPDATE 等の破壊的操作
  - `specialist-secret-handling`: `password =` / `BEGIN PRIVATE KEY` / `Bearer` / `console.log(.*token)` 等のシークレット漏洩
  - `specialist-input-validation`: `JSON.parse(req.*)` / `RegExp(user_input)` 等の信頼境界
  - specialist の指摘は大半が BLOCKER/CRITICAL になる前提で、2軸マトリクスにより低 confidence でも人間に届く設計
- **Phase 5.5 Adaptive deepening (追加 explorer ラウンド)**（Idea 1）。reviewer の `unmet_information` 申告をトリガーに、対応する re-explore explorer を 1 ラウンドだけ起動して該当 reviewer のみ再実行する
  - reviewer-prompts.md 共通指示に `## unmet_information` 出力フィールド仕様を追加。「BLOCKER 候補で context 不足」「呼び出し元全件確認が必要」等のケースのみ申告
  - explorer-prompts.md に `re-explore` フォーカステンプレートを追加。元 reviewer の why に直接回答する形式
  - 上限 3 体ずつ。失敗時は best-effort で続行
- **Phase 5.6 Meta-reviewer ラウンド**（Idea 1+3 統合）。BLOCKER または CRITICAL 検出時に、別 reviewer が「他の reviewer の見落とし観点」を探すメタレビューを 1 ラウンド実行
  - 観点の偏り検出、指摘の盲点、複合リスク、正常系の見落としを重点的に検証
  - 重複指摘禁止、追加指摘なしも健全
- **explorer 配置条件の緩和**（Idea 3-b）。共通モジュール（`utils/` / `shared/` / `lib/` / `common/` / `helpers/` / `core/`）の変更は **行数・関数数に関わらず必ず shared-module-impact explorer を 1 体起動**。小規模変更で依存元への波及を見落とすリスクを構造的に解消
- `plugin.json` の userConfig に `enable_adaptive_rounds` (boolean, default: true) と `enable_meta_reviewer` (boolean, default: true) を追加。トークンコスト・レイテンシを抑えたい場合は false に

### Changed
- `triage-guide.md` の `## 7 最小保証とフェーズ上限` に specialist 上限 6 体を追加（reviewer 枠 10 体とは別カウント）
- `triage-guide.md` に `## 8 動的ラウンド (Phase 5.5 / 5.6)` セクションを新設、effort 適応ルール表 (low/medium はスキップ、high は 5.5 のみ条件付き、xhigh/max は両方) を明文化
- `review` skill / `self-review` skill にレポート出力時の動的ラウンド可観測性を追加 (`Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由}`)
- skill description / `marketplace.json` の説明を 2.12 機能反映に更新

### Notes
- effort 適応により、デフォルト effort=high では Phase 5.5 (unmet 起動時のみ) のみ動作し、Phase 5.6 はスキップ。深掘りが必要な場合は effort=xhigh / max で実行
- 動的ラウンド全体のトークンコスト増分は「unmet 申告がない場合 0」「申告ありでも追加 explorer 最大 3 + 再 reviewer 最大 3」「meta-reviewer +1」のため、保守的設計
- 本リリースは Phase B (Idea 1 + Idea 3 統合) に該当。Phase A (2軸スコアリング) は v2.11.0

## [2.11.0] - 2026-05-19

### Added
- **2 軸スコアリング** (confidence × severity) を導入。`scoring-guide.md` を全面改訂し、severity 4 段階 (BLOCKER / CRITICAL / MAJOR / MINOR) と報告マトリクスを定義。「重大だが不確実」(race condition 疑い 等) と「軽微だが確実」(typo 等) を従来の単一軸 confidence では区別できなかった構造的ジレンマを解消
  - 報告マトリクス: BLOCKER は confidence ≥ 60 で報告、CRITICAL は ≥ 80、MAJOR / MINOR は ≥ 95
  - これにより「疑わしい重大問題は人間判断を促す」「ノイズ的 nitpick は自動除外される」の非対称運用が可能に
- `reviewer-prompts.md` の共通指示に severity 必須付与を追加、出力フォーマットに `[severity: XXX]` ラベルを追加。各 Focus テンプレート (bug-detection / security / migration / performance / api-design / cross-cutting 等) に severity 目安を追加
- `plugin.json` の userConfig に `review_severity_threshold` を追加 (デフォルト: `MAJOR`)。ユーザーが報告閾値を `BLOCKER` (厳しめ) / `MINOR` (緩め) に変更可能

### Changed
- `review` skill / `self-review` skill の Phase 6 / 5 のフィルタリングロジックを 2 軸マトリクスベースに変更
- `review` skill の Step 7 出力フォーマットを severity 別グルーピング (🚨 BLOCKER / ⚠️ CRITICAL / 📋 MAJOR) に変更
- `review:completed` event payload に `blocker_count` / `major_count` / `minor_count` を追加。`critical_count` は subscriber 互換のため維持
- `self-review` skill の修正方針 AskUserQuestion を「BLOCKER/CRITICAL のみ」に変更 (旧: `confidence >= 90 のみ`)。BLOCKER 指摘を残したままコミットしようとした場合は再確認
- `review` skill の返答ドラフト生成の「重要のみ」を severity ベース (BLOCKER または CRITICAL) に変更
- `review` / `self-review` skill の description を 2 軸スコアリング対応に更新

### Notes
- **後方互換性**: severity が付与されていない reviewer 出力は CRITICAL とみなして処理されるため、移行期間中も既存挙動が維持される (旧 confidence ≥ 80 と等価)
- userConfig の `review_confidence_threshold` は後方互換のため残置 (CRITICAL severity 以下のフィルタに使用)
- 本リリースは Phase A (スコア再定義) に該当。Phase B (Idea 1+3 統合: 動的ラウンド + 検出ミス対策) は別リリース予定

## [2.10.0] - 2026-05-19

### Added
- `references/reply-tone-guide.md` を新規追加 (#37 軽量版)。レビュー後の返答ドラフトのトーン・テンプレ・禁則・パターン別ガイド（完全対応/部分対応/据置/意図確認/反証/レビュアー再返信）を集約
- `review` skill の Step 7 にレポート出力後の **返答ドラフト生成** ステップを追加（AskUserQuestion で `不要 / 重要のみ / 全件 / 個別選択` を選択、reply-tone-guide.md に従いドラフトのみ生成、投稿は手動）
- `review` skill と `commands/review.md` の allowed-tools に `AskUserQuestion` を追加

### Notes
- Issue #37 の thread skill 構想（check / reply / status）からスコープを大幅に縮小。状態管理・GitHub 投稿自動化・未対応スレッド一覧は本リリースに含めず、将来 skill 化が必要になった時点で再検討する（退路確保）
- `self-review` skill は PR コメントの返答対象がないため変更なし

## [2.9.0] - 2026-05-18

### Added
- `review` skill の Step 7（レポート出力後）に `review:completed` イベント発行を追加 (#33)。payload は `{"pr":"<number>","critical_count":<n>,"warning_count":<n>,"missing_coverage":[...]}`
  - publisher は `safe-hook.sh` の `event_bus_publish` を `SAFE_HOOK_NAME="code-review:review"` 上書きで呼び出す形式（fire-and-forget、失敗してもレポートは成功扱い）
  - retrospective / instinct-memory 等の subscriber がレビュー傾向（critical 数推移・missing_coverage の偏り）を集計できるようにするための土台

## [2.8.1] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）。code-review 自身は現時点で event を発行しないが、将来 `review:completed` イベント発行用の土台として整備

## [2.8.0] - 2026-05-15

### Added
- 公式 skill 連携を 2 系統追加。
  - `ui-quality` reviewer Focus を新設し、`web-design-guidelines` 公式 skill（`~/.agents/skills/web-design-guidelines/`）のチェックリストに準拠した WCAG 違反 / セマンティック HTML 違反 / フォーカス管理 / 状態フィードバック欠落の指摘を confidence ≥ 80 で報告
  - `triage-guide.md` に UI/フロントエンド観点判定ルールを追加（`.tsx`/`.jsx`/`.vue`/`.svelte`/`components/`/`pages/`/`app/` の変更、または diff の `aria-`/`role=`/`tabindex`/`<button`/`onClick`/`onKeyDown` を検出）
- reviewer 共通指示に外部ライブラリ最新仕様確認（公式 skill `context7` 経由）を opt-in で追加。モデル学習データ cutoff を越える破壊的変更による誤判定を防止し、裏付け不能な仕様ベース指摘は confidence ≤ 75 に下げて自動除外させる

## [2.7.0] - 2026-05-15

### Added
- review SKILL.md に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて explorer/reviewer の上限体数を自動調整（low/medium: 速度優先、high: 既定、xhigh/max: 深掘り）

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）。シェル解釈なしでスクリプトを直接 spawn し、起動オーバーヘッドとパース起因のエッジケースを削減
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応、opt-in 利用）

## [2.6.2] - 2026-05-13

### Added
- `code-review/scripts/fetch-pr-context.sh` を追加。PR メタ・issue コメント・レビューサマリ・行単位 review コメント（返信チェーン込み）を一括取得し、SKILL.md Step 2.5 の構造化フォーマットで markdown 出力する

### Changed
- review SKILL.md Step 1 を更新: PR 会話コンテキスト取得を `fetch-pr-context.sh` の **必須実行** に変更。LLM が個別 `gh` コマンドで組み立てる方式を禁止し、PR コメントの取りこぼしを防止
- review SKILL.md Step 2.5 を更新: スクリプト出力をそのまま PR コンテキストブロックとして使用するよう簡略化（LLM による再構築・要約・編集を禁止）

### Fixed
- review スキルで PR コメント取得がスキップされるケースを解消（取得手順をスクリプトに集約することで決定的に取得保証）

### Removed
- review / self-review の allowed-tools から未使用ツールを削除（Permission Pruning 原則に基づく最小化）
  - review: `Glob`, `Grep`, `mcp__github__pull_request_read`
  - self-review: `Glob`, `Grep`
  - 対応する commands/*.md の allowed-tools も同期

## [2.6.1] - 2026-04-25

### Changed
- `reviewer-prompts.md` の Confidence スコアリングに段階的思考誘導を追加（Opus 4.7 対応）。境界値（75-85）や他 reviewer との矛盾時に diff 意図確認・既存問題誤検知チェック・証拠裏付け確認の 3 ステップを明記

## [2.6.0] - 2026-04-24

### Added
- review スキルに PR 会話コンテキストの reviewer プロンプト注入を追加
  - `gh api repos/{owner}/{repo}/pulls/<PR>/comments` で行単位レビューコメントを取得
  - `gh pr view --json reviews` でレビューサマリを取得
  - PR 説明・issue コメントと合わせて PR コンテキストブロックとして構造化（SKILL.md Step 2.5）
- reviewer-prompts.md に「PR コンテキスト注入テンプレート」(#2.5) を追加
  - 検出ルールはタグベース: `[re-flag: @<user>]` / `[resolved: @<user>]` / `[intent-conflict]` / `[scope:out]`
  - 重複指摘の回避（既指摘かつ diff で修正済みは出力除外）
  - 著者意図の尊重（PR 説明のスコープ・意図と照合）
- scoring-guide.md にタグベースの加減算ルールを追加（正本）
  - `[re-flag: ...]`: +15（既指摘かつ diff で未修正の押し戻し）
  - `[intent-conflict]`: -20（spec-compliance の仕様違反は対象外）
  - `[resolved: ...]`: -30（PR 会話で LGTM/resolved）
  - `[scope:out]`: -50（PR 説明で明示されたスコープ外）
  - 行単位 review comment で既指摘 かつ diff で修正済み: 報告対象外
- triage-guide.md の Stage 1 に PR コンテキストによる観点追加・冗長化ロジックを追記（review skill のみ）

### Changed
- scoring-guide.md と reviewer-prompts.md の責務分離を明確化: reviewer は検出・タグ付けに集中、confidence 数値の加減算は scoring-guide.md を正本として Step 6 で適用

## [2.5.0] - 2026-04-22

### Added
- review / self-review スキルに部分失敗耐性ロジックを追加。explorer / reviewer が並列実行中に失敗しても成功した結果で合成継続し、欠損観点を最終レポートに明示する（最小保証 reviewer-bugs + reviewer-claude-md の両方失敗時のみ中止） (#25)
- self-review スキルに「Generator と分離された Evaluator」設計原則セクションを追加。dev-workflow:git-commit-helper との連携フローを明示 (#27)

## [2.4.2] - 2026-04-19

### Changed
- `check-deps.sh` を `safe-hook.sh` 共通ラッパー経由に移行（stdin 消費・エラー分類・名前付きログの統一） (#21)

## [2.4.1] - 2026-04-17

### Changed
- review/self-review の skill frontmatter effort を `max` → `xhigh` に変更（Opus 4.7 のコーディング向け新推奨設定）
- reviewer subagent の起動を `effort: max` 明示指定に変更（深い推論を優先、偽陽性は Confidence ≥80 フィルタで除去）
- effort 設計意図を SKILL.md に明文化（orchestrator: xhigh、reviewer: max の役割分担）

## [2.4.0] - 2026-04-13

### Added
- review: EnterWorktree/ExitWorktree による worktree 分離実行（レビュー中の並行作業を可能に）

### Changed
- review: `gh pr checkout` を worktree 内で実行するよう変更（作業ブランチへの影響を排除）

## [2.3.3] - 2026-04-04

### Fixed
- review/self-review スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）

## [2.3.2] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

## [2.3.1] - 2026-03-30

### Changed
- explorer のモデルを opus → sonnet に変更（情報収集タスクの effort 最適化、reviewer は opus 維持）

## [2.3.0] - 2026-03-29

### Changed
- self-review: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（修正方針選択 + 後処理）

### Removed
- rules/self-review-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）

## [2.2.1] - 2026-03-29

### Fixed
- userConfig.review_confidence_threshold に type/title を追加し manifest バリデーションエラーを修正

## [2.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（review/self-review: max）
- userConfig: review_confidence_threshold でレビュー閾値をカスタマイズ可能に

## [2.1.0] - 2026-03-26

### Added
- Phase 0 トリアージ: diff 分析による動的エージェント構成決定（Stage 1 タイプ判定 → Stage 2 体数・フォーカス・冗長度決定）
- explorer エージェントタイプ: 事実収集特化（function-flow, dependency-trace, branch-impact, history-context, shared-module-impact）、上限 6 体
- reviewer 冗長化: 対象コードの複雑さに応じて同一観点を複数体（angle 違い）で起動、上限 10 体
- spec-compliance 観点: session-context / Issue / knowledge との仕様整合性チェック
- references/triage-guide.md: Phase 0 判定ロジック・パターンマトリクス・フォールバック構成
- references/explorer-prompts.md: explorer プロンプトテンプレート集
- references/reviewer-prompts.md: 観点別 reviewer プロンプトテンプレート集（現行 #1-#16 から移行・再構成）
- scoring-guide: explorer 裏付け (+10)、冗長ペア合意 (+10)、冗長ペア片方のみ (-5) ルール追加

### Changed
- 固定2フェーズ構成（Phase 1 固定6+条件2 → Phase 2 動的8）を廃止し、Phase 0 トリアージ → 探索 → レビューの動的3フェーズ構成に移行
- CLAUDE.md 準拠チェック: 冗長2体 → Phase 0 判断で 1-2 体（複雑さに応じた冗長化）
- diff-first 原則を改訂: 変更箇所を含む関数の全体確認・類似名称の確認を Read 許可用途に追加

### Removed
- references/agent-prompts.md: 3ファイル（triage-guide, explorer-prompts, reviewer-prompts）に分割移行

## [2.0.0] - 2026-03-25

### Added
- 2フェーズレビュー構成: Phase 1 (コアレビュー) → Phase 2 (専門レビュー動的起動)
- Phase 2 専門エージェント8種: セキュリティ(OWASP)、パフォーマンス、API設計、依存関係、マイグレーション、設定、クロスカッティング影響、パターン統一
- Phase 2 起動判定: diff パターンマッチ（静的）+ Phase 1 結果からの動的判定
- Phase 2 スキップ条件: 小規模かつ懸念なしの場合は Phase 1 のみで完了

### Changed
- 全エージェントを `model: opus` で起動（品質最大化）
- scoring-guide: 複数エージェント同一指摘の加算を +10 → +15 に引き上げ
- scoring-guide: Phase 2 専門エージェント関連のスコアリングルールを追加

## [1.5.0] - 2026-03-25

### Changed
- review: diff 取得を `git diff` から `gh pr diff` に変更（ローカル状態に依存しない）
- review: 全エージェントを `isolation: "worktree"` で起動（PR ブランチの正しい状態でファイルを読む）
- review: diff-first 原則を追加（diff が真のソース、ファイル Read はコンテキスト確認のみ）
- Agent #3: ファイル全文分析→依存先の仕様確認のみに限定

## [1.4.0] - 2026-03-24

### Added
- self-review/review: セッションコンテキスト読み込み（Step 2.5）を追加。`.claude/session-context.md` から Issue の設計判断を取得し、エージェントプロンプトに注入
- scoring-guide: セッションコンテキストによるスコア減算ルールを追加（設計判断一致: -30、スコープ外: -50）

## [1.3.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（GitHub MCP）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.2.0] - 2026-03-23

### Added
- self-review: レポート出力後に修正方針選択ステップ（Phase 6）を追加
- rules/self-review-interaction.md を新規追加

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- code-review プラグインを新規作成
- 並列エージェントによる PR レビュー / セルフレビュー機能
