# worktree-teardown cleanup チェックリスト

`worktree-teardown` skill が順次確認する 6 項目の詳細と、漏れ検出パターン。

## チェック項目一覧

| # | 項目 | 失敗時の影響 | 検出方法 |
|---|---|---|---|
| 1 | プロセス停止 | port leak / DB connection 残留 | `lsof -i :$port -t` |
| 2 | DB drop | 次回 setup で「既に存在」 | `pg_database` / `mysql.show_databases` 確認 |
| 3 | port 解放 | 兄弟 worktree との port 衝突 | `lsof -i :$port -t` 再確認 |
| 4 | env マーカー削除 | 次回 setup で worktree-ready 誤判定 | ファイル存在チェック |
| 5 | uncommitted 変更 | 作業ロスト / `--force` 暴発 | `git status --porcelain` |
| 6 | git worktree remove | worktree 一覧に残骸 | `git worktree list` |

## 1. プロセス停止

### 検出

```bash
# env から読んだ port を対象に
for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$DB_PORT"; do
  [ -z "$port" ] && continue
  lsof -i ":$port" -sTCP:LISTEN -t 2>/dev/null
done
```

### 対応

- 検出されたら `lsof -i :$port` で詳細表示（プロセス名 / コマンドライン）
- ユーザー確認 → `kill <pid>` で停止
- それでも残るなら `kill -9 <pid>`

### 漏れ検出

- worktree のディレクトリ配下を `cwd` にしているプロセスを `lsof -d cwd` で確認
- node / python / ruby / docker container のいずれかが残っていないか

## 2. DB drop

### 検出

```bash
# PostgreSQL
psql -U postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1

# MySQL
mysql -uroot -e "SHOW DATABASES LIKE '$DB_NAME'" | grep -q "$DB_NAME"

# SQLite (file)
[ -f "db/${DB_NAME}.sqlite3" ]
```

### 対応

- 存在を確認したらユーザーに drop 許可を取って実行
- 接続中セッションがあると drop に失敗する。`pg_terminate_backend` 等で先に切る

```bash
# PostgreSQL: 接続切断 → drop
psql -U postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();
"
psql -U postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
```

### 漏れ検出

drop 後に再度存在チェックして、残っていれば必ず WARNING を出す:

```
[WARNING] 2. DB drop: $DB_NAME の drop に失敗
  接続中のセッション or 権限不足の可能性
  手動対応:
    psql -U postgres -c "DROP DATABASE $DB_NAME;"
```

## 3. port 解放確認

### 検出

Step 1 のプロセス停止後に再度 lsof で確認する。kill しても TIME_WAIT で数十秒残ることがあるので、`-sTCP:LISTEN` フィルタで LISTEN 状態のみを対象にする。

```bash
for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$DB_PORT"; do
  if lsof -i ":$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[WARNING] port $port leak"
  fi
done
```

### 対応

- 占有プロセスを表示
- 兄弟 worktree が同じ port を使ってないか確認（env を読んで照合）

## 4. env マーカー削除

### 検出

```bash
[ -f envs/.backend.env.worktree ] || [ -f envs/.frontend.env.worktree ]
```

### 対応

```bash
rm -f envs/.backend.env.worktree envs/.frontend.env.worktree
# 空ディレクトリも片付け
rmdir envs 2>/dev/null || true
```

### 注意

env を削除する前に DB 名 / port を控えておく（あとで再 teardown 試行する場合に必要）。

## 5. uncommitted 変更

### 検出

```bash
git status --porcelain
```

何か出力があれば dirty。

### 対応の選択肢

ユーザーに以下を提示:

- **stash**: `git stash push -m "worktree-teardown:$WORKTREE_NAME"`
- **commit**: 別途 `/git-commit-helper` を呼ぶ
- **force remove**: 変更を破棄して `git worktree remove --force`（破壊的、要確認）
- **中止**: teardown を止めて別途整理

## 6. git worktree remove

### 実行

```bash
MAIN_REPO=$(git rev-parse --git-common-dir | xargs dirname)
cd "$MAIN_REPO"
git worktree remove "$WORKTREE_DIR"
```

### 失敗パターン

- **dirty**: Step 5 で対応済みのはずだが、untracked ファイルだけ残っていることがある → `--force`
- **prunable な残骸**: 過去に worktree を rm -rf した残骸が `git worktree list` に出る → `git worktree prune`

### 確認

```bash
git worktree list
# 該当 worktree が消えていれば OK
```

## 全体の漏れ検出スクリプト

teardown 完了後にもう一度全項目を再チェックしてユーザーに提示する:

```bash
report_status() {
  local label=$1
  local condition=$2
  if eval "$condition"; then
    echo "[OK]      $label"
  else
    echo "[WARNING] $label"
  fi
}

report_status "1. プロセス停止"   '[ -z "$(lsof -i :$BACKEND_PORT -t 2>/dev/null)" ]'
report_status "2. DB drop"        '! psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='"'"'$DB_NAME'"'"'" | grep -q 1'
report_status "3. port 解放"      '[ -z "$(lsof -i :$BACKEND_PORT -t 2>/dev/null)" ]'
report_status "4. env マーカー"    '[ ! -f envs/.backend.env.worktree ]'
report_status "5. 変更なし"        '[ -z "$(cd $WORKTREE_DIR && git status --porcelain)" ] || true'
report_status "6. worktree remove" '! git worktree list | grep -q "$WORKTREE_DIR"'
```

---

> プロジェクト固有のため必要に応じて override してください。
