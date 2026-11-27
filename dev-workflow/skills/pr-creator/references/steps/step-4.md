<!-- 正本依存（SSoT pin）。この Step が言い換えている ui-verify の節。正本が変わったら本ファイルへの伝播を確認して pin を書き換える -->
<!-- SSOT: dev-workflow/skills/ui-verify/references/modes/verify.md#(e) @c1dc7450 -->

### 4. PR情報を生成

- タイトル: Linear Issue があればそのタイトル本文のみを使う（Issue ID prefix の `TEAM-123:` 等は含めない）。なければ変更の要約（50 文字以内）
- Description: 人間レビュアーが読んで `What / Why / Outcome` の三要素が即座に分かること。末尾に `<details><summary>詳細情報</summary>...</details>` を置いて、AI やレビュー bot が参照する補足情報を畳む

三要素の定義:
- **What**: 変更の対象 / スコープ（どのコード・機能・領域を触ったか）
- **Why**: 動機 / 背景（何が問題・状況だったか、なぜ変える必要があったか）
- **Outcome**: 結果 / 効果（何が変わって、ユーザーやコードベースから見てどう違うか）

実装の手段（How）は「変更点」セクションに書く。概要で How まで踏み込むと冗長化するので、概要では Outcome（結果・効果）だけに留める。

**概要は bullet 3 本（What / Why / Outcome を 1 本ずつ）**: 各観点を独立した bullet で明示する。brevity を優先して Why（動機・背景）や Outcome（結果・効果）を省くのは不可（3 本すべて埋める）。各 bullet は 1 文で簡潔に。3 要素が 1 本ずつに収まらないほど大きいなら、概要が長いのではなく PR が大きすぎるサインとして分割を検討する。**リポジトリの PR テンプレートが散文形式の概要を明示的に要求している場合はテンプレートに従う**（bullet を強制しない）。

リポジトリに PR テンプレートがあれば本文はそれに従い、ない場合は概要 / 変更点 / 図で見る要点（Step 4.6 で作ったときだけ）/ レビューしてほしいところ / 動作確認 / Screenshots / 備考 の構成を使う。

本文の書き方は `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/description-guide.md` に従う。

**動作確認セクションは `.claude/verification/<branch>.md` から生成する**（ui-verify の verify モードが残す実機 E2E の結果）。あれば差分から想像で書かず、記録を材料にする:

```bash
VERI=".claude/verification/$(git rev-parse --abbrev-ref HEAD).md"
```

1. `$VERI` が無ければ従来どおり diff から動作確認を書き、レポートに「動作確認は記録なし」と添える
2. あれば frontmatter の `head` で鮮度を 3 値判定する（rebase / amend / force-push で記録 sha が orphan になる事故を避ける）:
   - `head` == 現 HEAD → 新鮮。ケース表をそのまま転記
   - `git merge-base --is-ancestor <head> HEAD` が真 → 同一線上で後方。「(<sha> 時点)」を添えて転記
   - 非祖先 / sha が解決できない（`git cat-file -e <head>^{commit}` が偽）→ 記録を信用せず「動作確認の記録が現ブランチと乖離（再実行推奨）」と書く。黙ってフレッシュ扱いしない（鮮度 ≠ 内容一致）
3. ケース表を「動作確認」セクションに転記する（**`## 動作確認` の大セクションとして**。チェックリスト 1 行へ潰さない。列: 種別 / 内容 / 結果）。手順の詳細は `<details>` に畳む。`fail` / `blocked` が残っていれば本文に残し隠さない
4. 記録の `## カバレッジ` の `未カバー` 行が `なし` 以外なら、動作確認セクションに 1 行で転記する（例: `未カバー: 準正常・異常（理由）`）。隠さない
5. 証跡（verify-* のスクショ / 動画）は Step 4.5 の `ATTACH` に渡し、機密チェックを通す。`browser` が `chrome-devtools(autoConnect)` / 実 Chrome の証跡は実ユーザー情報を含みやすいので既定で添付対象外、添付は dev アカウント画面に限りユーザー承認で opt-in

**次は Step 4.5**（SKILL.md に戻り、その見出しを見る）
