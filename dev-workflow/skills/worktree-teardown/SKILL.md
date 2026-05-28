---
name: worktree-teardown
description: |
  git worktree の安全な破棄。DB drop / port 解放 / env クリーンアップを cleanup チェックリストで確認する。
  teardown 漏れ（DB drop 失敗・port leak）を検知して警告する。
  トリガー: 「worktree 破棄」「worktree 削除」「並列開発環境クリーンアップ」「worktree teardown」「/worktree-teardown」
effort: medium
allowed-tools:
  - Bash
  - Read
  - Edit
  - Glob
  - Grep
---

# worktree-teardown

`worktree-setup` で作った worktree 環境を安全に破棄する。DB / port / env の片付けを cleanup チェックリストで順次確認し、漏れがあれば警告する。

## 適用範囲

- `worktree-setup` を実行済みの worktree（マーカー `envs/.backend.env.worktree` が存在する worktree）
- マーカーが無い worktree でも `git worktree remove` だけは実行可能（DB / port 後処理はスキップ）

main の clone 上では実行不可。worktree 内から実行する。

## 実行手順

### Step 1: 状態確認

```bash
WORKTREE_DIR=$(git rev-parse --show-toplevel)
WORKTREE_NAME=$(basename "$WORKTREE_DIR")
BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_DIR=$(git rev-parse --git-dir)
GIT_COMMON=$(git rev-parse --git-common-dir)

if [[ "$GIT_DIR" == "$GIT_COMMON" ]]; then
  echo "ERROR: main の clone では worktree-teardown を実行できない" >&2
  exit 1
fi
```

マーカーの存在を確認し、`worktree-setup` 済みかどうかを判定する。

```bash
MARKER="envs/.backend.env.worktree"
if [ -f "$MARKER" ]; then
  # 割当内容を読み込む
  set -a; source "$MARKER"; set +a
else
  echo "WARNING: $MARKER が無い。DB / port の後処理はスキップして git worktree remove のみ実行する"
fi
```

### Step 2: cleanup チェックリスト実行

[references/cleanup-checklist.md](references/cleanup-checklist.md) の項目を順次確認する。各項目の成否を内部状態に持ち、最後にまとめてレポート。

#### チェックリスト

- [ ] **1. プロセス停止**: worktree 上の dev server / DB プロセスが停止しているか
- [ ] **2. DB drop**: `worktree-setup` で作った DB が drop されたか
- [ ] **3. port 解放**: 動的割当 port が LISTEN していないか
- [ ] **4. env マーカー削除**: `envs/*.worktree` ファイルが削除されたか
- [ ] **5. uncommitted 変更チェック**: コミットしていない変更が無いか
- [ ] **6. git worktree remove**: worktree が git 管理から外せたか

### Step 3: プロセス停止（チェック 1）

worktree 配下で起動中の dev server / DB プロセスを検出。

```bash
# 該当 port を LISTEN しているプロセス
for port in "${BACKEND_PORT}" "${FRONTEND_PORT}" "${DB_PORT}"; do
  [ -z "$port" ] && continue
  pids=$(lsof -i ":$port" -t 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "port $port を占有中: PID $pids"
    # ユーザー確認の上で kill
  fi
done
```

検出したらユーザーに kill 許可を確認してから停止。勝手に kill しない。

### Step 4: DB drop（チェック 2）

```bash
# PostgreSQL の例
psql -U postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1
if [ $? -eq 0 ]; then
  # ユーザー確認の上で drop
  psql -U postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
fi
```

DB drop は破壊的操作のため必ずユーザー確認を取る。drop に失敗した場合は **必ず警告** を出す（漏れると次回 setup で「既に存在」エラーになる）。

```bash
if ! psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  echo "OK: DB ${DB_NAME} drop 完了"
else
  echo "WARNING: DB ${DB_NAME} の drop に失敗。手動で確認: psql -U postgres -c 'DROP DATABASE ${DB_NAME};'" >&2
fi
```

### Step 5: port 解放確認（チェック 3）

Step 3 でプロセスを止めた後、port が実際に解放されているか再確認。

```bash
for port in "${BACKEND_PORT}" "${FRONTEND_PORT}" "${DB_PORT}"; do
  [ -z "$port" ] && continue
  if lsof -i ":$port" -t >/dev/null 2>&1; then
    echo "WARNING: port $port がまだ占有されている（port leak の可能性）" >&2
  fi
done
```

leak 検出時は占有プロセスを表示して手動対応を促す。

### Step 6: env マーカー削除（チェック 4）

```bash
rm -f envs/.backend.env.worktree envs/.frontend.env.worktree
rmdir envs 2>/dev/null || true  # 中身が空なら削除
```

### Step 7: uncommitted 変更チェック（チェック 5）

`git worktree remove` する前に未コミット変更を確認。dirty なら `--force` を使うか、ユーザーに stash / commit を促す。

```bash
if [ -n "$(git status --porcelain)" ]; then
  echo "WARNING: uncommitted な変更がある:"
  git status --short
  # ユーザー確認: stash する / commit する / --force で破棄する / 中止
fi
```

### Step 8: git worktree remove（チェック 6）

worktree のディレクトリから抜けて、メインリポジトリで `git worktree remove` を実行する。

```bash
MAIN_REPO=$(git rev-parse --git-common-dir | xargs dirname)
cd "$MAIN_REPO"
git worktree remove "$WORKTREE_DIR"
# dirty で失敗したら --force（ユーザー確認後）
# git worktree remove --force "$WORKTREE_DIR"
```

### Step 9: 完了レポート

cleanup チェックリストの各項目の OK / WARNING / SKIP をまとめてユーザーに提示。

```
worktree-teardown 完了: feature-payment

[OK]      1. プロセス停止 (3 process killed)
[OK]      2. DB drop (appdb_feature_payment)
[OK]      3. port 解放 (8010 / 3010 / 5442)
[OK]      4. env マーカー削除
[OK]      5. uncommitted 変更なし
[OK]      6. git worktree remove
```

WARNING が出た項目は強調表示し、手動対応コマンドを併記する。

## 警告例

### DB drop 失敗

```
[WARNING] 2. DB drop: appdb_feature_payment の drop に失敗
  接続中のセッションが残っている可能性があります。
  手動対応:
    psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='appdb_feature_payment';"
    psql -U postgres -c "DROP DATABASE appdb_feature_payment;"
```

### port leak

```
[WARNING] 3. port 解放: 8010 がまだ占有されている
  占有プロセス: PID 12345 (node)
  手動対応: kill 12345
```

### uncommitted 変更

```
[WARNING] 5. uncommitted 変更あり:
  M  src/feature.ts
  ?? new-file.md
  対応: git stash / git commit / git worktree remove --force のいずれかを選択
```

## 絶対厳守ルール

- `main`（メインの clone）では実行しない
- DB drop / プロセス kill / `git worktree remove --force` は **必ずユーザー確認を取ってから** 実行する
- DB drop / port 解放に失敗したら silently スキップせず、必ず WARNING で残す
- マーカーファイル削除前に DB drop と env 内容の保存（必要なら）を済ませる（削除すると DB 名 / port が分からなくなる）
- 兄弟 worktree が起動中の場合、その port まで kill しないよう、現 worktree の env に書かれた port のみを対象にする

## Additional Resources

### Reference Files

- **`references/cleanup-checklist.md`** - 6 項目のチェックリスト詳細と漏れ検出パターン
