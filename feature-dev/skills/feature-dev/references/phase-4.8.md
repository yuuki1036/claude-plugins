## Phase 4.8: 実装環境の分離（worktree・opt-in）

**Goal**: 並列開発・メインツリーを汚さない実装のために、実装フェーズ以降を worktree 内で回す。設計（Phase 1〜4）は読み取りのみなので、書き込みが始まる Phase 5 の手前で環境を確定させる。

**起動条件**: ユーザーが「worktree」を明示した（引数・会話）か、プロジェクト指示（CLAUDE.md / memory）が worktree 作業を指示している場合のみ。**自分の判断では作らない**（`EnterWorktree` の利用条件）。

```bash
# メインの clone か linked worktree か
[ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ] && POS=main || POS=worktree
```

| 状態 | アクション |
|---|---|
| `main` + 明示要求なし | **Phase 4.8 を skip** して Phase 5 へ（従来の挙動・何も報告しない） |
| `main` + 明示要求あり | `${CLAUDE_PLUGIN_ROOT}/references/worktree-flow.md` を Read し、Step 1（作成・移動）から従う |
| `worktree`（すでに worktree 内） | 同 doc を Read し、Step 2（環境セットアップ）から従う |

**Output**: worktree 内で続行する場合、doc の Step 3「引き継ぎ規約」が Phase 5.3 / 5.5 / 6 / 7 の挙動に効く（特に Phase 7 の publish 先）。

**次は Phase 5**（SKILL.md に戻り、その見出しの入口の条件を見る）
