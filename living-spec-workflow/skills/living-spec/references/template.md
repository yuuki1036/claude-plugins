# living spec 本文テンプレ

`init` 実行時にこのテンプレを Read し、`{...}` プレースホルダを置換して Write する。

語彙・スキーマの正本は `format-spec.md`。このテンプレはその具現化なので、両者が食い違ったら **format-spec.md が正**。

## プレースホルダ一覧

| プレースホルダ | 置換値 | 取得方法 |
|---|---|---|
| `{TITLE}` | プロジェクト名（原文ママ、日本語可） | 引数またはユーザー確認 |
| `{TODAY}` | 本日（`YYYY-MM-DD`） | Bash `date +%Y-%m-%d` |

`phase: target` / `notion_page_id: null` / `sync: null` はテンプレの固定値（置換不要）。

`last-validated` と `last_updated` は**どちらも `{TODAY}`** で初期化する。作成行為を「人が内容を確認した瞬間」とみなすため（adr-keeper / design-doc が作成時に `{TODAY}` を入れる先例と同じ）。以降は format-spec.md の更新主体表に従い、`last_updated` は機械が、`last-validated` は maintain 実行時に更新する。

---

## テンプレ本体（ここから下を書き出す）

```markdown
---
phase: target
last-validated: {TODAY}
last_updated: {TODAY}
notion_page_id: null
sync: null
---

# {TITLE}

## 現在地サマリ

<!-- 3 行以内。いま何が確定していて、次に何を決めるのか。
     status で収束率と open OQ 残数が出るので、ここには数字でなく「判断の現在地」を書く -->

## 仕様

<!-- 確度ラベルは 確定 / 方向性(仮) / 未定 の 3 値（括弧は半角）。
     空セルは半角ハイフン 1 文字。since は /living-spec spec が機械付与するので手で書き換えない。
     行が 0 件の状態が正常な初期値（項目が決まってから追加する） -->

| 項目 | 内容 | 確度 | since |
|------|------|------|-------|

## Open Questions

<!-- 行は削除しない。close しても status を closed にして 関連 D# を書くだけ。
     再燃したら reopen せず新しい OQ を起票する。
     行が 0 件の状態が正常な初期値（最初の OQ は OQ1 から採番される） -->

| OQ# | 問い | status | 関連 D# | since |
|-----|------|--------|---------|-------|

## Decision log

<!-- append-only。既存エントリの編集・削除は禁止。
     エントリの形式は format-spec.md の「4. Decision log スキーマ」を参照する
     （見出し + 固定順の 6 bullet）。
     ここに記入例を置かないのは、例が採番と相互参照のパースに拾われてしまうため。
     最初の決定は D1 から採番される -->

## 進め方フェーズ

<!-- どういう順で収束させるか。フェーズ名と、そのフェーズを抜ける条件 -->

## タイムライン

<!-- 期日がある事項。無ければ空のままでよい -->

## 参照ソース

<!-- 判断の根拠にした外部資料。maintain 段 4 がここの外部 URL の死リンクを見る -->
```
