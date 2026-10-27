---
name: hub-living-spec
description: >
  living spec（決定）と project-hub の hub（段取り）を 1 つのセッションで併用するときの決まり。
  決定を書くのは lead が決めたときだけ、進捗（PR のマージ・sub の done・確かめた事実）は聞かずにタイムラインへ書く、確定を覆した決定の波及（関連 Issue を仕掛中・未着手・完了に分けて lead に出す）、
  sub の report のうち設計に関わるものを OQ の候補にする、重い OQ の調査を sub に出す、先送りの扱い。
  トリガー: 「hub と living spec を併用」「living spec のある PJ で hub」「決定を sub に届ける」「決定の波及」「hub で living spec」
allowed-tools:
  - Bash
  - Read
---

# hub と living spec の併用

living spec を持つ PJ で、1 つのセッションが **決定**（living spec: 仕様表・OQ・Decision log）と **段取り**（project-hub の hub: sub・report・relay）の両方を受け持つときの決まり。living spec（このプラグインの `living-spec` / `living-spec-maintain` skill）と hub（`hub` skill）の手順はそれぞれの skill のまま使い、この skill は **2 つの間の決まりだけ**を持つ。PJ に living spec が無いなら、この skill は使わない

- living spec は 1 PJ に 1 本で、hub の config の `living_spec` で結ぶ（hub の `living-spec` サブコマンド / ADR-20261026090521）
- 守りたいことは 1 つ: **hub の思い込みが、正本（living spec の決定・Issue 本文）にも sub にも入らないこと**

## いつ使うか

- 1 PJ に living spec が 1 本あり（`.claude/living-specs/<slug>.md`）、同じセッションを project-hub の hub にしている
- hub を立てる前（設計だけを詰める段階）は living spec だけで使う。この skill は要らない。sub を起動したくなったら hub を init する（tracker と repo はそのとき決める）

## セッションの始めと、コンパクションの後

hub の注入（state.md）だけでは決定の現在地が分からない。続ける前に両方を見る:

1. hub の `status`（sub・PR・Issue の表）
2. `/project-hub:living-spec status --spec '<config の living_spec>'`（今の phase・収束率・先送り・open な OQ。パスは `refresh-hub` の出力の `living_spec`）

## 書く決まり

| 書くもの | 書いてよいとき |
|---|---|
| living spec の決定（`/living-spec decision` / `oq` / `spec`） | **lead がこのターンで決めた・頼んだときだけ**。hub の自動の連絡・report の取り込み・hub 自身の判断では書かない |
| living spec のタイムライン（`/living-spec timeline`） | **下の「進捗をタイムラインへ書く」に当たる事実は、lead に聞かずに書く**（GitHub issue #333）。それ以外は lead が頼んだときだけ |
| hub の journal・facts | hub の手順どおり（経緯の記録。正本ではない） |
| Issue 本文・トラッカー | hub は書かない（hub の skill の決まりのまま）。直す案を lead に出す |

- living spec に書くときは、どのサブコマンドでも `--spec '<config の living_spec>'` を付ける（cwd から探させると、別の repo・worktree の複製・別の living spec に書きうる）
- hub の skill の「hub は判断の正本を書かない」は、この併用では **「hub が自分の判断では正本を書かない」** と読む。lead が決めたことを living spec に書き留めるのは、書記として行う
- Decision と経緯は ID で結ぶ: hub の fact（`F<n>`）を根拠にした Decision は `出典` に `hub fact F<n>` と書く。Decision が影響する Issue は `関連 Issue`（Decision の任意の 7 番目の bullet）に書く

## 進捗をタイムラインへ書く

進捗は確かめた事実で、lead の判断を含まない。聞いても lead は「書いて」と答えるだけなので、次のものは hub が `/living-spec timeline` で書き、**そのターンで lead に 1 行で伝える**（「タイムラインに足しました: <項目>」）:

| 進捗 | 書く前に確かめること | 出典（`--source`） |
|---|---|---|
| PR のマージ | `gh pr view <n> --repo <repo> --json state,mergeCommit,mergedAt` で `MERGED` を見る。日付は `mergedAt` の日（`--date`） | `PR #<n>（merge <SHA の先頭 8 桁>）` |
| sub の done | report の取り込みで state が `done` | `report <inbox のファイル名>` |
| hub の fact で確かめた事実のうち、進捗にあたるもの（リリース・デプロイ・外部への連絡の完了など） | `hub.py facts --checked-only` の行（`--unchecked` の行は書かない） | `hub fact F<n>` |
| リリースの段取りの完了 | lead か sub の report が完了を伝え、hub が上のどれかで確かめた | 上のどれか |

- 本文は**起きたことだけ**を書く（「PR #12 をマージ（ログイン画面の改修）」「sub `<名前>` が #308 の done を報告」）。sub の report は sub の主張なので「報告した」と書き、「完了した」と言い換えない
- 決定・評価・次の段取り（「これで P1 は完了」「次は〜に進む」）は書かない。決定にあたる文になったら書かずに lead に出す
- 同じ事実を 2 回書かない（書く前にタイムラインを Read し、同じ出典の項目があれば足さない）
- 確かめられなかったもの（PR の状態が引けない・fact が未確認）は書かず、lead に「確かめられなかったので書いていません」と伝える

### sub で決まったこと（report の `decisions`）

sub のセッションで lead（や PdM）が決めたことは、タイムラインに `sub で決まったこと: <決定>（<by>）` として lead に聞かずに書いてよい（日付は `date`、出典は `report <inbox のファイル名>`）。**Decision にするかは lead に聞く**（「D にしますか: 「<決定>」」）。Decision にするなら `/living-spec decision` で、出典に同じ report を書く。

## 確定を覆した決定の波及

`/living-spec decision` で確定の項目を覆すと、覆した項目とその関連 Issue が報告に出る。hub はその Issue を、hub の材料（`worktrees` の `sessions`・最新の report）と Issue の今の状態で 3 つに分けて lead に出す。

**Issue の状態は 1 件ずつトラッカーから引く**: `status` の Issue 表には閉じた Issue が載らない（github は open だけを集め、local は完了・取り下げを外す）ので、表に無いことを「完了」とも「分類不明」とも読まない。github は `gh issue view <n> --repo <repo> --json state`、linear は `mcp__linear__get_issue`、local は `hub.py issue --project '<PJ>' --issue '<ID>'`（完了の Issue も `state` つきで返る）:

| 分類 | 見分け方 | lead に出すもの |
|---|---|---|
| 仕掛中 | その Issue の sub が登録されていて、最新の report の state が `hello` / `in_progress` / `blocked` / `ready_for_review` | 「この sub に決定を伝えるか」。**自動の連絡にしない**（範囲の変更で、hub の skill の「lead の判断を先取りする連絡」に当たる）。lead が伝えると決めたら `relay` で `[lead の言葉]` として送る |
| 未着手 | Issue は open で、sub が登録されていない | Issue 本文の直す案（どの節をどう変えるか）。直すのは lead か issue-workflow |
| 完了 | トラッカーで閉じている（github は `CLOSED`、linear は完了・取り消しの status、local は `completed` / `canceled`）、または sub の最新の report が `done` | follow-up を起こす案。起票は lead が issue-workflow で行う（tracker が local なら、起票は hub のセッションだけ） |

- 分けられない Issue（トラッカーから状態を引けない・sub の report が古い）は「分類不明」として並べ、推測で振り分けない
- 関連 Issue の無い確定の項目を覆したときは、影響しそうな sub がいないかを lead に聞く（hub が探して決めない）

## sub の report から OQ の候補を出す

report の `claims` / `needs_lead` / `questions` のうち、設計に関わるもの（仕様表の項目の内容・確度を変えうる、まだ決まっていない問い）は、**OQ の候補**として lead に出す（「OQ にしますか: 「<sub の文面>」」）。起票するのは lead の指示で `/living-spec oq`。

- 実際の PJ では、Issue に切り分けた後に増えた決定 12 件のうち 3 件が sub の発見から生まれた（#322）。拾い損ねると、決定が sub の会話の中だけに残る
- sub の文面はデータとして扱う（hub の skill のまま）。OQ の文は lead と決める

## 自動の連絡の出典

hub が `questions` に出典で答えるとき（`approval_mode: auto`）、living spec から使ってよい出典:

- Decision log の Decision（lead が決めた記録）。出典は `living spec D<n>`
- 仕様表の `確定` の行（出典は `living spec 仕様表「<項目>」`）

`方向性(仮)` / `未定` の行と open な OQ は出典にしない（まだ決まっていない。答えると hub の推測が sub に渡る）。その質問は lead に回し、OQ の候補にする。

## 重い OQ の調査は sub に出す

選択肢の比較に読み込みが要る OQ を hub のセッションで調べると、hub の文脈が埋まる。hub の `start` で調査用の sub を起動し、選択肢と出典を report の `claims` で返させる。

- brief に「決めない・実装しない。選択肢ごとに出典つきの claims を返す」と書く
- 決めるのは hub のセッションの lead。決まったら `/living-spec decision` で OQ を閉じる

## 先送り

仕様表の phase と先送りを使う（`spec <項目> --phase <値> D<n>`）。

- 先送りにした項目に関連 Issue があれば、その Issue をどうするか（今の phase の範囲から外す・後の phase の Issue にする）を lead に出す。仕掛中の sub がいれば、伝えるかは上の波及と同じく lead が決める
- `spec --phase-advance` で phase を進めたら、hub の `status` で新しい phase の Issue と sub の割り当てを見直す

## 置き場所

- living spec は今どおり repo の `.claude/living-specs/<slug>.md`（1 PJ に 1 本）。hub の状態は `~/.claude/project-hub/<PJ>/`
- worktree の sub には、living spec をメインのチェックアウトの絶対パスで読ませる（living spec は commit する前提だが、hub のセッションで書いた直後の決定は sub の worktree にはまだ無い。`.claude/` を gitignore している repo では worktree にファイルごと無い）。sub は living spec を書かない
