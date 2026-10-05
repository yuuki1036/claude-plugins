// issue-workflow の mod（hooks/issue-band.tsx）が $.state に置く値の型の契約

export type IssueBand = {
  issueId: string
  /** Issue ファイルの見出し `# <ID>: <タイトル>` のタイトル。ファイルが無ければ空 */
  title: string
  status: string
  type: string
  branch: string
  scopeSize: string
  /** `## 進捗`（無ければ `## 完了条件`）のチェックリストの済み / 全体 */
  done: number
  total: number
  /** scope_size のタスク数の上限。scope_size が無い・不明なら null */
  limit: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'issue-workflow': { band: IssueBand | null; bandHidden: boolean }
  }
}
