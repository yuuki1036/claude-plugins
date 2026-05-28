# DB 命名規約

worktree 名から DB 名を導出するルールとサンプル。

## 基本規約

```
DB_NAME = ${BASE_DB}_${WORKTREE_NAME_SANITIZED}
```

- `BASE_DB`: プロジェクトの本来の DB 名（例: `appdb`）
- `WORKTREE_NAME_SANITIZED`: `WORKTREE_NAME` を DB 識別子として valid な形に sanitize

例:

| BASE_DB | WORKTREE_NAME | DB_NAME |
|---|---|---|
| `appdb` | `feature-payment` | `appdb_feature_payment` |
| `app_prod` | `bugfix/login` | `app_prod_bugfix_login` |
| `myapp` | `wt1` | `myapp_wt1` |

## sanitize 関数

```bash
sanitize_db_name() {
  local raw=$1
  echo "$raw" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -c 'a-z0-9' '_' \
    | sed -E 's/_+/_/g; s/^_+|_+$//g'
}

WORKTREE_NAME_SANITIZED=$(sanitize_db_name "$WORKTREE_NAME")
DB_NAME="${BASE_DB}_${WORKTREE_NAME_SANITIZED}"
```

- 小文字化
- 英数以外（`-` / `/` / `.` 等）を `_` に置換
- 連続 `_` を 1 つに圧縮、先頭末尾の `_` を除去

## DB エンジン別の制約

| エンジン | 識別子最大長 | 許容文字 | 注意 |
|---|---|---|---|
| PostgreSQL | 63 bytes | `[a-zA-Z_][a-zA-Z0-9_$]*` | quoted なら制限緩い |
| MySQL | 64 chars | ほぼ任意（quoted） | `-` を含めると quoting 必須 |
| SQLite | 制限なし | ファイル名と同じ | パス区切り注意 |
| SQL Server | 128 chars | `[a-zA-Z_@#][a-zA-Z0-9_@#$]*` | 先頭 `#` で temp table |

長すぎる worktree 名は truncate するか、ハッシュサフィックスに切り替える。

```bash
# 長すぎたら頭 20 文字 + 短ハッシュ
if [ ${#DB_NAME} -gt 50 ]; then
  HASH=$(echo "$DB_NAME" | shasum | cut -c1-6)
  DB_NAME="${BASE_DB}_$(echo "$WORKTREE_NAME_SANITIZED" | cut -c1-20)_${HASH}"
fi
```

## create コマンドサンプル

### PostgreSQL

```bash
psql -U postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || psql -U postgres -c "CREATE DATABASE ${DB_NAME};"
```

### MySQL

```bash
mysql -uroot -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### SQLite

```bash
# DB 名 = ファイル名
DB_FILE="db/${DB_NAME}.sqlite3"
touch "$DB_FILE"
```

### docker-compose の volume 分離

DB をコンテナで動かしている場合、worktree 単位で volume も分けると安全:

```yaml
services:
  postgres:
    environment:
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_data_${WORKTREE_NAME}:/var/lib/postgresql/data

volumes:
  postgres_data_feature_payment:
  postgres_data_feature_signup:
```

## drop 漏れ対策

`worktree-teardown` で DB drop に失敗すると次回 `worktree-setup` で「既に存在」扱いになる。teardown 側で「drop 成功確認 + 失敗時の警告出力」を実装してあるため、setup 側では既存 DB を上書きしない方針（壊さない）に倒している。

---

> プロジェクト固有のため必要に応じて override してください。
