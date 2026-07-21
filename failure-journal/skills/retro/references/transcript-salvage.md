# Transcript Salvage

retro の Phase 0.5（未起票失敗のサルベージ）の仕様。

## なぜ必要か

log-failure は手動起票のため、**人間が失敗に気づいて想起したものしか journal に入らない**。

### 測定条件（数値を読む前に）

以下は **1 ユーザー・1 マシン・日本語セッション主体**の単一環境での実測であり、普遍的な比率ではない。再現・追試の前提として次を明示する:

- 測定日 2026-07-21 / 対象は 2026-07-02 以降に更新された transcript
- 対象は 9 プロジェクト（claude-plugins ほか 8）。**うち claude-plugins 以外の 8 プロジェクトは log-failure を一度も使っておらず `journal.jsonl` は 0 行**
- sidechain（subagent）は除外

| 経路 | 実測値 | 再現方法 |
|---|---|---|
| ユーザーが訂正したターン | 603 ターン中 2〜3 件 | 下記「参考: ユーザー訂正側の測り方」 |
| Claude の自己訂正シグナル | 4783 assistant ターン中 111 件 / 35 セッション | 本文「走査手順」1〜2 をそのまま実行 |
| うち「再発しうる失敗」 | **111 件から 1/3 系統抽出した 37 件**を LLM 分類 → REAL 13 件（35%） | 走査手順 3 |
| 全 111 件を分類した場合の推定 | 35〜40 件 | 上の 35% を外挿 |
| 実際に journal に入っていた数 | 1 件 | `wc -l journal.jsonl` |

**「起票率 ≒2.5%」（1 ÷ 約 40）は、「導線が弱くて起票されない」と「そのプロジェクトで運用していない」を合算した数字**である点に注意。運用中の 1 プロジェクトに限れば分母は小さくなる。導線の弱さを単独で示す指標ではない。

失敗の大半は **Claude が自分で気づいて直しており、人間の目に触れないまま消える**。サルベージはこの取りこぼしを retro 実行時にまとめて回収する。

> 抽出された失敗の多くは単一クラスタ「未検証の前提で断定する」（フィールド名を確認せず参照 / 環境依存コマンドの存在を未確認で使用 / 挙動を検証せず既知バグと決めつけ / 出力を想定通りと思い込む）に収まった。起票さえされれば閾値 3 回は容易に超える。

### 参考: ユーザー訂正側の測り方

「人間経由の検知が働いていない」ことの根拠なので、手順を残す。`type=="user"` かつ sidechain でない行のうち、`<task-notification>` 等のシステム注入と eval harness のプロンプトを除いた 603 件に対し、自己訂正 grep と同じ語彙で絞った。ヒットのうち貼り付けプロンプトの誤検出を目視で除くと 2〜3 件（幅があるのは、1 件が「訂正」とも「仕様確認」とも読める境界だったため）。

## transcript の所在

`~/.claude/projects/<slug>/*.jsonl`。`<slug>` はプロジェクトの絶対パスの **`/` と `.` の両方**を `-` に置換したもの。

```bash
# `.` も変換すること（/Users/foo/.claude → -Users-foo--claude）
slug="$(echo "${CLAUDE_PROJECT_DIR:-$PWD}" | sed 's|[/.]|-|g')"
tdir="$HOME/.claude/projects/$slug"

# 不在なら黙ってスキップせず必ず知らせる（誤った slug は「失敗 0 件」に化けるため）
if [ ! -d "$tdir" ]; then
  echo "transcript dir が見つかりません: $tdir" >&2
  echo "（slug 導出を疑うこと。ls ~/.claude/projects/ で実際の名前を確認）" >&2
fi
```

> **`.` の変換を落とすと事故る。** `sed 's|/|-|g'` だけだと `.claude` を含むパスで実在しない dir を指し、`find` がエラーを握り潰して**「シグナル 0 件」＝正常終了に見える**。SKILL.md の「dir 不在ならスキップ」規定と組み合わさると無言で機能が死ぬ。

対象は **retro の集計窓と同じ期間**に更新された transcript のみ（既定 30 日）。窓の起点は次で算出する（走査手順で使う `$since_date`）:

```bash
days="${1:-30}"
since_date="$(date -u -v-"${days}"d +%Y-%m-%d 2>/dev/null \
  || date -u -d "${days} days ago" +%Y-%m-%d)"
```

`find -newermt` は `YYYY-MM-DD` 形式を受ける（journal 集計側の ISO8601 秒精度とは形式が異なる点に注意）。

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

並列分類の直後、**tag 語彙を単一コンテキストで統合する**。

実運用の例（2026-07-21、claude-plugins 単独・シグナル 94 件を 5 バッチに分けて**全件**分類。上の「なぜ必要か」の表は 9 プロジェクト横断・1/3 抽出なので別の試行）: REAL 36 件に対し約 20 個の tag が付き、`assumed-fact-without-verifying` / `assumed-root-cause-unverified` / `concluded-without-checking-timeline` のように**同一の失敗が別 tag に分散**した。

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
- **subagent 内で起きた失敗は原理的に一切拾えない**。走査は `isSidechain != true` で subagent を除外するが、実測で sidechain は assistant 出力の約 30%（同期間で 2142 件）を占める。agent team を多用する運用ほどこの盲点は大きい。除外を外すとノイズが支配的になるため、現状は「拾えない」と割り切っている
- **却下した候補は記録されず、次回以降も再浮上する**。重複排除は journal との突合のみなので、NOISE と判定した候補（precision 35% ＝ 候補の約 2/3）は毎回再レビュー対象になる。同じ窓で繰り返し実行すると同じ候補群を何度も捌くことになる
- **`/retro 60` のように窓を広げてもサルベージ側は伸びない**。transcript は `cleanupPeriodDays`（既定 30 日）で削除されるため、journal 集計が 60 日でもサルベージの被覆は約 30 日で頭打ちになり、両者の期間が非対称になる
- **正規表現は日本語前提**。英語セッション主体の環境では recall が落ちる
- transcript は `~/.claude/projects/` 配下のローカルファイルで、**マシンローカル**。複数マシン運用では各マシンで個別にサルベージが必要
- 走査対象が大きいとコストが嵩む。窓を絞る（`/retro 7`）ことで軽量化できる
