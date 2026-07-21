# Transcript Salvage

retro の Phase 0.5（未起票失敗のサルベージ）の仕様。

## なぜ必要か

log-failure は手動起票のため、**人間が失敗に気づいて想起したものしか journal に入らない**。実測（2026-07-21、claude-plugins および関連 8 プロジェクト / 2026-07-02 以降の transcript）:

| 経路 | 実測値 |
|---|---|
| ユーザーが訂正したターン | 603 ターン中 2〜3 件 |
| Claude の自己訂正シグナル | 4783 assistant ターン中 111 件 / 35 セッション |
| うち「再発しうる失敗」（1/3 抽出 37 件を LLM 分類） | 13 件（35%）→ 全体で 35〜40 件規模 |
| **実際に journal に入った数** | **1 件（≒2.5%）** |

失敗の大半は **Claude が自分で気づいて直しており、人間の目に触れないまま消える**。サルベージはこの取りこぼしを retro 実行時にまとめて回収する。

> 抽出された失敗の多くは単一クラスタ「未検証の前提で断定する」（フィールド名を確認せず参照 / 環境依存コマンドの存在を未確認で使用 / 挙動を検証せず既知バグと決めつけ / 出力を想定通りと思い込む）に収まった。起票さえされれば閾値 3 回は容易に超える。

## transcript の所在

`~/.claude/projects/<slug>/*.jsonl`。`<slug>` はプロジェクトの絶対パスの `/` を `-` に置換したもの。

```bash
slug="$(echo "${CLAUDE_PROJECT_DIR:-$PWD}" | sed 's|/|-|g')"
tdir="$HOME/.claude/projects/$slug"
```

対象は **retro の集計窓と同じ期間**に更新された transcript のみ（既定 30 日）。

## 走査手順

### 1. assistant 発話の抽出

`isSidechain` が true の行は **subagent の発話**なので除外する（除外しないと agent へのプロンプトが大量に誤検出される）。

```bash
find "$tdir" -name "*.jsonl" -newermt "$since_date" 2>/dev/null \
| while read -r f; do
    jq -c --arg f "$f" '
      select(.type=="assistant")
      | select(.isSidechain != true)
      | {f:$f, ts:.timestamp,
         t:(.message.content // [] | map(select(.type=="text").text) | join(" "))}
      | select(.t != "")
    ' "$f" 2>/dev/null
  done > /tmp/retro-asst.jsonl
```

### 2. 自己訂正シグナルの grep

```bash
jq -c 'select(.t | test("訂正|間違えて|間違って|誤り|誤って|私のミス|失敗した|勘違い|想定と違|やり直"))' \
  /tmp/retro-asst.jsonl > /tmp/retro-signals.jsonl
```

### 3. LLM による REAL / NOISE 分類

grep の **precision は約 35%**。以下は NOISE として落とす:

- 文書・コードの内容として「訂正」等の語を書いているだけ
- 他エージェント / 過去レポートの誤りを指摘している（Claude 自身の失敗ではない）
- 機能仕様の説明、ユーザーの誤りの指摘

REAL の条件は log-failure と同じ **「同じ状況で再発しうるか」の単一基準**。一過性・偶発のものは落とす。

件数が多い場合（目安 30 件超）は Agent tool で分割して並列分類してよい。その際は `run_in_background: false` を明示する（省略すると完了を待たずに次フェーズへ進む）。

### 4. 既存 journal との重複排除

サルベージ候補が既に起票済みでないかを、同一窓内の journal レコードと突き合わせる。判定は tag の意味的一致で行う（timestamp は起票時刻であり失敗発生時刻とは限らないため、時刻一致では判定しない）。

## append は必ず承認制

**precision 35% ゆえ、自動 append は禁止。** 分類後の REAL 候補を一覧提示し、AskUserQuestion または明示的な確認を経てから append する。誤起票は journal を汚し、閾値集計の信頼性を直接損なう。

append の手順・スキーマは log-failure の `references/journal-schema.md` に従う（`timestamp` / `tag` / `phenomenon` / `context`）。**timestamp はサルベージ実行時刻ではなく、失敗が発生した transcript 上の時刻**を使う（窓集計の正確性のため）。

## 制約と既知の穴

- **assistant が自己訂正を言語化しなかった失敗は拾えない**。無言で直した場合はシグナルが残らない
- **正規表現は日本語前提**。英語セッション主体の環境では recall が落ちる
- transcript は `~/.claude/projects/` 配下のローカルファイルで、**マシンローカル**。複数マシン運用では各マシンで個別にサルベージが必要
- 走査対象が大きいとコストが嵩む。窓を絞る（`/retro 7`）ことで軽量化できる
