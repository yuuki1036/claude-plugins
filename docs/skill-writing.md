# スキル執筆指針（description 設計と本文の情報設計）

1 つのスキルを「書く」ときの共通指針。多段 agent パイプラインの設計は `docs/pipeline-design.md` が担い、このファイルはその手前 — SKILL.md というテキストそのものの品質を扱う（元ネタ: mattpocock/skills の writing-great-skills（現 writing-for-agents と SKILL-MECHANICS）。Copyright (c) 2026 Matt Pocock / MIT License、許諾文は repo 直下の NOTICE。本リポジトリの規約に合わせて翻案。2026-09-24 に MP `c55ee46` と再同期した — 次に差分を見るときはここから）。**対象は SKILL.md だけではない** — rules（SessionStart で注入するルール）・agents の定義・`references/prompts/*.md`・CLAUDE.md も、エージェントが読む文書として同じ観点（情報階層・no-op 剪定・leading words・cache と context pointer）で書く。とくに CLAUDE.md と rules は毎セッション常駐するので、特定の作業でしか使わない節は `docs/` などに移してポインタだけ残す（事故から生まれた Gotchas の規範は残す）。

核心は 1 語: **予測可能性 (predictability)**。スキルは確率的なシステムから決定性を絞り出す装置であり、「毎回同じ出力」ではなく「毎回同じ**プロセス**」を取らせることが根本の徳。以下の道具はすべてこれに奉仕する。

## 2 つの負債: context load と cognitive load

- **context load**: model-invoked スキルの description は**毎セッションのシステムプロンプトに常駐**する（本文は遅延ロード）。description の 1 文字は全セッションで課金され続ける。`validate_plugin_quality.py` の単体 600 字 / 全体合計 15,000 字の warning はこの負債の機械化
- **cognitive load**: description を持たない user-invoked スキル（`disable-model-invocation`）は context load ゼロだが、**存在を覚えておく索引が人間側に移る**

**このリポジトリでは `disable-model-invocation` は採用しない。** トリガーフレーズ必須規約（error）・evals 回帰・commands↔skills ペアの文化が model-invoked 前提で組まれているため。負債の制御は「description のダイエット」と「スキルを増やさない判断（`claude-meta:component-addition-advisor`）」で行う。新しいスキルに分けてよいのは、**独立した leading word で発火すべきとき**か、**他のスキルから Skill tool で呼ぶ必要があるとき**だけ。どちらでもなければ、常駐する description 1 本分の context load に見合わない。

## description の設計

description の仕事は 2 つだけ — **スキルの正体を 1 文で言う**ことと、**起動すべき分岐 (branch) を列挙する**こと。

- **主語を先頭に**: スキルを特徴づける語（leading word。後述）を文頭に置く。「〜のためのスキルで、…」と前置きしない
- **1 branch 1 トリガー**: 同じ branch の言い換えを羅列するのは duplication。「TDD で機能を作る…テストファーストを求められたら」は 1 つの branch を 2 回書いている。ただしうちのトリガーフレーズは**ユーザーが実際に打つ表記ゆれ**（日英・スラッシュ形）を守る役目も持つので、実在する言い換えは残してよい — 目安は「同じ branch の言い換えは 3 つまで。増やすなら evals にケースを足して回帰で守る」
- **本文にある説明を繰り返さない**: 設計背景・内部手順は description に書かない（context-budget warning の常連）

**command と同名の skill では、この description は起動に使われない**（GitHub issue #206）。スキル選択の一覧に載るのは `commands/<name>.md` の description のほうで、`SKILL.md` 側は載らない。同名スキル（本リポジトリでは 9 プラグイン 26 個）で description を設計するときは、**この節の指針を `commands/*.md` の description に適用し、`SKILL.md` 側は対で揃える**。どちらが読まれているかは router 本人に引用させて確かめる（`claude -p '... 見えている description を一字一句そのまま引用して' --permission-mode plan`）。

## 情報階層と progressive disclosure

SKILL.md の内容は「エージェントがどれだけ即時に必要とするか」で 3 段に置き分ける:

1. **in-skill step** — 順序ある手順。各 step は**完了基準 (completion criterion)** で終える。基準は checkable（done と not-done を区別できる）かつ必要なら網羅的（「変更ファイル全件を確認した」であって「確認する」ではない）に書く。網羅性の要求は、step として書いていない掘り下げ（legwork）まで引き出す。曖昧な基準は早仕舞い（premature completion）を招く
2. **in-skill reference** — 定義・ルール・判定表。順序を持たないフラットな同格集合はそれ自体正しい形（全ルール適用が完了基準になる）
3. **external reference** — `references/*.md` に押し出し、**context pointer**（「〜のときは X.md を Read する」）で必要時のみロード

**参照先に届くかどうかは、参照先ではなく pointer の文面で決まる**。全 branch に必須の素材が弱い pointer（「必要なら X を参照」）の後ろにあると、読む回と読まない回に分かれる（variance bug）。まず文面を鋭くし（「Phase 3 に入る前に X を Read する」のように条件と義務を書く）、それでも届かなければ inline に戻す。実例: 同名 command の本文から SKILL.md に到達しなかった（#219）、サンドボックスで `references/` を見つけられず正本を読まずに推敲していた（writing-polish 0.10.1）。CLAUDE.md の「〜を読むこと」も同じ pointer として扱う。

**押し出しの判定は branch**: 全 branch が必要とするものは inline、一部の branch しか到達しないものは references へ。押し出しすぎると必要な材料が隠れ、押し出さないと SKILL.md が肥大する — この緊張が判断のすべて。押し出すべき reference を inline に残すと step が埋もれ、注意が向くかどうかが回ごとにばらつく（読みやすさだけでなく、ばらつきの問題）。規模の目安（100 行未満は既存 skill へ追記 / 500 行以上は references 分割）は `component-addition-advisor` の表が正本。本文 500 行以上は `validate_plugin_quality.py` が warning を出す。

**co-location**: 1 つの概念の定義・規則・注意は 1 つの見出しの下にまとめる。duplication（同じ意味を 2 か所に書く）とは別の問題で、こちらは 1 つの意味を複数の場所に散らすこと。大きな SKILL.md（feature-dev・code-review 系）をレビューするときの観点にもなる。

## leading words

**leading word** = モデルの事前学習に既に住んでいる圧縮概念 1 語（例: *tracer bullet* / *red* / *tight* / *ファネル* / *fail-closed*）。本文で繰り返すことで分散定義が蓄積し、最少トークンで挙動の一帯をアンカーする。

- 本文では**実行**をアンカーする: 同じ語が出るたびエージェントは同じ挙動に手を伸ばす
- description では**起動**をアンカーする: ユーザーの語彙・ドキュメント・コードに同じ語が生きていれば、スキルの発火が安定する
- **造語は事前分布を持たない**: 事前学習済みの語なら無料で得られる挙動を、定義の token で払うことになる。まず既存の語を探し、造語するなら（dormant / 退路確保 / 機械層 など）定義を明記する
- リファクタの好機: 3 箇所で言い直されている三つ組（「速く・決定的で・低オーバーヘッド」）は 1 語（*tight*）に collapse できる。曖昧なゲート（「信頼できるループ」）は観測可能な 2 値（ループが *red* になるか）に変換できる

## 剪定 (pruning)

- **SSoT**: 1 つの意味は 1 箇所に置く（リポジトリの正本規約と同じ。スキル内でも同様）
- **cache**: 環境も正本になる（スクリプトの `--help` や冒頭 docstring、ディレクトリ構成、`plugin.json`、設定ファイル）。それを書き写した記述はキャッシュで、引くのが高くつくときだけ置く価値がある。書くのは、引いても見つからないもの（書かれていない慣習・選択の理由・設定が語らない落とし穴）。1 ファイル・1 コマンドで引けるものは環境に任せる（書き写さなければ古くならない）。実例: `validate_plugin_quality.py` の検査項目は冒頭 docstring が正本で、CLAUDE.md に列挙を複製しない
- **no-op テスト**: その行はモデルの既定挙動を変えるか？ 変えないなら削除する。文単位で判定し、落ちた文は語を削って残すのでなく**文ごと消す**。弱い leading word（「丁寧に」— もともと丁寧）も no-op で、直すなら強い語（「執拗に」）に替える
  - 判定の基準はモデルの既定挙動で、読む人の感覚ではない。意見が割れたら議論せず実行で決める（このリポジトリでは `evals/runner.py` で「選ばれるか」、`claude plugin eval` の with / without の Δ で「効くか」。どちらも実行前に概算コストを示す）。世代が変わったら書き直すより、no-op の見直しを 1 周するほうが先
  - **判定は挙動で、長さではない**。エージェントに「短くして」と頼むと、見えている長さを減らす方向に最適化して機能ごと削る（コメント規約の「長さは違反の根拠にならない」と同じ）
- **sediment**: 追加は安全に見え、削除は危険に見える。だから放置されたスキルは堆積する。バージョンバンプで本文を触るときは剪定も 1 周する。行が生きていないのは、最初からタスクに効いていない（説明だけ・一部の branch しか要らないのに inline）か、記述している挙動や環境が変わって古くなったかのどちらか

終わりの目安: 何も 2 回書かれていない / 一部の branch しか要らない reference が pointer の後ろにある / leading word が複数の箇所で働いている。改善するほど短くなるのが普通。

## 失敗モードカタログ

スキルが期待どおり動かないときの診断語彙:

| 失敗モード | 症状 | 対処 |
|-----------|------|------|
| **premature completion** | step を本当は終えていないのに次へ進む | ①完了基準を鋭くする（安い・局所的）→ ②それでも観測されたら後続の step を視界から隠す。順序を守る（いきなり分割しない）。**隠す対策が効くのは実際のコンテキスト境界を越えるとき**（subagent に渡す・新しいセッションに引き継ぐ）だけで、inline の Skill 呼び出しや references 分割では後続の Phase 見出しが文脈に残り、何も隠れない。逆向きにも注意: sequence を 1 つに統合すると後続 step が見えて早仕舞いを招く（既存 skill への Phase 追加も同じ） |
| **duplication** | 同じ意味が複数箇所にある | collapse。保守と token の二重コストに加え、その意味の階層上の重みを実態以上に吊り上げる |
| **sprawl** | 全行が生きているのに長すぎる | 情報階層で下へ押し出す（references 分割 / branch 分割） |
| **no-op** | 既定挙動と同じ指示に token を払っている | 文ごと削除 or 強い語へ |
| **negation** | 「〜するな」が逆に対象を活性化する | 目標挙動を肯定形で書く。肯定形にできない hard guardrail のみ禁止形を許し、必ず代替行動を並記する |
| **over-fitting** | 作ったときの 1 回の実行（その repo・そのファイル）でしか動かない | 1 回やってから skill に書き起こすと、例が具体的すぎるものになる。実行は証拠として残し、その repo・そのファイル固有の部分を落として、タスクの類に向けて書く |

Opus 5 世代で逆効果になる足場 3 種（委譲促進 / 自己ダブルチェック / 重要な指摘だけ報告）はこのカタログの世代特化版 — ルート CLAUDE.md と `docs/pipeline-design.md` の Opus 5 節を参照。

## このリポジトリでの機械強制マップ

| 観点 | 強制手段 | レベル |
|------|---------|--------|
| description に `トリガー:` が存在 | `validate_plugin_quality.py` | error |
| description 単体 600 字 / 合計 15,000 字 | 同上（context-budget）。**数えるのは常駐する側**＝ commands 全部と、同名 command を持たない skill | warning |
| SKILL.md 本文 500 行以上 | 同上（skill-size） | warning |
| トリガーフレーズ → 期待スキル起動の回帰 | `evals/runner.py`（pass^k=3） | 手動実行 |
| 同名ペアで **トリガーフレーズだけ** SKILL.md 側を直した | 同上（router-drift）。トリガーの編集はルーティング意図そのものなので「意図はあったが届かなかった」を名指しできる（#206 案 B） | warning |
| 同名 command と skill の description の**内容**乖離 | **機械強制なし** — 対で直す規約のみ（#206）。素朴な判定式は実測で判別しなかった（同名 26 件中 12 件で鳴る一方、実害の無い対照群でも 10 件中 6 件で鳴る） | — |
| description と本文の質（branch 重複・no-op・cache・弱い pointer・co-location・over-fitting） | **機械強制なし** — 本 doc を執筆・レビュー時の観点として使う。no-op の対立は evals / plugin eval の実行で決める | — |
