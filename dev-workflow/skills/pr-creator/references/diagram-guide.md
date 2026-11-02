# 説明図の型と描き方（pr-creator Step 4.6 / GitHub issue #349）

Step 4.6 で「作る」と決めた後に読む。作るかどうかの判定は SKILL.md の Step 4.6 のまま。

## 1. 型を選ぶ

1 枚 1 主題で、主題ごとに型を選ぶ。1 つの PR で型が混ざってよい。

| 型 | 向く主題 | 差分に出るシグナル |
|---|---|---|
| `state`（状態遷移図） | 状態の移り変わり | 状態の enum・status の列・送信中や読み込み中のフラグ・開閉の操作・論理削除の印 |
| `sequence`（シーケンス図） | 層・モジュールをまたぐ呼び出しの順と分岐 | 画面 → Server Action / API → UseCase → Repository のように 3 つ以上の層を順に呼び、途中の分岐・エラー・早期 return で抜ける |
| `flow`（箱と矢印） | 流れ・導出の起点と範囲・レビューの範囲 | 集計・導出の起点や範囲が変わる / データの流れを付け替える / 「ここまでが今回の変更」を示したい |

同じ主題に複数のシグナルが当たるときは、読み手が追いたい問いで選ぶ:

- 「何がどの順で起きるか」→ `sequence`
- 「どの状態にいられて、何で移るか」→ `state`
- 「何が何から作られるか / どこまでが範囲か」→ `flow`

変更前後の対比のために型を変えたり、図を 2 枚に分けたりしない。変更後の図に、消した部品を `removed`、足した部品を `added`、変えた部品を `changed` で描いて 1 枚にする。2 枚に分けると、どこが変わったかを読み手が自分で突き合わせることになる。

選んだ型と理由（1 行）は、Step 4.95 の提示に図ごとに出す。例: `型: sequence（Server Action → UseCase → Repository を順に呼び、NotFound で抜ける経路がある）`

## 2. 定義を書いて組む

型ごとの JSON 定義を書き、`scripts/diagram-svg.py` で SVG にする。座標は書かない（スクリプトが並べる）。手で SVG を組むと、全角の文字幅・矢印の先の大きさ・見出しの重なりで毎回つまずく。この 3 点はスクリプトの中で固定してある。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/diagram-svg.py" '<控えたパス>/<名前>.json' …
```

定義はヒアドキュメントで書くとき、区切りを引用する（`cat > '<控えたパス>/<名前>.json' <<'EOF'`）。引用しないと、ラベルの `$` やバッククォートがファイルに書く前に展開される。

出力は 1 定義につき 1 行（警告があれば続けて出る）。1 件が失敗しても、残りの定義は処理する:

| 行 | 意味 | すること |
|---|---|---|
| `svg=<パス>` | 書けた | その SVG を svg-to-png.sh に渡す |
| `warn=<パス>\t<理由>` | 書けたが直したほうがよい | 理由に沿って定義を直し、組み直す（§5） |
| `failed=<定義のパス>\t<理由>` | 書けなかった | 理由（知らないキー・id の参照先が無い・値の型が違う・SVG に書けない文字・想定外のエラーなど）に沿って直す。前回書いた同じ名前の .svg は消えずに残るので、その図（と PNG）は `ATTACH` に入れない |

### 全型に共通のキー

| キー | 既定 | 意味 |
|---|---|---|
| `type` | 必須 | `flow` / `sequence` / `state` |
| `title` | 無し | 図の上に出す題。PR 本文の「何についての図か」と同じ文になるなら省いてよい（本文と図で 2 回言うことになる） |
| `legend` | `true` | 凡例を出すか。使った status（箱・線・範囲の枠）と返り値だけが並ぶ。全部 `existing` で返り値も無ければ出ない |
| `legend_labels` | 無し | 凡例の文言の差し替え。例: `{"later": "PR-2 で足す"}`（キーは status 名か `reply`。値は空にできない。凡例を消すなら `legend: false`） |

### status（箱・線・参加者・状態に付ける）

| status | 見た目 | 使いどころ |
|---|---|---|
| `added` | 緑 | この PR で足した |
| `changed` | 橙 | この PR で変えた |
| `removed` | 赤・取り消し線 | この PR で消した（変更前後の対比） |
| `existing` | 灰（既定） | 既存。触っていない |
| `later` | 灰の破線の箱・点線の線（返り値は一点鎖線） | 後続の PR で足す・変える部品。PR を分けたときの全体像を見せる |

ラベルは 1 つの箱で 1〜2 行（`\n` で改行。線のラベル・枠の条件も改行できる）。名前は diff に出てくる関数・画面・テーブルの名前に合わせ、本文に無い用語を図だけに持ち込まない。`label` を省くと `id` がそのまま描かれる。

## 3. 型ごとの定義

### `sequence`

```json
{
  "type": "sequence",
  "participants": [
    {"id": "ui", "label": "一覧画面"},
    {"id": "act", "label": "Server Action", "status": "added"},
    {"id": "uc", "label": "DeleteItemUseCase", "status": "added"},
    {"id": "repo", "label": "ItemRepository", "status": "changed"},
    {"id": "audit", "label": "監査ログ", "status": "later"}
  ],
  "steps": [
    {"from": "ui", "to": "act", "label": "deleteItem(id)", "status": "added"},
    {"from": "act", "to": "uc", "label": "execute(id)", "status": "added"},
    {"from": "uc", "to": "repo", "label": "findById(id)"},
    {"frame": "alt", "branches": [
      {"label": "見つからない", "steps": [
        {"from": "repo", "to": "uc", "label": "null", "reply": true},
        {"from": "uc", "to": "act", "label": "NotFound", "reply": true, "status": "added"}
      ]},
      {"label": "見つかった", "steps": [
        {"from": "uc", "to": "repo", "label": "softDelete(id)", "status": "changed"},
        {"from": "uc", "to": "audit", "label": "record(削除)", "status": "later"}
      ]}
    ]},
    {"from": "act", "to": "ui", "label": "revalidatePath", "reply": true}
  ]
}
```

- 参加者は、最初に呼ばれる順に左から並べる（矢印が左から右へ流れる）
- 呼び出しは `from` / `to` / `label`。返り値は `"reply": true`（破線）。`from` と `to` が同じなら自分を呼ぶ矢印になる
- 枠（`frame`）は `alt`（条件で分かれる。`branches` に分岐ごとの `label` と `steps`）/ `opt`（条件を満たすときだけ）/ `loop`（繰り返し）/ `par`（並行）/ `break`（途中で抜ける）/ `critical`。分岐の無い枠は `{"frame": "opt", "label": "<条件>", "steps": [...]}`。`branches` を使う枠には枠直下の `label` を書けない（条件は各分岐の `label` に書く）。枠は入れ子にできる
- 全部の呼び出しを描かない。主題（分岐・抜ける経路・この PR で足した呼び出し）に関わる呼び出しだけを残す

### `state`

```json
{
  "type": "state",
  "initial": "closed",
  "states": [
    {"id": "closed", "label": "閉じている", "pos": [0, 0]},
    {"id": "open", "label": "確認中", "status": "added", "pos": [1, 0]},
    {"id": "sending", "label": "送信中", "status": "added", "pos": [2, 0]},
    {"id": "done", "label": "完了", "status": "added", "final": true, "pos": [3, 0]},
    {"id": "error", "label": "失敗の表示", "status": "later", "pos": [2, 1]}
  ],
  "transitions": [
    {"from": "closed", "to": "open", "label": "削除を押す", "status": "added"},
    {"from": "open", "to": "closed", "label": "キャンセル", "status": "added"},
    {"from": "open", "to": "sending", "label": "削除する", "status": "added"},
    {"from": "sending", "to": "done", "label": "成功", "status": "added"},
    {"from": "sending", "to": "error", "label": "失敗", "status": "later"},
    {"from": "error", "to": "open", "label": "やり直す", "status": "later"},
    {"from": "done", "to": "closed", "label": "閉じる", "status": "added"}
  ]
}
```

- 状態は節、操作（イベント）は辺の `label`。辺の `label` には操作の名前を書き、条件や処理の説明を書き込まない
- `initial` は始まりの状態（黒丸から矢印が入る。黒丸は左・上・下のうち、線や箱に掛からない側に置く）。`"final": true` は終わりの状態（二重の枠）。`from` と `to` が同じ辺は、箱の右上の角に掛かる輪になる
- `pos: [列, 行]` を省くと、`initial` から辺をたどって左から右へ並べる。状態が 5 つを超えるときや、戻る辺が 2 本以上あるときは `pos` を付ける。主な流れを行 0 に左から並べ、脇道（失敗・取り消し）を行 1 に置くと、戻る辺が交差しにくい。`pos` は全部に付けるか、どれにも付けない。値は整数で書く（小数で箱が重なると warn= が出る）

### `flow`

```json
{
  "type": "flow",
  "nodes": [
    {"id": "src", "label": "注文テーブル"},
    {"id": "old", "label": "全期間を集計", "status": "removed"},
    {"id": "filter", "label": "今月の注文に絞る", "status": "added"},
    {"id": "agg", "label": "monthlyTotal()", "status": "changed"},
    {"id": "view", "label": "ダッシュボード"}
  ],
  "edges": [
    {"from": "src", "to": "old", "status": "removed"},
    {"from": "src", "to": "filter", "label": "createdAt", "status": "added"},
    {"from": "old", "to": "agg", "status": "removed"},
    {"from": "filter", "to": "agg", "status": "added"},
    {"from": "agg", "to": "view"}
  ],
  "groups": [
    {"label": "レビューで見てほしい範囲", "nodes": ["filter", "agg"], "status": "added"}
  ]
}
```

- `direction` は `LR`（既定。左から右）か `TB`（上から下）。層が深い（4 段を超える）流れは `TB` のほうが幅に収まる
- `groups` は箱の集まりを破線の枠で囲む。「この PR の範囲」「レビューで見てほしい範囲」「後続の PR で触る範囲」に使う。自動で並べるときは、枠の中の箱を各列（TB なら各行）の先頭に寄せる
- `pos` の扱いは `state` と同じ。`pos` を全部に付けると `direction` は使われない（`pos` はいつも [列, 行]）

## 4. 描き方の決まり（スクリプトが固定していること）

定義を書く側は気にしなくてよい。手で SVG を直すときにだけ守る:

- 文字の幅は全角と曖昧幅（`→` `①` `×` など）を 1 文字 = 1em で見積もる。英字の幅で見積もると日本語が箱や枠の見出しからはみ出す
- 矢印の先は `<marker markerUnits="userSpaceOnUse">` で大きさを固定する。既定（`strokeWidth`）だと線の太さに比例して膨らむ
- ライフラインの見出しの箱は、見出しの幅から列の間隔を決めて並べる。間隔を固定すると、長い見出しが隣と重なる
- ルートの `<svg>` に `width` / `height`（px の数値）を書き、最初に白い背景の `<rect>` を置く（svg-to-png.sh の撮影範囲になり、GitHub のダークテーマでも読める）
- 線のラベルは白地を付けて前面に置き、箱・範囲の枠の見出し・他のラベルと重ならない位置を座標で確かめる。縦の線のラベルは線の横に出す。置き場が無ければ warn= を出す（画像を見ない手順では、これが重なりを知る合図になる）

## 5. `warn=` が出たとき

| 理由 | 直し方 |
|---|---|
| 幅が 1200 を超えた | 主題を分ける（2 枚にする）か、ラベルを短くする。`flow` なら `direction: TB` も試す（`pos` を全部に付けているときは効かない） |
| 線が他の箱を横切る | `pos` を付けて並べ直す（横切られている箱を別の行へ移す） |
| ラベルが他のラベルか箱と重なる | 同じ 2 つの箱の間の線を減らすか、ラベルを短くする。`pos` で箱の間隔を空ける |
| 箱と箱が重なる | `pos` を整数にして、箱の間隔を 1 以上空ける |
| 始まりの黒丸が他の箱か線と重なる | `pos` で `initial` の状態の左・上・下のどれかを空ける |
| 枠に、メンバーでない箱が入った | `pos` を付けて、枠の外の箱を別の行・列へ移す |

直しても消えない warn= は、そのまま進めてよい。PNG を開いて読めることを確かめ、残った理由を Step 5 のレポートに 1 行添える。

## 6. スクリプトが使えないとき

`python3` が無い・`failed=` が直らないときは、SVG を手で書いてよい。§4 の決まりを守り、変更した部品は §2 の status の色で区別して、使った status の凡例を付ける。フォントは `font-family="Hiragino Sans, Noto Sans CJK JP, Yu Gothic, sans-serif"`、幅は 1200 以下にする。手で書いたことを Step 5 のレポートに一言添える。
