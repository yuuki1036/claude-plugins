# recall 回帰 fixture（GitHub issue #75 / #386）

code-review の high-risk recall 補強（Tier3 v2.30.0 / Tier2 v2.31.0 / Tier1 v2.32.0）が、
実レビューで見落とした実バグ（issue #75 #1 / #7）を捕捉できるかを測る回帰 fixture。
設計は [design doc](../../../.claude/designs/20260703-code-review-recall-high-risk-surface.md) の「検証方法」を実装したもの。
`08` はその後に足した fixture で、bug-detection の「例外・早い return の後ろの後片付け」の点検（issue #353）が
効いているかを測る（issue #386。high-risk surface は含まない）。

> `evals/runner.py` は「トリガーフレーズ → skill 選択」の決定的回帰のみを扱う。
> この fixture は **レビュー指摘レベルの recall / precision** を測るランタイム検証で、
> LLM 実行を伴うため runner.py には統合しない（半自動 runbook 方式）。

## fixture 一覧

| id | 種別 | 再現対象 | 期待 |
|---|---|---|---|
| `01-value-flow-insert` | recall | #75 #1: 空文字が `?? null` を素通り → NUMERIC 列へ生 INSERT → 22P02 → 500 | **CRITICAL 以上**で報告 |
| `07-handler-bypass` | recall | #75 #7: 共有エラーハンドラ迂回で SERVICE_UNAVAILABLE の error ログが消える | **MAJOR 以上**で報告 |
| `08-rethrow-skips-cleanup` | recall（対照つき） | #386: catch に足した `unstable_rethrow(err)` の経路だけが finally の外の `closeDialog()` に届かず、ルートのダイアログが遷移先に残る | 投げ直しの `+` 行を **MAJOR 以上**で報告。同じ catch の入力エラーの `return`（意図してダイアログを残す）は MAJOR 以上で**指摘しない** |
| `90-precision-minor-unit` | precision | 副単位ゲート（正しいコード）への誤検出 | CRITICAL/MAJOR が**出ない** |

期待値の詳細（対象ファイル・キーワード・判定根拠）は [expected.yaml](expected.yaml)。

## 実行手順（半自動 runbook）

### 前提

- `code-review` plugin **>= 2.32.0** がインストール済み（Tier1 の skeptic / surface-aware 閾値を含む）。
  古い場合は `/update-all` か `claude plugin update code-review` で更新する
- 08 は code-review **>= 2.165.2**（bug-detection に #353 の「例外・早い return の後ろの後片付け」の節が入った版）で測る
- effort は **xhigh** で実行する（self-review skill の frontmatter 既定。skeptic の起動条件）

### 1 fixture の実行

```bash
# 1. fixture repo を構築（surface 判定の発火チェックまで自動）
cd evals/fixtures/recall
./setup.sh 01-value-flow-insert

# 2. 出力された temp dir で self-review を実行し、レポートを保存する（コマンド名は名前空間付きで指定）。k=3 回
OUT=$(mktemp -d) # レポートの保存先
cd <出力された target dir>
for i in 1 2 3; do claude -p "/code-review:self-review" --permission-mode plan > "$OUT/run$i.md"; done
# 対話モードなら: claude を起動して /code-review:self-review し、「セルフレビュー結果」以降を run<i>.md に保存する

# 3. 判定する（repo のルートで。expected.yaml と 3 本のレポートを突き合わせ、結果の記録の表を出す）
python3 evals/fixtures/recall/judge.py 01 "$OUT"/run{1,2,3}.md
```

`judge.py` の exit は 0 PASS / 1 FAIL / 2 判定不能（レポートが 3 本でない・「セルフレビュー結果」の無いファイル・
fixture id の誤り・PyYAML が無い・「指摘件数」の行と読めた指摘の数が合わない）/ 3 要確認（機械で決まる範囲は PASS で、人が本文を読んで決める候補が残る）。要確認の候補は表の下に並ぶので、
下の判定ルールの**[人]** の条件で人が決める。`--embed` は付けない（採否の確認と Markdown 推敲を省くので、
計測条件が変わる。2026-11-07 決定）。PyYAML が要る（`pip install pyyaml`）。

> **⚠️ コマンド名は必ず名前空間付き `/code-review:self-review` で指定する**
> 名前空間なし `/self-review` や自然文プロンプトはユーザーグローバルの旧 self-review
> skill 等に解決され、素の単騎レビューになって Tier1 パイプラインを測れない
> （2026-07-04 スモークの「headless で skill 不起動」の実際の原因。2026-07-08 の
> 本計測で名前空間付きなら headless でも skill が起動することを確認済み）。
> 各 run とも transcript に **「Phase 0 トリアージ結果」表が出ること**で skill 起動を
> 確認してから記録する。skill 起動が確認できない run はカウントせず再実行する。
>
> **⚠️ plan mode では `review:completed` event が publish されない**（書き込み制約）。
> fixture 計測は issue #77 の recall_skeptic 集計データに寄与しない。
>
> **合成 fixture の解釈上の注意**: fixture は最小 diff（実 PR より探索空間が狭い）なので
> 実バグより見つけやすい。PASS は「デグレしていない」ことの回帰確認であり、
> 「実バグ級を必ず捕捉できる」の証明ではない。
> 08 はとくに、測る点検（`code-review/references/prompts/focus/bug-detection.md` の「例外・早い return の後ろの後片付け」）が
> 同じ catch に投げ直しと意図した `return` が並ぶ形を例として書いている。PASS はその例どおりの形を拾えることの確認で、
> 別の形の後片付け漏れへの汎化は示さない。

### 判定ルール

`judge.py` が機械で決めるのは、下のうち **[機械]** と書いた条件だけ。**[人]** の条件は候補を挙げるだけで、最後は人が決める。

- **recall fixture（01 / 07 / 08）** **[機械]**: k=3 回実行し **2 回以上**で期待指摘（severity・対象ファイル・キーワード。
  `expect.target_lines_any` があれば、指摘の主対象の行がそのどれかを含むことも）が報告されれば PASS。
  LLM の非決定性を吸収するため 3/3 は要求しない
- **主対象の行**: レポートの指摘の `ファイル:` 欄が指す行（範囲なら範囲の全行）。根拠や本文に並べた行は数えない。
  報告外の節（🔁 報告閾値を割った指摘・✏️ コメント推敲）の行も数えない
- **対照（`expect.must_not_flag`。08）**: k=3 回のうち **1 回でも**、次のどれかに当たる MAJOR 以上が出たら
  FAIL（precision fixture と同じ厳格さ）。recall 側が PASS でも fixture 全体は FAIL。判定規則の正本はこの節
  （expected.yaml の冒頭はここを指すだけ）
  - **[機械]** 主対象の行が対照の行（`must_not_flag` の `target_files_any` のファイルの、`target_lines_any` の行。
    ファイルと行の両方）を含み、期待指摘の行（`expect.target_lines_any`）を含まない
  - **[機械]** 主対象の行が期待指摘の行も、飛ばされる後片付けの行（`expect.cleanup_lines`。08 では 57 行目の
    `closeDialog()`）も含まない指摘が `false_positive_patterns` に合致する
  - **[人]** 主対象の行が期待指摘の行か飛ばされる後片付けの行を含む指摘、または `ファイル:` 欄に行番号の無い指摘でも、
    本文が対照の経路まで欠陥・要修正と述べている（入力エラーでも
    ダイアログを閉じるべき、`closeDialog()` を無条件に `finally` へ移す、など。無条件に移すと、入力エラーで
    ダイアログを残す対照の UX を壊す）
  - 期待指摘の行・飛ばされる後片付けの行を指すか行番号の無い指摘で、本文で対照の経路と比べるだけ（対照の
    `return` は意図した残しと読む）のものは数えない（patterns に合致しても数えない）。
    脱出口ごとに意図を比べる書き方こそ測りたい振る舞いなので、本文の字面だけで FAIL にしない
  - `judge.py` は上の **[人]** の項に当たりうる MAJOR 以上を「要確認」に挙げる。期待指摘の行だけを指す指摘は、
    本文が対照に触れている（`must_not_flag.mentions_any` のどれかを含む）ものに絞る（期待指摘そのものを毎回挙げない
    ため）。後片付けの行を指す指摘と行番号の無い指摘は絞らない（`closeDialog()` を無条件に `finally` へ移す、のように
    対照に触れずに対照を壊す形がある）。対照のファイルを行番号なしで挙げた指摘は、別のファイルに行があっても行番号の
    無い指摘に数える
- **precision fixture（90）** **[機械]**: k=3 回実行し **1 回でも** `false_positive_patterns` に合致する
  CRITICAL/MAJOR が出たら FAIL（誤検出の復活は surface-aware 緩和の失敗を意味するため厳格）
- 01 では **skeptic（Phase 4.8）が起動したこと**もレポートで確認する（`judge.py` が「動的ラウンド」の行の
  `冷や読み skeptic` を表の「skeptic 起動」に写す。判定には使わない）
  （起動しなかった / 失敗した場合は `missing_coverage` に `recall-skeptic:` が出るはず。
  silent 失敗はそれ自体が Tier1 のバグ）

### 結果の記録

実行結果は `evals/reports/recall-YYYYMMDD.md` に以下の形式で記録する（`judge.py` が fixture ごとにこの表の行と
「総合」の行を出す。「判定」と「備考」の列と、要確認を決めた結果は人が書き足す）:

```md
# recall fixture 実行結果 (YYYY-MM-DD, code-review vX.Y.Z)

| fixture | run | 期待指摘の報告 | severity | skeptic 起動 | 対照 | 判定 | 備考 |
|---|---|---|---|---|---|---|---|
| 01 | 1/3 | ✅ | CRITICAL | ✅ | - | - | |
| 08 | 1/3 | ✅ | MAJOR | - | ✅（指摘なし） | - | 修正案: 投げ直す前に閉じる |
| ... | | | | | | | |

総合: 01 PASS (3/3) / 07 PASS (2/3) / 08 PASS (2/3, 対照 0/3) / 90 PASS (0/3 FP) → recall 回帰 PASS

- 「対照」は `must_not_flag` を持つ fixture（08）だけに書く（それ以外は `-`）
- 「備考」は判定に使わない観察を書く（08 なら期待指摘の修正案の形。投げ直す前に閉じる / 残すかのフラグを立てて `finally` で閉じる、など）
```

判定後、design doc の「実装状況」に結果と `last-validated` を反映する（01 / 07 / 90 の分。08 はこの design doc の
範囲の外なので反映せず、記録ファイルに残すだけにする）。

## Tier1 縮小の出口条件（design doc open「Tier1 打ち切り条件」）

01 / 07 が **skeptic なし（`enable_recall_skeptic: false`）でも安定して捕捉できる**場合、
Tier2（敵対的入力逆算 + 帰結接続義務化）だけで十分な可能性がある。その場合は
skeptic の起動ゲートをさらに絞る（または既定 false にする）縮小判断の材料にする。
比較実行: 同じ fixture を userConfig `enable_recall_skeptic: false` で k=3 追加実行し、
捕捉率の差分を見る。
