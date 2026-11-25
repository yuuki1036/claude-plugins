### 4.9 PR body の最終検証（gitignored パス検出）

`gh pr create` を実行する直前に、生成した body から gitignored パスを検出して fail-fast する。一度 PR が public になると内部パス参照は外部から見えてしまうため、文書ルール（厳守ルール参照）だけでなく機械チェックで橋渡しする。

```bash
# $pr_body に生成済みの PR 本文、$ATTACH に Step 4.5 / 4.6 の添付パスが入っている前提
# 0) --attach で URL に書き換わる参照 `](<ATTACH のパス>)` だけを検査対象から外す。
#    ATTACH に入れ忘れた参照はローカルパスのまま公開されるので、ここで外さず (1)(2) に掛ける
check_body=$pr_body
for p in "${ATTACH[@]}"; do check_body=${check_body//"]($p)"/"](attached)"}; done

# 1) 代表的な gitignore 対象パスの即時検出（regex）
violations=$(printf '%s\n' "$check_body" | grep -E '(\.claude/|\.next/|node_modules/|dist/|build/|coverage/|\.env)' || true)

# 2) リポジトリ固有の gitignore も尊重（動的判定）
while read -r path; do
  [ -n "$path" ] && git check-ignore -q "$path" 2>/dev/null && violations="${violations}"$'\n'"gitignored: $path"
done < <(printf '%s\n' "$check_body" | grep -oE '[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+')

[ -n "$violations" ] && { echo "PR body に gitignored パスが含まれています:"; printf '%s\n' "$violations"; }

# 3) パス文字列を伴わないローカル限定ドキュメント参照の検出（advisory・非 fail-fast）
#    「knowledge に詳細」「設計メモ参照」のように regex (1)(2) をすり抜ける自然言語の言及を拾う。
#    誤検知が出やすい（一般語としての knowledge / plan を含む）ため warning のみで PR は止めない。
soft=$(printf '%s\n' "$check_body" | grep -nE '(knowledge|設計メモ|実装メモ|作業メモ|ローカル(の)?(メモ|ノート|ドキュメント|ファイル)|plans?/|issues?/).{0,12}(参照|に詳細|を参照|参考|see|詳しくは)' || true)
[ -n "$soft" ] && { echo "[advisory] レビュアーが開けないローカル限定ドキュメントへの言及かもしれません。要点を本文にインライン要約できないか確認してください:"; printf '%s\n' "$soft"; }
```

regex (1)(2) で検出された場合は **PR を作成せず**、該当箇所を body から除去（または GitHub からクリック可能な URL に置換）してから再検証する。除去後に違反 0 件になったことを確認してから次へ進む（Step 4.93）。

(3) の advisory は PR 作成を止めない。ヒットした箇所が本当にローカル限定ドキュメントへの参照なら、参照させるのではなく要点を本文へ書き写してから進む。一般語としての `knowledge` / `plan`（外部リンク付き・社内 wiki 等のクリック可能リソースを含む）であれば無視してよい。

**次は Step 4.93**（SKILL.md に戻り、その見出しを見る）
