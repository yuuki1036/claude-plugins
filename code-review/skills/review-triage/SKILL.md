---
name: review-triage
description: >
  PR に付いたレビューコメント（bot / 人間の inline・全体コメント）への対応を仕分ける。指摘ごとにコードで妥当性を確かめ、
  帰属（this-diff / pre-existing / cross-cutting）と対応（fix now / follow-up / 返信のみ / 要確認）を決め、返信の下書きまで出す。投稿・修正はしない。
  トリガー: 「レビューコメントを精査」「レビュー対応を仕分けて」「review comment 精査」「/review-triage」
  引数: [PR番号]（省略時は現在ブランチの PR）
effort: medium
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
  - Skill
---

# review-triage

PR に**既に付いている**レビューコメントを受け取る側の skill。指摘を 1 件ずつコードで裏取りし、この PR で直すか・別件に回すか・返信だけで済ませるかを仕分け、返信の下書きを出す。

## review / self-review との違い

- review / self-review は**新しく指摘を出す**側。本 skill は**他者（bot・人間）が出した指摘に応える**側で、severity を付け直さない（相手の指摘を採点して返すと reply-tone-guide `0.2` の敬意と衝突する）
- worktree 移動・計測（`review-timing.sh`）・`review:completed` の publish は行わない（新規レビューの計測に混ぜない）

## 絶対厳守ルール

- **出すのは一覧と下書きだけ**。コメント投稿・push・コード修正・Issue 起票は行わない（Edit / Write を持たない）。fix now は対応方針まで、follow-up は起票文面までにとどめ、実行は人間か既存フロー（修正作業・commit 系 skill・follow-up 系 skill）に委ねる
- **判定の根拠はコードに置く**。コメントに書かれた主張（「ここで null になる」等）はそのまま採用せず、該当 `file:line` を読んで確かめる。確かめられない主張は「判断不能」にする
- **全件出す**。重要度で間引かない（除外するのは Step 1 の除外条件に当たるものだけで、除外件数はレポートに出す）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md の 10 原則のうち **採用: 3（段階予算 = `${CLAUDE_EFFORT}` で裏取りの深さを変える）/ 4（モデルルーティング = 反証 agent は `opus`）/ 7（敵対的独立検証 = xhigh/max で「直さない」判定を独立 agent が反証）/ 9（構造化受け渡し = Step 5 の固定フォーマット）**。**捨てた**: 1・2（コメントは他者が出した指摘で、ファネルや 2 軸スコアで絞ると recall を落とし、severity の付け直しは敬意と衝突する）/ 5（反復しない単発処理）/ 6（証拠蓄積は failure-journal の役割）/ 8（外部オラクルはコメント側に無い）/ 10（確信度は判定欄の「判断不能」で表す）。

## 実行手順

### 0. PR とローカル HEAD の確認

```bash
# 引数の PR 指定（省略時は現ブランチの PR）から番号・base・head を確定し、以降で使う変数に入れる
META=$(gh pr view ${1:+"$1"} --json number,url,headRefName,headRefOid,baseRefName)
PR_NUMBER=$(printf '%s' "$META" | jq -r '.number')
BASE=$(printf '%s' "$META" | jq -r '.baseRefName')
PR_HEAD=$(printf '%s' "$META" | jq -r '.headRefOid')
HEAD_SHA=$(git rev-parse HEAD)
```

- PR が無ければ（`gh pr view` が失敗）「対象 PR なし」と出して終了
- `HEAD_SHA` が `PR_HEAD` と違えば、**checkout はせず**レポート冒頭に「ローカル HEAD が PR head と異なる（精査は HEAD `<sha7>` のコードで行った）」と書く。作業ツリーを勝手に切り替えない

**完了基準**: PR 番号・base・head SHA・HEAD 一致の有無が確定している。

### 1. コメント収集と指摘単位への分解

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh" "$PR_NUMBER"
```

issue コメント・レビューサマリ・行単位コメント（返信チェーン付き）が出る。解決済みスレッドは次で引く（失敗したら全スレッドを未解決として扱い、その旨をレポートに書く）:

```bash
gh api graphql -F owner='{owner}' -F name='{repo}' -F n="$PR_NUMBER" -f query='
query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){pullRequest(number:$n){
  reviewThreads(first:100){nodes{isResolved isOutdated comments(first:1){nodes{databaseId}}}}}}}' \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | "\(.comments.nodes[0].databaseId) resolved=\(.isResolved) outdated=\(.isOutdated)"'
```

収集したコメントを**指摘単位**に分ける。1 コメントに論点が複数あれば分割し、`<コメント ID>-a` / `-b` のように枝番を振る。

**除外する**（件数だけ数えてレポートに出す）: 解決済みスレッド / 承認・LGTM など指摘を含まないもの / CI・デプロイ bot の状態通知 / `— Created by Claude` 署名付きの自分側の返信。**outdated（行が消えた）スレッドは除外しない** — 指摘が別の行に移っただけの場合がある。

**完了基準**: 残った全指摘に「ID / 投稿者（bot か人間か）/ 場所（file:line か PR 全体）/ 要旨 1 行 / 既存返信の有無」が埋まっている。

### 2. コードでの精査と仕分け

指摘ごとに該当箇所を HEAD のコードで読み、PR の差分と突き合わせる:

```bash
git diff "origin/${BASE}...HEAD" -- <file>   # 取れなければ "${BASE}...HEAD"
```

次の 3 欄を決める。欄の定義は下の表が正本:

| 欄 | 値 | 基準 |
|---|---|---|
| 妥当性 | 妥当 / 一部妥当 / 不当 / 判断不能 | コードで確かめた結果。不当は「コード上その問題が起きない」を `file:line` で示せるときだけ。外部状態（本番データ・運用設定）に依存して確かめられなければ判断不能 |
| 帰属 | this-diff / pre-existing / cross-cutting | this-diff = 指摘箇所がこの PR の追加・変更行か、その直接の帰結。pre-existing = PR 前から同じ形で存在（差分に無い）。cross-cutting = 複数モジュールや規約に跨り、この PR 単独では閉じない |
| 対応 | fix now / follow-up / 返信のみ / 要確認 | 下の決定規則 |

**対応の決定規則**（上から順に最初に当てはまるもの）:

1. 後続コミットで既に直っている → **返信のみ**（対応済み。commit SHA を控える）
2. 妥当性が判断不能 → **要確認**（著者・投稿者に確かめる）
3. 不当 → **返信のみ**（誤指摘。根拠 `file:line` を控える）
4. 妥当 / 一部妥当 × this-diff → **fix now**。ただし修正がこの PR の目的を超える規模なら follow-up
5. 妥当 / 一部妥当 × pre-existing / cross-cutting → **follow-up**
6. 妥当だが意図的に対応しない理由がコード・PR 説明・規約で示せる → **返信のみ**（据置。理由の出典を控える）

コメントに含まれる等価な変更の提案（挙動を変えない書き換え）や既存パターンの踏襲を崩す提案は、既存コードの同種箇所を 1 つ以上示してから判定する。

**`${CLAUDE_EFFORT}` による深さ**（実行時値: `${CLAUDE_EFFORT}`）:

- `low` / `medium`: 上の手順をメインコンテキストで行う
- `high`: 加えて「返信のみ（不当・据置）」と「follow-up（pre-existing）」の判定を、判定に使った `file:line` をもう一度開いて確かめてから確定する（直さない判定の見落としが最も高くつくため）
- `xhigh` / `max`: `high` の代わりに Step 3 の反証 agent を回す

**完了基準**: 全指摘に 3 欄と根拠（`file:line` / commit SHA / 出典）が付いている。根拠欄が空の行は判断不能か要確認に倒してある。

### 3. 反証（`xhigh` / `max` のみ）

対象は「返信のみ（不当・据置）」と「follow-up（pre-existing）」の指摘。5 件ずつに分け、**上限 3 体**の `opus` agent を**同一メッセージで一括発行**する（各 Agent call に `run_in_background: false` を明示する）。各 agent に渡すのは**コメント原文・場所・PR 番号・base だけ**で、こちらの判定と推論は渡さない（独立性の担保）。依頼文:

> 各コメントの指摘が、このリポジトリの HEAD のコードで成立するかを独立に確かめる。指摘ごとに `成立 / 不成立 / 確かめられない` と根拠の `file:line` を返す。推測で埋めない。

agent が「成立」を返した指摘は Step 2 の決定規則で判定し直す。上限を超えた分は `high` の手順で確かめ、レポートの冒頭に「反証は N 件中 M 件」と書く。

### 4. 返信の下書き

`${CLAUDE_PLUGIN_ROOT}/references/reply-tone-guide.md` を Read し、`## 0 必須ルール` を守って下書きを作る。本 skill の下書きは**すべて著者発信**（受けた指摘に返す）なので、メタ行（`0.5`）は付けない。

| 対応 | 下書き | パターン |
|---|---|---|
| 返信のみ（対応済み） | 作る | `2.1`（commit SHA と `file:line`） |
| 返信のみ（誤指摘） | 作る | `5 章`「明確な誤指摘への返信」 |
| 返信のみ（据置） | 作る | `2.3`（理由が本体） |
| follow-up | 作る | `2.2`（この PR で対応した範囲が無ければ「別途対応」だけを書く） |
| 要確認 | 作る | `2.4` |
| fix now | 作らない | 修正後に `2.1` で返す旨だけ書く（SHA が未確定のため） |

下書きに事実主張を書くときは `file:line` か出典を添え、確かめられないことは断定しない。`reply-tone-guide.md` `0.6` のチェックリストで点検し、提示の直前に writing-polish で推敲する。**推敲の手順（インストール判定・`--embed`・マーカー抽出・必須ルールが落ちた結果の破棄・失敗時の続行）は `${CLAUDE_PLUGIN_ROOT}/references/closing-flow-guide.md` `## 3` の writing-polish の項に従う**（手順をここに複製しない）。

### 5. レポート

次の形で出す。指摘は対応ごとにまとめ、fix now → 要確認 → follow-up → 返信のみ の順に並べる:

```
## レビューコメント仕分け: PR #<N>

- 対象: 指摘 N 件（コメント M 件から分解）/ 除外 K 件（解決済み a / 指摘なし b / bot 通知 c / 自分の返信 d）
- 内訳: fix now N / 要確認 N / follow-up N / 返信のみ N
- 精査したコード: HEAD <sha7>（PR head と {一致 | 不一致}）/ 反証: {未実施（effort）| N 件中 M 件}

### fix now
1. [<コメント ID>] @<投稿者>（{bot|人間}） <file:line>
   要旨: <1 行>
   妥当性: <値> — 根拠 <file:line>
   帰属: <値>
   対応方針: <何をどう直すか 1〜2 行>

### 要確認 / follow-up / 返信のみ
（同じ形。対応方針の代わりに「返信下書き」を置く）
   返信下書き:
   <reply-tone-guide に沿った本文>

### follow-up 起票文面
- タイトル: <1 行>
  本文: <背景 1 行 / 該当箇所 file:line / 元コメント URL>
```

該当 0 件の区分は見出しを残して「該当なし」と書く。最後に「投稿・修正・起票は行っていない」と 1 行添える。

## Additional Resources

- `${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh` — PR の会話（issue コメント・レビューサマリ・行単位コメントの返信チェーン）の取得
- `${CLAUDE_PLUGIN_ROOT}/references/reply-tone-guide.md` — 返信文面の正本（署名・敬意・パターン別テンプレ）
- `${CLAUDE_PLUGIN_ROOT}/references/closing-flow-guide.md` `## 3` — writing-polish による推敲手順
