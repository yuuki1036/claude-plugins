### 2. 状態確認

```bash
git status
git branch -vv
git remote show origin | grep "HEAD branch"
git log <base-branch>..HEAD --oneline
git diff <base-branch>...HEAD
git diff <base-branch>...HEAD --shortstat
```

diff のファイル数・行数を把握する。目安（400 行超 または 10 ファイル超）を大きく超える場合は、PR 作成は継続しつつ Step 5 のレポート末尾に分割検討の advisory を一言添える。判断基準は `${CLAUDE_PLUGIN_ROOT}/skills/pr-creator/references/description-guide.md` の「変更の粒度を小さく保つ（Small CL）」を参照。

**次は Step 3**（SKILL.md に戻り、その見出しを見る）
