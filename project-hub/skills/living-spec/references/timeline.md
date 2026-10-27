# timeline — タイムラインへの 1 項目の append（living-spec Phase 8）

起きたこと（進捗）と期日を、`format-spec.md` 1.1 節の形で「## タイムライン」の末尾に 1 行足す（GitHub issue #333）。**決定は書かない**（`decision` の領分。「〜にする」「〜を採用」のような決定の文が渡されたら、書かずに `/living-spec decision` を案内して終了する）。仕様表の凍結とは関係なく書ける。対象ファイルは SKILL.md の Phase 0 で決めたもの、W1・W4 は SKILL.md の「共通手順」。

1. 引数を検証する（勝手に正規化しない）。当たったら書かずに報告して終了する:
   - `<text>` が空、または改行を含む → 「タイムラインの項目は 1 行で渡してください」
   - `--source` の値が改行を含む → 同上
   - `--date` が `YYYY-MM-DD` の形でない・実在しない日付 → 「`<値>` は日付として読めません（YYYY-MM-DD）」。確かめは Bash で行う:
     ```bash
     python3 -c 'import re,sys,datetime; s=sys.argv[1]; assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s); datetime.date.fromisoformat(s)' "$DATE"
     ```
2. W1 で `<TODAY>` を取る。項目の日付は `--date` があればその値（起きた日。未来の期日も可）、無ければ `<TODAY>`
3. 対象ファイルを Read し、`## タイムライン` の見出しを探す。無ければ「`## タイムライン` の節がありません（format-spec.md 1 節）。/living-spec-maintain で構成を確かめてください」と報告して終了する（節を作らない）
4. 節の末尾（次の `## ` 見出しの直前。HTML コメントと既存の行の後ろ）に 1 行足す:
   ```
   - <日付> <text>（出典: <source>）
   ```
   `--source` が無ければ `（出典: …）` ごと書かない。足した行と次の `## ` 見出しの間には空行を 1 行置く。既存の行は動かさない・並べ替えない（1.1 節）
5. W4 で `last_updated` を更新する
6. 報告:
   ```
   ✅ タイムラインに足しました（.claude/living-specs/<slug>.md）
     - <日付> <text>（出典: <source>）
   ```
