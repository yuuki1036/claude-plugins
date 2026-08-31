# Journal Schema

failure-journal の永続フォーマット定義。

## 保存先

- パス: `.claude/failure-journal/journal.jsonl`
- 形式: JSON Lines（1 行 = 1 イベント）
- 書き込み: **append-only**（既存行の編集・削除を禁止）
- 永続性: **gitignore 推奨**（fingerprint を AI の出力に汚染させないため、commit せずローカルに留める。README 参照）

## candidates.jsonl（自己申告の候補置き場）

journal の手前に置くステージングファイル。SessionStart 注入ルール（`rules/self-report-rule.md`）により、Claude が自己訂正した瞬間に 1 行 append する。`/retro` Phase 0.5 が承認レビューで journal に昇格する。

- パス: `.claude/failure-journal/candidates.jsonl`
- スキーマ: `{"ts":"<ISO8601 UTC>","summary":"<何をどう間違えたか 1 行>","verdict":null}`
  - `verdict` は起票時 `null`。`/retro` のレビュー後に `"accepted"` / `"rejected"` が書き戻される（再浮上防止）
  - `summary` は自由文。固有名詞可（tag 化・抽象化は retro のレビューで行う）
- journal との違い: append-only ではない（verdict の書き戻しのみ許可。行削除・summary 書き換えは禁止）
- Read 制約は journal と同じ（**retro 実行中のみ Read**。append はいつでもよい）

## remediations.jsonl（還流の実施記録）

閾値超え tag に対して**実際に打った手**の記録。`/retro` Phase 3 の閾値判定は、この記録より後の発生だけを分子に取る（GitHub issue #193）。

- パス: `.claude/failure-journal/remediations.jsonl`
- 書き込み: **append-only**（journal と同じ。訂正は新しい行で行う）
- 永続性: journal と同じくローカル（gitignore 推奨）

```json
{"timestamp":"2026-08-28T00:00:00Z","tag":"claimed-fact-without-source","target":"convention","ref":"ac8214d"}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `timestamp` | string (ISO8601 UTC) | yes | **還流を実施した日時**（起票日ではなくコミット日時） |
| `tag` | string | yes | 対象 tag。journal の tag 規約に準拠 |
| `target` | string | yes | 還流先の層: `convention` / `hook` / `skill` |
| `ref` | string | yes | 還流先の特定子（commit hash / ファイルパス） |
| `note` | string | no | 補足（何を入れたか 1 行） |

> **実施していない還流を書かない。** この記録より前の発生は次の retro の分子から外れるため、
> 提案しただけ・着手しただけの段階で書くと**再発を見逃す**。書くのは還流が landed した後。

> **umbrella tag の分割宣言とは別物。** 分割は tag の粒度を変える操作（下記）、還流は
> 対策を打つ操作。分割と同時に還流したなら、両方を記録する。

### append 手順

```bash
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"   # または還流コミットの日時
jq -nc --arg ts "$ts" --arg tag "$tag" --arg target "$target" --arg ref "$ref" \
  '{timestamp:$ts,tag:$tag,target:$target,ref:$ref}' \
  >> .claude/failure-journal/remediations.jsonl
```

## splits.jsonl（umbrella tag の分割宣言）

**分割は doc に表を書くだけでは起票側に降りない**（GitHub issue #195）。log-failure Phase 2 が寄せ先候補として見るのは「journal に実在する tag」だけで、宣言直後のサブ tag は 0 件だから構造的に候補にならない。宣言は**機械が引ける場所**に置く。

- パス: `.claude/failure-journal/splits.jsonl`
- 書き込み: **append-only**（訂正は新しい行を足す。同一 umbrella は最新行の内容が勝つ）
- 永続性: journal と同じくローカル（gitignore 推奨）
- **remediations.jsonl に相乗りさせない。** 相乗りすると分割が有効境界を動かし、対策を何も打っていないのに分子が下がって「還流後に再発なし」として報告される

```json
{"declared_at":"2026-08-31T00:00:00Z","umbrella":"claimed-fact-without-source","sub_tags":[{"tag":"stale-record-read-as-current","mechanism":"記録（title / コミットメッセージ / 過去コメント）から現在値を断定","target":"convention"}],"redirects":[{"when":"他者（subagent / スクリプト / 集計）の出力を検算せず採用した","tag":"misread-or-trusted-bad-output"}],"ref":"#195"}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `declared_at` | string (ISO8601 UTC) | yes | 宣言した日時。**この時刻以降の umbrella 起票が「分割が降りていない」の観測対象**。同一 umbrella が複数行あるときは最も古いものが起点 |
| `umbrella` | string | yes | 分割元 tag |
| `sub_tags` | array | yes | 1 件以上。`tag`（tag 規約準拠）/ `mechanism`（1 行・必須）/ `target`（任意） |
| `redirects` | array | no | umbrella に見えるが**別ファミリへ送る**型。`when`（見分ける手がかり 1 行）/ `tag`（送り先） |
| `ref` / `note` | string | no | 根拠（commit / issue 番号）・補足 |

> **`mechanism` は必須。** 起票側が読むのはこの 1 行だけで、SKILL.md や本ファイルの散文は読まれない（issue #195 が観測したのはまさにそれ）。

### 照会

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/tag-split-lookup.sh"
```

exit 0 が回答（宣言 0 件を含む）、exit 2 は判定不能（jq 不在・壊れた行・引数不正）。**exit 2 を「分割なし」と読まない。**

> **壊れた行で止める（fail-loud）のは意図的**。宣言を 1 行落とすと「分割されていない」に化けて起票側が黙って umbrella へ寄せ、issue #195 の状態へ戻る。集計側（`retro-aggregate.sh`）が壊れた行を飛ばすのと非対称なのは、あちらは落ちてもレポートの 1 フィールドが欠けるだけだから。

### append 手順

```bash
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -nc --arg ts "$ts" --arg u "$umbrella" --argjson subs "$subs_json" --arg ref "$ref" \
  '{declared_at:$ts,umbrella:$u,sub_tags:$subs,ref:$ref}' \
  >> .claude/failure-journal/splits.jsonl
```

- サブ tag を足すときは**全件を含む新しい行を append** する（既存行は書き換えない）。最新行が現在の集合
- `declared_at` は**宣言した日**にする。遡って書くと、宣言前の umbrella 起票（append-only の規約どおり正しい起票）まで「降りていない」と数えられ、初回から偽陽性が出る

## スキーマ

各行は次の構造の単一 JSON オブジェクト:

```json
{"timestamp":"2026-05-29T12:00:00Z","tag":"spec-skipped-without-rationale","phenomenon":"spec.md を生成せず実装へ進んだ","context":{}}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `timestamp` | string (ISO8601 UTC) | yes | `date -u +%Y-%m-%dT%H:%M:%SZ` で生成 |
| `tag` | string | yes | 集計の fingerprint。下記 tag 規約に準拠 |
| `phenomenon` | string | yes | 失敗現象の簡潔な説明（1〜2 文。長文ログ禁止）|
| `context` | object | yes | 将来拡張用。Phase 1 では `{}` 固定 |

## tag 規約

| 規約 | 内容 | 違反例 → 修正例 |
|---|---|---|
| kebab-case | 小文字 + ハイフン区切り | `SpecSkipped` → `spec-skipped` |
| 30 文字以内 | 長い場合は抽象化して短縮 | `spec-md-was-skipped-without-any-rationale` → `spec-skipped-without-rationale` |
| 固有名詞禁止 | ファイル名・関数名・Issue ID・人名を含めない | `foo-ts-type-error` → `type-error-untracked` |
| 現象主体 | 「何をしくじったか」を抽象化 | `forgot` → `version-bump-omitted` |

> tag は「同じ失敗を別の機会に踏んだとき、同一の tag に collapse できる」ことが目的。具体的すぎると集計で別 tag に散り、抽象的すぎると無関係な失敗が混ざる。現象の「型」を表す粒度を狙う。

## umbrella tag の分割（retro で閾値を超え続けるとき）

**同一 tag が還流のたびに別の機構を出してくるなら、それは 1 つの失敗型ではなく複数を束ねている。**
分割せずに還流を重ねても、対策は毎回「今回の 1 件」にしか当たらず、閾値だけが鳴り続ける。

判定の目安（retro の Phase 4 で使う）:

- 閾値を超えた tag の内訳を書き出したとき、**還流先が 2 つ以上に割れる**（hook / 規約 / skill）
- 既に還流した対策が、**次の発生を止めていない**（発生が対策より後で、かつ別の機構）

分割するときは**新しい発生から新 tag を使い、既存 journal は書き換えない**（append-only）。
過去ぶんは umbrella のまま残るので、集計は「umbrella + 新 tag の合計」で読む。

### 実例: `claimed-fact-without-source`（全期間 17 件・窓内 9 件で最多）

> **判定の正本はこの表ではなく `.claude/failure-journal/splits.jsonl`**（上の節）。下表は分割がどう見えるかの説明で、起票側はこれを読まない。件数は起票時点のスナップショット。

内訳が 4 機構に割れ、還流先もばらけた:

| サブ tag | 機構 | 還流先 |
|---|---|---|
| `stale-record-read-as-current` | 記録（title / コミットメッセージ / 過去コメント）から現在値を断定 | 規約（CLAUDE.md） |
| `cited-passage-not-verified` | 引用先に該当記述が実在するか確認しない | hook（guardrail-protect） |
| `mechanism-asserted-unread` | 正本のコードを読まずに機構・原因を断定 | 規約 |
| `unassigned-id-written-as-fixed` | 未確定の識別子（issue 番号・版・ハッシュ）を確定として書く | 規約 |

**`unassigned-id-written-as-fixed` は存在検査では止まらない**（実測: 起票前に書いた issue 番号が
実在する別の issue を指しており、存在検査を通ってしまう）。`vNEXT` プレースホルダと同じく
**書く側の手順**で消す型。

**隣接するがサブ tag にしない型**: 「他者（subagent / スクリプト / 集計）の出力を検算せず典拠として採用」は 5 つ目のサブ tag にせず、既存 tag `misread-or-trusted-bad-output` に寄せる。還流先が CLAUDE.md の「subagent の事実主張は採用前に一次ソースへ当てる」で規約層に既存で、分割基準（還流先が 2 つ以上に割れる）を満たさないため。切り分けは**典拠が誰の出力か**: 自分が読んだ記録から断定 → `stale-record-read-as-current` / 他者の出力を検算せず採用 → `misread-or-trusted-bad-output`。新設すると既存の実績から引き剥がされて閾値に届かなくなる。**この判定は `redirects` に入れて起票側へ降ろす**（散文に書いても降りないのが本節の教訓）。

## append 手順（正準）

```bash
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -nc \
  --arg ts "$ts" \
  --arg tag "$tag" \
  --arg ph "$phenomenon" \
  '{timestamp:$ts,tag:$tag,phenomenon:$ph,context:{}}' \
  >> .claude/failure-journal/journal.jsonl
```

- `jq -nc` で null input から compact な 1 行 JSON を生成（valid JSON を保証）
- `>>` で末尾追記のみ。`>` （上書き）は禁止
- 文字列は `--arg` 経由で渡す（クオート・改行のエスケープを jq に任せる）

## event publish

append 成功後、`failure:logged` event を publish する（payload は tag のみ）:

```bash
if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null; then
  SAFE_HOOK_NAME="failure-journal"
  event_bus_publish "failure:logged" "$(jq -nc --arg t "$tag" '{tag:$t}')"
fi
```

> `SAFE_HOOK_NAME` を設定せずに `event_bus_publish` すると `"plugin":"unknown"` が書かれる。source 直後に必ず `SAFE_HOOK_NAME="failure-journal"` を設定する（`safe_hook_init` は stdin を cat するので skill 内 Bash では呼ばない）。
