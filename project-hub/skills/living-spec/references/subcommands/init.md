<!-- 正本依存（SSoT pin）。本ファイルは format-spec.md の、続く pin の節を言い換えている。正本の節が変わったら、その節を言い換えている箇所を確認して pin を打ち直す（`--update-ssot-pins` は repo 全体を一括で打ち直す） -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#0 @74e61f65 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#7 @e4e38744 -->
<!-- SSOT: project-hub/skills/living-spec/references/format-spec.md#10 @fe9a7606 -->

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
     1. label: 「この内容で作成 (Recommended)」 / description: 「slug: `<推定 slug>` / タイトル: `<推定タイトル>` で `.claude/living-specs/<slug>.md` を作成する」。会話から見て未確定が 1 セッションで片付きそうなら、「1 セッションで決まりそうなら design-doc / feature-dev の grill で足ります」と 1 文だけ添える（止めない。選ばれればそのまま作る）
     2. label: 「slug を指定する」 / description: 「別の slug / タイトルをチャットで指定する」

> **既存時に上書き / 改訂 / supersede を問わない**のは design-doc Phase 1 との**意図的な非対称**。living spec は 1 プロジェクト = 1 ファイルで、supersede の概念を持たない（収束の履歴は Decision log が線形に持つ）。誤って別プロジェクトの living spec を潰す事故のほうが重いので、中止に倒す。

---

## Phase 2: scaffold 生成

1. **日付取得**（必ず Bash で取る。擬似日付を作らない）:
   ```bash
   date +%Y-%m-%d
   ```
2. **衝突確認**: Glob で `.claude/living-specs/<slug>.md` の不在を確認する（Phase 1 で確認済みでも、Write の直前にもう一度見る）
3. `${CLAUDE_PLUGIN_ROOT}/skills/living-spec/references/template.md` を Read し、プレースホルダを置換する:
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
