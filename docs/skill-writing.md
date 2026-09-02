# スキル執筆指針（description 設計と本文の情報設計）

1 つのスキルを「書く」ときの共通指針。多段 agent パイプラインの設計は `docs/pipeline-design.md` が担い、このファイルはその手前 — SKILL.md というテキストそのものの品質を扱う（元ネタ: mattpocock/skills の writing-great-skills, MIT。本リポジトリの規約に合わせて翻案）。

核心は 1 語: **予測可能性 (predictability)**。スキルは確率的なシステムから決定性を絞り出す装置であり、「毎回同じ出力」ではなく「毎回同じ**プロセス**」を取らせることが根本の徳。以下の道具はすべてこれに奉仕する。

## 2 つの負債: context load と cognitive load

- **context load**: model-invoked スキルの description は**毎セッションのシステムプロンプトに常駐**する（本文は遅延ロード）。description の 1 文字は全セッションで課金され続ける。`validate_plugin_quality.py` の単体 600 字 / 全体合計 15,000 字の warning はこの負債の機械化
- **cognitive load**: description を持たない user-invoked スキル（`disable-model-invocation`）は context load ゼロだが、**存在を覚えておく索引が人間側に移る**

**このリポジトリでは `disable-model-invocation` は採用しない。** トリガーフレーズ必須規約（error）・evals 回帰・commands↔skills ペアの文化が model-invoked 前提で組まれているため。負債の制御は「description のダイエット」と「スキルを増やさない判断（`claude-meta:component-addition-advisor`）」で行う。

## description の設計

description の仕事は 2 つだけ — **スキルの正体を 1 文で言う**ことと、**起動すべき分岐 (branch) を列挙する**こと。

- **主語を先頭に**: スキルを特徴づける語（leading word。後述）を文頭に置く。「〜のためのスキルで、…」と前置きしない
- **1 branch 1 トリガー**: 同じ branch の言い換えを羅列するのは duplication。「TDD で機能を作る…テストファーストを求められたら」は 1 つの branch を 2 回書いている。ただしうちのトリガーフレーズは**ユーザーが実際に打つ表記ゆれ**（日英・スラッシュ形）を守る役目も持つので、実在する言い換えは残してよい — 目安は「同じ branch の言い換えは 3 つまで。増やすなら evals にケースを足して回帰で守る」
- **本文にある説明を繰り返さない**: 設計背景・内部手順は description に書かない（context-budget warning の常連）

**command と同名の skill では、この description は起動に使われない**（GitHub issue #206）。スキル選択の一覧に載るのは `commands/<name>.md` の description のほうで、`SKILL.md` 側は載らない。同名スキル（本リポジトリでは 9 プラグイン 26 個）で description を設計するときは、**この節の指針を `commands/*.md` の description に適用し、`SKILL.md` 側は対で揃える**。どちらが読まれているかは router 本人に引用させて確かめる（`claude -p '... 見えている description を一字一句そのまま引用して' --permission-mode plan`）。

## 情報階層と progressive disclosure

SKILL.md の内容は「エージェントがどれだけ即時に必要とするか」で 3 段に置き分ける:

1. **in-skill step** — 順序ある手順。各 step は**完了基準 (completion criterion)** で終える。基準は checkable（done と not-done を区別できる）かつ必要なら網羅的（「変更ファイル全件を確認した」であって「確認する」ではない）に書く。曖昧な基準は早仕舞い（premature completion）を招く
2. **in-skill reference** — 定義・ルール・判定表。順序を持たないフラットな同格集合はそれ自体正しい形（全ルール適用が完了基準になる）
3. **external reference** — `references/*.md` に押し出し、**context pointer**（「〜のときは X.md を Read する」）で必要時のみロード

**押し出しの判定は branch**: 全 branch が必要とするものは inline、一部の branch しか到達しないものは references へ。押し出しすぎると必要な材料が隠れ、押し出さないと SKILL.md が肥大する — この緊張が判断のすべて。規模の目安（100 行未満は既存 skill へ追記 / 500 行以上は references 分割）は `component-addition-advisor` の表が正本。本文 500 行以上は `validate_plugin_quality.py` が warning を出す。

## leading words

**leading word** = モデルの事前学習に既に住んでいる圧縮概念 1 語（例: *tracer bullet* / *red* / *tight* / *ファネル* / *fail-closed*）。本文で繰り返すことで分散定義が蓄積し、最少トークンで挙動の一帯をアンカーする。

- 本文では**実行**をアンカーする: 同じ語が出るたびエージェントは同じ挙動に手を伸ばす
- description では**起動**をアンカーする: ユーザーの語彙・ドキュメント・コードに同じ語が生きていれば、スキルの発火が安定する
- リファクタの好機: 3 箇所で言い直されている三つ組（「速く・決定的で・低オーバーヘッド」）は 1 語（*tight*）に collapse できる。曖昧なゲート（「信頼できるループ」）は観測可能な 2 値（ループが *red* になるか）に変換できる

## 剪定 (pruning)

- **SSoT**: 1 つの意味は 1 箇所に置く（リポジトリの正本規約と同じ。スキル内でも同様）
- **no-op テスト**: その行はモデルの既定挙動を変えるか？ 変えないなら削除する。文単位で判定し、落ちた文は語を削って残すのでなく**文ごと消す**。弱い leading word（「丁寧に」— もともと丁寧）も no-op で、直すなら強い語（「執拗に」）に替える
- **sediment**: 追加は安全に見え、削除は危険に見える。だから放置されたスキルは堆積する。バージョンバンプで本文を触るときは剪定も 1 周する

## 失敗モードカタログ

スキルが期待どおり動かないときの診断語彙:

| 失敗モード | 症状 | 対処 |
|-----------|------|------|
| **premature completion** | step を本当は終えていないのに次へ進む | ①完了基準を鋭くする（安い・局所的）→ ②それでも観測されたら後続 Phase を別スキル/別 references に分割して視界から隠す。順序を守る（いきなり分割しない） |
| **duplication** | 同じ意味が複数箇所にある | collapse。保守と token の二重コストに加え、その意味の階層上の重みを実態以上に吊り上げる |
| **sprawl** | 全行が生きているのに長すぎる | 情報階層で下へ押し出す（references 分割 / branch 分割） |
| **no-op** | 既定挙動と同じ指示に token を払っている | 文ごと削除 or 強い語へ |
| **negation** | 「〜するな」が逆に対象を活性化する | 目標挙動を肯定形で書く。肯定形にできない hard guardrail のみ禁止形を許し、必ず代替行動を並記する |

Opus 5 世代で逆効果になる足場 3 種（委譲促進 / 自己ダブルチェック / 重要な指摘だけ報告）はこのカタログの世代特化版 — ルート CLAUDE.md と `docs/pipeline-design.md` の Opus 5 節を参照。

## このリポジトリでの機械強制マップ

| 観点 | 強制手段 | レベル |
|------|---------|--------|
| description に `トリガー:` が存在 | `validate_plugin_quality.py` | error |
| description 単体 600 字 / 合計 15,000 字 | 同上（context-budget） | warning |
| SKILL.md 本文 500 行以上 | 同上（skill-size） | warning |
| トリガーフレーズ → 期待スキル起動の回帰 | `evals/runner.py`（pass^k=3） | 手動実行 |
| 同名 command と skill の description 乖離 | **機械強制なし** — 対で直す規約のみ（#206）。同名時に router が読むのは commands 側 | — |
| description の質（branch 重複・no-op） | **機械強制なし** — 本 doc を執筆・レビュー時の観点として使う | — |
