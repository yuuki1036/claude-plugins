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

**並列分類には既知の失敗モードが 2 つある**（2026-07-21 の実運用で両方発生）。以下のガードを必ず入れる:

- **識別子は ISO 時刻を verbatim で返させる**。行番号を返させると、担当分（例: 58〜76 行目）を勝手に 1〜19 に振り直す agent が出て、timestamp への逆引きが壊れる。時刻なら自己識別的で再採番の影響を受けない
- **分類直後に tag 正規化フェーズを挟む**（次節）。並列 agent は互いの語彙を見ないため、同じ失敗に別々の tag を付ける

### 3.5. tag 正規化（並列分類時は必須）

並列分類の直後、**tag 語彙を単一コンテキストで統合する**。実運用では REAL 36 件に約 20 個の tag が付き、`assumed-fact-without-verifying` / `assumed-root-cause-unverified` / `concluded-without-checking-timeline` のように**同一の失敗が別 tag に分散**した。

分散したままでは同一 tag が閾値 3 回に届かず、**サルベージしても還流提案が出ない**（拡張の目的が消える）。

正規化の手順:

1. 既存 journal の tag 一覧を統制語彙のシードとして与える（表記ゆれの発生源を減らす）
2. 分類結果の全 tag を一覧化し、意味的に同一のものを正準 tag へ寄せる
3. 寄せた結果を提示する際は「元 tag → 正準 tag」の対応も見せる（過剰な統合をユーザーが検知できるようにする）

> 統合しすぎると別種の失敗が 1 つの tag に潰れ、還流先の判定が粗くなる。「同じ還流先（hook / skill / 規約）に落ちるか」を統合の基準にするとよい。

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
