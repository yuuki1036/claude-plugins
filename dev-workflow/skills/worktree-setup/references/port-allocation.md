# port 動的割当

worktree 用の port を空き探索で割り当てる bash 関数集。

## 基本方針

- メインで使う port を **base** とし、worktree 用は base から +10 単位で空きを探す
- 連続 worktree が増えても port 番号が読みやすい（main=3000, wt1=3010, wt2=3020 …）
- 最大探索範囲は base+1000（100 worktree 相当）でハードリミット

## 関数: allocate_port

```bash
allocate_port() {
  local base=$1
  local candidate=$base

  while [ "$candidate" -lt $((base + 1000)) ]; do
    if ! lsof -i ":$candidate" -t >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
    candidate=$((candidate + 10))
  done

  echo "ERROR: no free port in range ${base}..$((base + 1000))" >&2
  return 1
}

# 使用例
BACKEND_PORT=$(allocate_port 8000)
FRONTEND_PORT=$(allocate_port 3000)
DB_PORT=$(allocate_port 5432)
```

## lsof vs nc -z

| 方法 | 利点 | 欠点 |
|---|---|---|
| `lsof -i :$port -t` | 詳細（プロセス名等）が取れる | macOS/Linux ともに必要、Windows 不可 |
| `nc -z localhost $port` | 軽量・どこでも動く | LISTEN しているかだけしか分からない |
| `(echo >/dev/tcp/localhost/$port) 2>/dev/null` | bash 組み込み、依存なし | bash 限定（dash 不可） |

開発機が macOS / Linux なら `lsof` で十分。CI 等で軽量さが必要なら `nc -z` に切り替える。

## race condition への対処

複数 worktree で同時に `worktree-setup` を走らせると、両方が同じ空き port を掴むレース条件があり得る。実害が出るほど頻繁ではないが、気になる場合は以下のいずれか:

- ファイルロック: `flock` で `/tmp/worktree-setup.lock` を取得してから割当
- 即時占有: 割当直後にダミー process を bind して保持（dev server 起動まで）
- 重複前提: 割当後に dev server 起動を試行し、`EADDRINUSE` が出たら再割当

worktree を 2-3 個並列で運用する程度なら何もしなくて問題ない。

## 既存 worktree との port 整合

別 worktree が起動中の場合、その worktree の env を読んで重複しないか事前チェックすると親切。

```bash
# 兄弟 worktree の env を全部読んで使用済み port を集める
USED_PORTS=$(find ../ -maxdepth 3 -path '*/envs/.backend.env.worktree' \
  -exec grep -hE '^(BACKEND_PORT|FRONTEND_PORT|DB_PORT)=' {} \; \
  | cut -d= -f2 | sort -u)
```

この USED_PORTS を `allocate_port` の skip list に渡せば、起動していない worktree とも被らない割当ができる。

## カスタムベース port

プロジェクトで使う port が `3000 / 8000 / 5432` 以外なら base を上書きする。`worktree-setup` の Step 4 を編集するか、env で `BASE_BACKEND_PORT=4000` のように外から渡す設計に拡張する。

---

> プロジェクト固有のため必要に応じて override してください。
