---
name: living-spec
description: >
  Issue 化前の「設計収束ドキュメント」(living spec) を作成・運用するスキル。OQ (Open Questions) 台帳と Decision log を append-only の表で持ち、確度ラベル（確定 / 方向性(仮) / 未定）で未確定を抱えたまま収束を追跡する。init / oq / decision / spec / status を提供する。**収束率や open OQ の残数を見る（status）のもこちら**（整合・鮮度の検証は living-spec-maintain）。
  トリガー: 「living spec」「リビングスペック」「living spec 作る」「OQ 台帳」「Open Questions 台帳」
  「OQ 追加」「Decision log」「決定を記録して OQ を閉じる」「確度ラベル」「収束率」「収束率を見せて」
  「open OQ を見せて」「残ってる OQ」「living spec の現在地」「living spec status」
  「Issue 化前に未確定を詰めたい」「設計を収束させたい」「/living-spec」
effort: medium
allowed-tools:
  - AskUserQuestion
  - Bash
  - Edit
  - Glob
  - Read
  - Write
---

# Living Spec

Issue 化する前段の「設計収束ドキュメント」(living spec) を `.claude/living-specs/<slug>.md` で運用するスキル。**未確定を抱えていることが正常状態**の文書を、採番・書式・相互参照を機械化しながら「仮 → 確定」へ収束させる。

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| Issue 化する前に、未確定を抱えたまま設計を収束させたい | **living-spec**（本スキル） |
| 代替案を比較して採用案を確定し、スナップショットとして残したい | `design-doc:design-doc` |
| 単一の設計判断（WHY）を点で記録したい | `adr-keeper:adr` |
| Issue 1 件の作業設計（9 セクション） | `issue-workflow:issue-design` |
| 設計から実装まで一気通貫で進める | `feature-dev` |

> living spec で確度が `確定` に寄った塊ができたら、それを Issue 化する。living spec 側からプラグインは呼ばない（疎結合）。ユーザーが `/issue-create`（issue-workflow）に手で渡す。

## 参照する規範（references）

- `${CLAUDE_SKILL_DIR}/references/format-spec.md` — 表スキーマ・確度ラベル・採番規約・frontmatter の**正本**
- `${CLAUDE_SKILL_DIR}/references/template.md` — scaffold テンプレ（プレースホルダ方式）

---

## Phase 0: 保存先確認 + サブコマンド判定

1. `.claude/living-specs/` の存在を Glob で確認。不在なら Bash で作成:
   ```bash
   mkdir -p .claude/living-specs
   ```
   living spec は **committed 前提**（プロジェクトローカルに永続化）。Decision log を履歴として残す設計なので gitignore しない
2. **第 1 引数は常にサブコマンドとして解釈する**。既知の語彙に一致しなければ slug とみなさず、usage を報告して終了する:

| サブコマンド | 引数 | 遷移先 |
|---|---|---|
| `init` | `[slug]` | Phase 1 |
| `oq` | `<text> [--spec <slug>]` | Phase 4 |
| `oq list` | `[--all] [--spec <slug>]` | Phase 4 |
| `decision` | `<text> [--spec <slug>]` | Phase 5 |
| `spec` | `<項目> <確度> [--spec <slug>]` | Phase 6 |
| `status` | `[--spec <slug>]` | Phase 7 |
| `maintain` | - | 案内のみ（整合・鮮度チェックは `/living-spec-maintain` の領分） |

3. 上記以外の入力の扱い:

| 入力 | 挙動 |
|---|---|
| 引数なし | usage（サブコマンド一覧）を報告して終了。**既定のサブコマンドを持たない** |
| 未知の第 1 引数（例: `/living-spec my-project`） | 「`my-project` は不明なサブコマンドです。利用可能: `init` / `oq` / `decision` / `spec` / `status`」と報告して終了 |

4. **`init` 以外は対象ファイルを特定する**（`format-spec.md` の 0 節が正本）: `--spec <slug>` があればそれ / 無くて 1 件なら自動 / 複数なら AskUserQuestion で選択 / 0 件なら init を案内して終了。**自動で推測しない**（意図しないファイルを書き換える事故のほうが重い）

> **slug は `init` の後ろにしか置けない。** サブコマンド名と slug 名を同じ名前空間に置くと、後からサブコマンドを追加するたびに、その語を slug に使っていた利用者の意味が変わる（例: `/living-spec oq` が「slug=oq で作成」から「OQ を追加」に反転する）。第 1 引数を常にサブコマンドとして解釈し未知語を弾くことで、Issue 追加時の破壊的変更をまとめて回避する。同じ理由で**既定のサブコマンドを持たない**（`/living-spec` 単独は usage）。typo（`stats` 等）が無確認でファイルを作る事故も同時に塞がる。

---

## Phase 1: init — 引数解析と slug / タイトルの確定

異常系はすべてこの Phase で落とす。

1. **slug の命名規則**: kebab-case `^[a-z0-9]+(-[a-z0-9]+)*$`。日本語は不可（ファイル名の可搬性）。日本語のプロジェクト名から作る場合は **romaji 化せず英語の要約 slug** にする（`kessai-kiban` ではなく `payment-platform`）。design-doc / adr-keeper の命名規約と同流儀
2. **init は slug とプロジェクト名の 2 つを必要とする**。frontmatter に `title` フィールドが無く、`# <プロジェクト名>` 見出しが唯一のタイトル源のため
3. 異常系の扱い:

| 状況 | 挙動 |
|---|---|
| slug 未指定 | 会話文脈から英語要約 kebab slug とプロジェクト名を推定し、**AskUserQuestion で 1 度だけ確認**する。文脈が皆無なら「slug を指定してください」と報告して終了 |
| slug が命名規則違反 | 勝手に書き換えない。正規化案を提示して上記と同じ 1 回の AskUserQuestion に畳む |
| `<slug>.md` が既存 | **中止**。「既存の living spec があります: `<path>`。編集は直接 Edit するか、別 slug で init してください」と報告して終了 |

   slug / タイトルを確認する AskUserQuestion の仕様:
   - question: 「living spec を作成します。この内容でよいですか？」
   - header: 「slug 確認」
   - options:
     1. label: 「この内容で作成 (Recommended)」 / description: 「slug: `<推定 slug>` / タイトル: `<推定タイトル>` で `.claude/living-specs/<slug>.md` を作成する」
     2. label: 「slug を指定する」 / description: 「別の slug / タイトルをチャットで指定する」

> **既存時に上書き / 改訂 / supersede を問わない**のは design-doc Phase 1 との**意図的な非対称**。living spec は 1 プロジェクト = 1 ファイルで、supersede の概念を持たない（収束の履歴は Decision log が線形に持つ）。誤って別プロジェクトの living spec を潰す事故のほうが重いので、中止に倒す。

---

## Phase 2: scaffold 生成

1. **日付取得**（必ず Bash で取る。擬似日付を作らない）:
   ```bash
   date +%Y-%m-%d
   ```
2. **衝突確認**: Glob で `.claude/living-specs/<slug>.md` の不在を確認する（Phase 1 で確認済みでも、Write の直前にもう一度見る）
3. `${CLAUDE_SKILL_DIR}/references/template.md` を Read し、プレースホルダを置換する:
   - `{TITLE}` → プロジェクト名（原文ママ）
   - `{TODAY}` → `date +%Y-%m-%d` の結果。`last-validated` と `last_updated` の**両方**に入れる
4. 置換した本文を `.claude/living-specs/<slug>.md` に Write する

> frontmatter の `phase: target` / `notion_page_id: null` / `sync: null` はテンプレの固定値。`append_only: true` は**付けない**（living spec は鮮度を測る対象そのもの。理由は `format-spec.md` の 10 節）。

---

## Phase 3: init の完了報告

```
✅ living spec を作成しました

📄 .claude/living-specs/<slug>.md
  phase: target / last-validated: <TODAY>

次のアクション:
- 「## 現在地サマリ」を埋める
- 仕様項目を立てる: /living-spec spec <項目> 未定
- 未確定の論点を起票する: /living-spec oq <問い>
```

---

## 共通手順: 書き込み前後の規律（Phase 4-6 が従う）

`oq` / `decision` / `spec` はいずれもファイルを更新する。**すべてこの規律に従う**。

### W1. 日付は Bash で取る

```bash
date +%Y-%m-%d
```

擬似日付を作らない。`since` / `日付` / `last_updated` はすべてこの値を使う。

### W2. 採番は「コメント除去 → 数値の最大 + 1」

`format-spec.md` の 6 節・9 節が正本。**必ず HTML コメント区間を除去してから**既存 ID を数える（コメント内の記入例を拾うと、実在しない ID を数えて採番がずれる）。

```bash
# OQ の max（コメント除去 → OQ 行の ID 列だけを取る）
perl -0777 -pe 's/<!--.*?-->//gs' "$F" | grep -oE '^\| *OQ([0-9]+) *\|' | grep -oE '[0-9]+' | sort -n | tail -1
# D の max
perl -0777 -pe 's/<!--.*?-->//gs' "$F" | grep -oE '^### D([0-9]+): ' | grep -oE '[0-9]+' | sort -n | tail -1
```

出力が空なら 0 件 → `OQ1` / `D1` から始める。**欠番は埋めない。ID は再利用しない**（6 節）。

### W3. 削除しない

Edit は **append と in-place 更新のみ**。行の削除を含む編集をしない（仕様表の行削除だけは項目の撤回として許容。2 節）。この規律があるので、Edit が部分適用で止まっても情報は消えない。

### W4. 書き込んだら `last_updated` を更新する

frontmatter の `last_updated` を W1 の日付に Edit する。**`last-validated` は触らない**（人が maintain を回したときに更新するフィールド。10 節）。

### W5. 0 行の表への最初の append

`init` 直後の表はヘッダ行 + 区切り行だけ。最初の行は**区切り行の直後**に足す。

---

## Phase 4: oq — OQ 台帳への追加 / 一覧

### 4a. `oq <text>` — 追加

1. 対象ファイルを Read する
2. W2 で `OQ<max+1>` を採番する
3. OQ 台帳の表に 1 行 append する（W5）:
   ```
   | OQ<n> | <text> | open | - | <TODAY> |
   ```
   - `関連 D#` は `-`（8 節: 空セルは半角ハイフン 1 文字）
   - `<text>` に `|` が含まれる場合は **`\|` にエスケープする**（8 節。9 節の正規表現はエスケープを許容する。生の `|` はセルを分割して段 1 の Critical になる）
4. W4 で `last_updated` を更新する
5. 報告:
   ```
   ✅ OQ<n> を追加しました（.claude/living-specs/<slug>.md）
     <text>

   open な OQ: <残数> 件
   ```

### 4b. `oq list` — 一覧

1. 対象ファイルを Read し、コメント除去後に OQ 行をパースする（9 節の正規表現）
2. **既定は `open` のみ**表示する。`--all` 指定時は `closed` も含める（closed 行は台帳に残っているので、フィルタは表示だけの話）
3. 0 件なら「open な OQ はありません」と報告する
4. 表で出す:
   ```
   ## Open Questions（open <n> 件 / 全 <m> 件）

   | OQ# | 問い | since | 経過 |
   |-----|------|-------|------|
   | OQ1 | ... | 2026-07-10 | 5 日 |
   ```
   `--all` のときは `status` と `関連 D#` の列を足す

> `oq list` は**読むだけ**。W1-W5 の書き込み規律は適用しない（`last_updated` も更新しない）。

---

## Phase 5: decision — Decision log への append と関連 OQ の close

**このサブコマンドが双方向参照を成立させる唯一の場所**。ここが片方向で止まると maintain 段 3 が Critical を出す。

1. 対象ファイルを Read する
2. W2 で `D<max+1>` を採番する
3. **関連 OQ を選ばせる**。コメント除去後に `status: open` の OQ を列挙し、AskUserQuestion で確認する（multiSelect）:
   - question: 「この決定が close する OQ を選んでください」
   - header: 「関連 OQ」
   - options: open な OQ ごとに「`OQ<n>`: <問いの先頭 40 字>」（**先頭に「なし（OQ を close しない）」を置く**。決定が既存の問いに対応しないことは普通にあるため）
   - open な OQ が 0 件なら**この確認を飛ばす**（選択肢が無いのに問わない）
4. **Decision log に append する**（4 節の形式。bullet のキーと順序は固定）:
   ```
   ### D<n>: <text を要約した見出し>
   - 日付: <TODAY>
   - 確信度: <高|中|低>
   - 根拠: <なぜこう決めたか>
   - 出典: <ファイルパス / URL / 会話。無ければ ->
   - 残: <この決定で残った未確定。無ければ ->
   - 関連 OQ: <OQ1, OQ3 形式。close しないなら ->
   ```
   - `確信度` / `根拠` / `残` はユーザーの入力から埋める。読み取れなければ**推測で埋めず**、`確信度: 中` を既定にして `根拠` に与えられた文言をそのまま置く
   - 既存エントリは**絶対に編集しない**（append-only。4 節）
5. **選ばれた OQ を close する**（同じファイルへの in-place 更新）。各 OQ 行を次のように Edit する（**セル区切りは単一スペース。カラム整列のパディングを入れない**。Edit は完全一致置換なので、見た目を整えると `old_string` が一致しなくなる）:
   ```
   | OQ<n> | <問い> | open | - | <since> |
   →
   | OQ<n> | <問い> | closed | D<新番> | <TODAY> |
   ```
   - `status` を `closed` に、`関連 D#` を新しい `D<n>` に、`since` を `<TODAY>` に更新する
   - **行は消さない**（W3）。`status` の書き換えだけで表現する
   - 既に `関連 D#` が入っている場合はカンマ + 半角空白で追記する（`D1, D3`。8 節）
6. **双方向参照を Read で検証する**（adr-keeper の supersede が新旧を Read で相互参照確認するのと同じ規律）: 書き込み後にファイルを Read し直し、**両方向を**確認する:
   - **Decision → OQ**: Decision の `関連 OQ` に挙げた各 `OQ<n>` が、OQ 台帳で `closed` かつ `関連 D#` に当該 `D<n>` を含むこと
   - **OQ → Decision**: 今 `closed` にした各 OQ の `関連 D#` に入れた `D<n>` が、Decision 側の `関連 OQ` にその `OQ<n>` を含むこと（step 5 で close したのに Decision の `関連 OQ` に載せ忘れた経路を捕まえる）
   - 片方向になっていたら**その場で直す**（maintain の事後検知に回さない。ここで直せる）。ファイルは既に Read 済みなので追加コストはない
7. W4 で `last_updated` を更新する
8. 報告:
   ```
   ✅ D<n> を追加しました（.claude/living-specs/<slug>.md）
     <見出し>

   close した OQ: OQ1, OQ3（双方向参照を検証済み）
   残る open な OQ: <残数> 件
   ```

> **OQ の reopen は許容しない**（`format-spec.md` 3 節）。close 後に議論が再燃したら、`/living-spec oq` で**新しい OQ を起票**し、その問いの中で旧 OQ / D# を参照する。決定の履歴を線形に保つため。

---

## Phase 6: spec — 仕様表の確度更新

`since` の発生源を機械に寄せるためのサブコマンド。手編集に委ねると「確度だけ変えて `since` を据え置く」（実際は動いているのに stale 警告）と「`since` だけ触る」（塩漬けなのに沈黙）が両方起こる。

1. **確度の検証**: `<確度>` が `確定` / `方向性(仮)` / `未定` の 3 値でなければ、報告して終了する（**勝手に正規化しない**）。括弧は**半角**（5 節）
   ```
   `<確度>` は不正な確度ラベルです。確定 / 方向性(仮) / 未定 のいずれかを指定してください（括弧は半角）。
   ```
2. 対象ファイルを Read し、コメント除去後に仕様表を 9 節の正規表現でパースする
3. `<項目>` に**完全一致**する行を探す:

| 一致数 | 挙動 |
|---|---|
| 1 件 | その行の `確度` と `since` を in-place 更新する |
| 0 件 | **新規行として append する**（W5）: `\| <項目> \| - \| <確度> \| <TODAY> \|`。`内容` は `-`（8 節。決まってから `spec` で更新するのではなく直接 Edit で埋める） |
| 2 件以上 | **更新せず報告して終了**。「`<項目>` が N 行あります。`format-spec.md` 2 節により項目はファイル内で一意である必要があります。重複を解消してください」（2 節の一意性違反。どちらを更新したかが非決定になるため倒す） |

4. 更新時は `確度` と `since` の**両方**を書く。`since` は必ず `<TODAY>`（W1）
   - **確度が変わらない場合も `since` を更新する**（「今日この確度で確認した」という意味になり、段 6 の塩漬け検出が正しく動く）
5. W4 で `last_updated` を更新する
6. 報告:
   ```
   ✅ 「<項目>」の確度を <旧確度> → <確度> に更新しました（.claude/living-specs/<slug>.md）
     since: <TODAY>

   収束率: <確定数>/<全項目数>
   ```
   新規行なら「新しい仕様項目「<項目>」を <確度> で追加しました」

> **確度の逆行（`確定` → `方向性(仮)`）は許容し、警告しない**（3 節）。決定が覆るのは正常な事象。ただし対応する Decision が既にある場合は、報告の末尾に「この項目に関する決定を覆すなら `/living-spec decision` で経緯を残してください」と 1 行添える。

---

## Phase 7: status — 進捗ビュー

**読むだけ**（W1-W5 の書き込み規律は適用しない）。

1. 対象ファイルを Read し、コメント除去後に仕様表と OQ 台帳をパースする
2. 集計する:
   - **収束率 = `確定` の数 ÷ 全項目数**（`format-spec.md` の重み付けはしない。単純な比）。項目 0 件なら「項目なし」と表示し、0 除算しない
   - 確度ラベル別の内訳（`確定` / `方向性(仮)` / `未定`）
   - **open OQ 残数**
3. 出す:
   ```
   ## <プロジェクト名> の現在地

   収束率: <確定>/<全> （<確定> 確定 / <仮> 方向性(仮) / <未定> 未定）
   open な OQ: <n> 件
   last_updated: <日付> / last-validated: <日付>

   ### 次に決めるもの
   - OQ1: <問い>（<経過> 日）
   - 未定の項目: <項目名>, <項目名>

   ### 現在地サマリ
   <「## 現在地サマリ」セクションの本文>
   ```
4. **セッション再開の導線**として、open な OQ と `未定` / `方向性(仮)` の項目を提示する。ここが「新規セッションで living spec の未確定から再開する」ゴールの実装

> 確定した塊ができていたら、報告の末尾に「確定した項目が <n> 件あります。Issue 化するなら `/issue-create` に渡してください」と添える。**living spec 側からプラグインは呼ばない**（疎結合）。

---

## maintain の案内

`maintain` が指定されたら、次を報告して終了する（このコマンドでは提供しない）:

```
整合・鮮度チェックは別コマンドです: /living-spec-maintain

段 1-7 の機械判定（表スキーマ / 採番 / 双方向参照 / 死リンク / 確度の塩漬け）と、
段 8 の LLM 判断（現在地サマリのズレ）を実行します。
```

> **このスキルで検証ロジックを即興実装しない**。maintain の段 1-8 は `format-spec.md` の全規約を機械判定する設計で、場当たりの検証は「通ったから正しい」という誤った安心を生む。`living-spec-maintain` スキルに委ねる。

---

## 処理フロー

```
1. Phase 0: .claude/living-specs/ 確認（無ければ mkdir）+ サブコマンド判定 + 対象ファイル特定
2. Phase 1: init → slug 命名規則の検証・タイトル確定・既存なら中止
3. Phase 2: date 取得 → 衝突確認 → template 置換 → Write
4. Phase 3: init の完了報告
5. Phase 4: oq → 採番（コメント除去 → max+1）→ append / oq list は読むだけ
6. Phase 5: decision → 採番 → 関連 OQ を選ばせる → append → OQ を close → 双方向参照を Read で検証
7. Phase 6: spec → 確度の 3 値検証 → 項目で引き当て（重複は倒す）→ 確度と since を更新
8. Phase 7: status → 収束率と open OQ 残数を集計（読むだけ）
```

---

## 注意事項

- **日付は必ず Bash で取得**: `date +%Y-%m-%d` を実行する。擬似日付を作らない（adr-keeper / design-doc と同じ規律）
- **format-spec.md が正本**: 表スキーマ・語彙・採番規約が SKILL.md 本文と食い違ったら format-spec.md が正。書式が揺れると maintain の段 1-3 の機械パースが壊れる
- **採番の前に必ず HTML コメントを除去する**（W2）: 除去を省くと、テンプレや説明コメント内の記入例を実在する ID として数え、採番がずれる（`D1` を数えて最初の決定が `D2` から始まる等）。`format-spec.md` 9 節が前処理として要求している契約
- **削除しない**（W3）: OQ 台帳と Decision log から行・エントリを消さない。close は `status` の書き換えで表現する。この規律があるので Edit が部分適用で止まっても情報は消えない
- **双方向参照は decision がその場で閉じる**（Phase 5.6）: 書き込み後に Read で検証し、片方向なら即座に直す。maintain の事後検知に回さない
- **既存ファイルには触らない**: init は scaffold 専用。既存の living spec を上書き・改訂しない
- **doc-freshness との住み分け**: ファイル単位の鮮度（`last-validated` / `phase` の stale 判定）と frontmatter スキーマ検証は doc-freshness が担う。living-spec 側は表スキーマ・採番・相互参照・確度ラベルの `since` stale（doc-freshness では測れないセクション粒度）を担当する
- **doc-freshness 未導入時も動く**: 失われるのはファイル単位の stale 検出だけで、living spec の中核価値（OQ・Decision・収束の可視化）は単体で成立する。fail-fast させない
- **鮮度 lint の委譲には doc-freshness 0.4.0 以降が必要**: `.claude/living-specs/` の走査対象への追加は 0.4.0 で入った。それ未満では living spec が走査されず stale が検出されない（README 参照）
