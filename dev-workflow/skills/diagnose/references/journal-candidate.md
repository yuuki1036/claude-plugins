<!-- 正本依存（SSoT pin）。候補の形式と ts の意味は failure-journal の journal-schema.md が正本。正本が変わったらこのファイルの手順を確認して pin を打ち直す -->
<!-- SSOT: failure-journal/skills/log-failure/references/journal-schema.md#candidates.jsonl（候補置き場） @d51af035 -->

# failure-journal への候補の書き方（diagnose Phase 6）

failure-journal の retro は、候補の `ts` をそのまま失敗の発生時刻として 30 日窓と「最後の還流より後の発生」を数える。診断した時刻を書くと、還流前に入った失敗が還流後の再発に数えられ、窓の外の古い失敗が窓の中に戻る。だから `ts` は**原因を入れた commit の日時**にする。自己申告ルールの jq（`ts` が今の時刻）をそのまま使わない。

## 書くもの・書かないもの

書くのは、**このセッションより前の commit で入った原因**で、その commit に `Co-Authored-By: Claude` の trailer があるもの。次は書かない:

- 原因の commit を特定できない（下の「特定する」を満たさない）
- trailer の無い commit — 人の作業と区別できない。failure-journal が集めるのは Claude 自身の失敗
- このセッションで自分が入れた原因 — 自己申告ルールの対象。訂正したターンで書いていなければ、今そのルールの形式で書く
- Phase 3〜4 で仮説が反証されたこと — 手順どおりで失敗ではない（断定として伝えた後に崩れたなら自己申告の対象）

## 原因の commit を特定する

- Phase 1 で `git bisect` を回したならその結果。回していなければ修正前の行を blame する: 修正を commit 済みなら `git blame -w -M -C <修正の commit>^ -- <file>`、未 commit なら `git blame -w -M -C HEAD -- <file>`。消した・足りなかったコードは `git log -S'<式>' -- <file>` で探す
- 候補の commit は `git show <commit> -- <file>` で、**差分に欠陥そのものが入っている**ことを確かめる。入っていなければ特定できていない。整形・移動だけの commit、merge commit、blame の `^` 付き（root か shallow clone の境界）がこれに当たる

## append

```bash
c="$(git rev-parse --verify --quiet '<原因の commit>^{commit}')" &&
git log -1 --no-show-signature --format=%B "$c" | grep -qi '^Co-Authored-By: Claude' &&
t="$(git log -1 --no-show-signature --format=%at "$c")" &&
jq -nc --argjson t "$t" --arg s "<何をどう間違えたか 1 行>（由来 $(git rev-parse --short "$c")）" \
  '{ts:($t|todate),summary:$s,verdict:null}' >> .claude/failure-journal/candidates.jsonl
```

- `&&` で連結しているので、途中で失敗すると何も書かない。commit を解決できない・trailer が無い・日時が取れない（`$t` が空だと `--argjson` が失敗する）のどれでも止まる。blame の `^` 付きを貼った場合も `git log` が空になって止まる
- `--no-show-signature` を外さない。`log.showSignature=true` の環境では署名の検証結果が日付より前に出て、`ts` が壊れる
- `%at` は author date の epoch 秒で、`todate` が UTC・`Z` 終端に直す（`retro-aggregate.sh` は `ts` を文字列で比較する）。squash merge の commit ではマージ時刻になり、PR の期間ぶん遅れる
- summary の `（由来 <短縮 sha>）` は retro が diagnose の行を見分け、同じ原因の重複をまとめるのに使う。summary は伏せ字の対象（SKILL.md「秘密情報を伏せる」）
