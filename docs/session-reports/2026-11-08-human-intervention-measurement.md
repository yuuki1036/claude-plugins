# 人の介入点の計測（AI-DLC v2 原則 1 の物差し）

AI-DLC v2（[awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows)）の目的は、人の判断を機械の検査へ
移した分だけ人の介入を減らすこと（仕様の原則 1・7）。
この repo のやり方を評価したときは「AI-DLC の仕組みで、こちらの失敗をどれだけ防げるか」で測ったので、
物差しが違った。そこで、人がどこで判断・修正・差し戻しをしているかを数え、多いところから
機械の検査へ移せるかを判定する。本書はその手順。結果は計測後に追記する。

## 何を数えるか

正本は `.claude-plugin/scripts/measure-interventions.py` の冒頭 docstring（種別・文の形・スキルへの帰属・
伏せ字の範囲）。要点だけ:

- 人の発話は transcript の user 行のうち `origin.kind == "human"` のものだけ。欄の無い行は eval・grader・
  別セッションからの起動で、人の発話ではない
- 発話は「問われて答えた（reply・ボタン）」と「問われずに出した（free）」に分け、別に文の形を付ける。
  continue（「次」「y」）・routine（「commit push」「merged」）は、人が止まった工程を押しているだけの発話
- AskUserQuestion は 1 問ごとに、推奨を選んだか・別の選択肢か・自由記述か
- 中断・tool の拒否（人の介入）と、PreToolUse hook の停止（機械の介入。比較用）
- fork・続きのセッションで別のファイルに複製された同じ行（同じ uuid）は 1 回だけ数える

数えていないもの: tool の許可（拒否だけ数える）/ transcript の外での判断（GitHub 上のレビューとマージ・
ターミナルでの手作業）/ subagent の中 / `cleanupPeriodDays` で消えた transcript。

## 手順

### 1. マシンごとに集計する

```bash
python3 .claude-plugin/scripts/measure-interventions.py --out <出力 dir>
```

- 出力は `summary.md` / `summary.json`（件数だけ）と `events.jsonl`（発話の本文と、直前の assistant 発話の
  末尾を含む）。**`events.jsonl` はそのマシンから出さない**
- `--out` はリポジトリの外を指す（git の作業ツリーの中なら exit 2 で止まる）。省くと毎回新しい一時 dir に書き、
  最後にそのパスを出す
- 既定で、プロジェクト名・質問の見出し・このマーケットプレイス外のスキル名と hook のプラグイン名・MCP サーバー名を伏せる。
  m1 で見出しまで見るなら `--names`（その出力は共有しない）
- m2（会社 PC）は `--names` を付けない。summary を持ち出す前に、業務情報が無いか目で確かめる
- 期間は既定で残っている transcript 全部。2 台で揃えるなら `--since YYYY-MM-DD`（日時は UTC。`--days N` は
  走らせた日から数えるので、2 台・2 回で揃えるには使わない）

### 2. 発話を分類する（そのマシンのセッションで）

決定的に分けられるのは「問われたか」と文の形まで。中身は Claude が `events.jsonl` を読んで分類し、
1 件 1 行の `labels.jsonl` に書く。置き場所は `events.jsonl` と同じ `<出力 dir>/labels.jsonl`（`check` に発話の
要約が入るので、リポジトリの中に置かない）:

```json
{"session": "<events の session>", "ts": "<events の ts をそのまま>", "label": "修正", "target": "決定的な検査", "check": "何を検査すれば防げたか 1 行"}
{"session": "<events の session>", "ts": "<events の ts をそのまま>", "qi": 1, "label": "方針の指定", "target": "人の判断", "check": "…"}
```

- `qi` は `question:free-text` の行（上の例の 2 行目）だけに付ける（events の `qi` をそのまま。1 回の
  AskUserQuestion の質問はどれも同じ ts を持つので、これが無いと区別できない）。prompt の行（1 行目）には付けない
- 対象は本文を持つ prompt の行（sub が start / free / reply / button-primary / button-alt）と `question:free-text`。
  form が continue・routine・choice の行は分類しなくてよい（形だけで「続行・承認」と分かる）

| label | 意味 |
|---|---|
| 修正 | AI の出力・行動の誤りを直させた |
| 差し戻し | 進め方・範囲をやり直させた |
| 方針の指定 | AI が聞かずに決めた・決めるべきだったことを人が決めた |
| 追加の依頼 | 同じ作業の範囲を広げた |
| 新しい依頼 | 別の作業を頼んだ |
| 質問 | 説明・状況を求めた |
| 情報の提供 | 貼り付け・transcript の外での作業の結果（「merged」など）を伝えた |
| 続行・承認 | 中身が続行・承認だけだった |

修正・差し戻し・方針の指定には `target`（移し先）を付ける:

| target | 意味 |
|---|---|
| 決定的な検査 | hook・script・lint で判定できる |
| LLM の判定 | 事後条件として書けるが判定は LLM。LLM の判定だけでは完了にしない（AI-DLC 仕様 §3） |
| 人の判断 | 好み・トレードオフ・transcript の外の事情 |

- 件数が多いときは subagent に分けてよい（1 タスク 4 体まで）。識別子は `ts` をそのまま返させる
  （行番号を返させると振り直す agent が出る。`failure-journal` の transcript-salvage で起きた）
- label・target は上の表の語だけを使う。外れた値は集計で `(語彙外)` に数えられる
- m2 では `check` の説明も業務情報を汎用名に置き換えて書く。summary には `check` を出さない

分類を件数に足す（transcript を読み直して集計し直すので、**step 1 と同じ `--since` / `--until` / `--project` /
`--names` を付ける**）:

```bash
python3 .claude-plugin/scripts/measure-interventions.py --labels <出力 dir>/labels.jsonl --out <出力 dir>
```

- `unmatched_labels` が 0 でなければ、次のどれか: `session` / `ts` / `qi` の写し間違い・対象外の行（slash・bash・
  card・free-text 以外の question）への分類・欄の型違い（`qi` が文字列など）・step 1 と違う期間の指定・events を
  作り直した後の古い分類
- `duplicate_labels` が 0 でなければ、同じ発話を 2 回分類している（2 行目以降は数えない）
- 移し先の表の `(未記入)` は、修正・差し戻し・方針の指定に target を付け忘れた行

### 3. 2 台を合算する

```bash
python3 .claude-plugin/scripts/measure-interventions.py --merge m1/summary.json m2/summary.json --out <出力 dir>
```

- 合算もスクリプトでする（LLM に足させない）。プロジェクトは `M1-P1` のようにマシンごとに分けて残る
- 入力は `--names` を付けずに作った summary にする（合算は伏せ字をかけ直さない）。期間の指定が揃っていない・
  伏せ字なしの summary が混ざるときは WARN が出る

## 読み方（機械へ移す候補）

| 見るところ | 候補 |
|---|---|
| 推奨率の高い AskUserQuestion の見出し（m1 の `--names` 出力だけで見る。m2 の分は含まない） | 聞かずに既定で進める（結果をレポートに出す） |
| 推奨率の低い見出し | 推奨の既定が人の判断とずれている。既定を直す |
| continue・routine の多いスキル | 止まる必要の無い所で止まっている。停止点を見直す |
| 修正・差し戻しで target が「決定的な検査」 | hook・script の事後条件にする（AI-DLC の区画 2） |
| 修正・差し戻しで target が「LLM の判定」 | 反証の層か事後条件の文として書く。完了の判定は人に残す |
| hook-block | すでに機械へ移した介入。停止が多すぎる hook は誤検出を疑う |
