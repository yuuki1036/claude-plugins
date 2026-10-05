// dev-workflow の mod（hooks/worktree-gc.tsx）が $.state に置く値の型の契約

/** scan.sh の 1 行（表示に使う分だけ取り出し、元の行は `line` にそのまま持つ） */
export type GcRow = {
  /** scan.sh が出した行そのもの。reap.sh にはこれを書き換えずに渡す（入力契約） */
  line: string
  repo: string
  path: string
  branch: string | null
  head: string | null
  kind: string
  verdict: 'reap' | 'keep'
  reasons: string[]
  /** `#<番号> <状態>`。PR が無ければ null */
  pr: string | null
  lastCommit: string | null
}

export type GcView = {
  rows: GcRow[]
  /** rows と同じ並び。reap の行だけが選べる */
  selected: boolean[]
  /** list: 選ぶ / dry: dry-run 済み（この選び方なら削除できる）/ running: 実行中 / done: 削除済み */
  phase: 'list' | 'dry' | 'running' | 'done'
  /** dry-run したときの選び方（selectionKey）。選び直したら list に戻す */
  dryKey: string
  /** dry-run / reap の出力 */
  output: string
  /** scan の前の fetch に失敗したリポなどの注記 */
  note: string
}

declare module 'claude-code' {
  interface PluginState {
    'dev-workflow': { gc: GcView | null }
  }
}
