// update-all mod の純粋な部分（CLI の出力の読み取りと、報告の組み立て）。手順の正本は commands/update-all.md

export type Installed = { id: string; name: string; marketplace: string; version: string; installPath: string }

export type MarketplaceEntry = { name: string; version: string | null; supersededBy: string | null }

export type Row = {
  id: string
  before: string
  after: string | null
  /** 更新済み / 変更なし / エラー / 未反映 */
  result: 'updated' | 'unchanged' | 'error' | 'stale'
  /** 未反映のとき marketplace にある版 */
  latest?: string
  changelog?: string
}

export type Migration = { from: string[]; to: string; ok: boolean; detail: string }

export type Config = { autoMigrate: boolean; ignorePlugins: string[]; ignoreMarketplaces: string[] }

/** `claude plugin list --json` の出力。読めない行は落とす */
export function parseInstalled(stdout: string): Installed[] | null {
  let data: unknown
  try {
    data = JSON.parse(stdout)
  } catch {
    return null
  }
  if (!Array.isArray(data)) return null
  const out: Installed[] = []
  for (const p of data) {
    if (typeof p?.id !== 'string' || !p.id.includes('@')) continue
    const at = p.id.lastIndexOf('@')
    out.push({
      id: p.id,
      name: p.id.slice(0, at),
      marketplace: p.id.slice(at + 1),
      version: typeof p.version === 'string' ? p.version : '?',
      installPath: typeof p.installPath === 'string' ? p.installPath : '',
    })
  }
  return out
}

/** marketplace.json の plugins[]（名前・版・後継） */
export function parseMarketplace(text: string): MarketplaceEntry[] {
  try {
    const data = JSON.parse(text) as { plugins?: unknown }
    if (!Array.isArray(data.plugins)) return []
    return data.plugins
      .filter((p): p is Record<string, unknown> => typeof p?.name === 'string')
      .map(p => ({
        name: p.name as string,
        version: typeof p.version === 'string' ? p.version : null,
        supersededBy: typeof p._superseded_by === 'string' && p._superseded_by !== '' ? p._superseded_by : null,
      }))
  } catch {
    return []
  }
}

/** `~/.claude/plugin-manager/config.json`。無い・読めないときは既定値 */
export function parseConfig(text: string | null): Config {
  const def: Config = { autoMigrate: true, ignorePlugins: [], ignoreMarketplaces: [] }
  if (text === null) return def
  try {
    const d = JSON.parse(text) as Record<string, unknown>
    const strs = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])
    // jq の `//` と違い、false をそのまま false として読む（CLAUDE.md の Gotcha）
    return { autoMigrate: d.auto_migrate !== false, ignorePlugins: strs(d.ignore_plugins), ignoreMarketplaces: strs(d.ignore_marketplaces) }
  } catch {
    return def
  }
}

/** CHANGELOG の `## [after]` から `## [before]` の直前まで。見出しが無ければ null */
export function changelogBetween(text: string, before: string, after: string): string | null {
  const lines = text.split('\n')
  const start = lines.findIndex(l => l.startsWith(`## [${after}]`))
  if (start < 0) return null
  let end = lines.findIndex((l, i) => i > start && l.startsWith(`## [${before}]`))
  if (end < 0) end = lines.length
  const body = lines.slice(start, end).join('\n').trim()
  return body === '' ? null : body
}

const RESULT_LABEL: Record<Row['result'], string> = {
  updated: '更新済み',
  unchanged: '変更なし',
  error: 'エラー',
  stale: '未反映',
}

/** Phase 5 の報告（commands/update-all.md のフォーマット） */
export function report(
  scope: string,
  rows: Row[],
  migrations: Migration[],
  skippedMigrations: string[],
  missing: string[],
): string {
  const out = [scope, '', '## プラグイン更新結果', '', '| プラグイン | Before | After | 結果 |', '|-----------|--------|-------|------|']
  for (const r of rows) {
    const result = r.result === 'stale' ? `未反映（marketplace: ${r.latest}）` : RESULT_LABEL[r.result]
    out.push(`| ${r.id} | ${r.before} | ${r.after ?? '-'} | ${result} |`)
  }
  const stale = rows.filter(r => r.result === 'stale')
  if (stale.length > 0) {
    out.push('', '未反映のプラグインは `claude plugin update <name@marketplace>` を実行して、もう一度確かめる（キャッシュは消さない）')
  }
  if (migrations.length > 0 || skippedMigrations.length > 0) {
    out.push('', '### 移行（deprecated → 後継）', '')
    for (const m of migrations) {
      out.push(m.ok ? `- ${m.from.join(', ')} → ${m.to} へ移行しました（uninstall → install）` : `- ${m.from.join(', ')} → ${m.to} の移行に失敗: ${m.detail}`)
    }
    for (const s of skippedMigrations) out.push(`- 移行候補（auto_migrate=false のためスキップ）: ${s}`)
  }
  const updated = rows.filter(r => r.result === 'updated')
  if (updated.length > 0) {
    out.push('', '### 更新内容')
    for (const r of updated) {
      out.push('', `#### ${r.id.slice(0, r.id.lastIndexOf('@'))} (${r.before} → ${r.after})`, '', r.changelog ?? 'CHANGELOG なし')
    }
  }
  if (missing.length > 0) {
    out.push(
      '',
      '### 未インストールの自作プラグイン',
      '',
      '自作マーケットプレイスに登録済みだが未インストールのプラグインがあります（`update-all` は更新専用のため自動導入はしません）:',
      '',
      ...missing.map(m => `- ${m}`),
      '',
      '導入する場合: `claude plugin install <name>@<marketplace>`',
      '',
      '抑止: ~/.claude/plugin-manager/config.json の ignore_plugins / ignore_marketplaces',
    )
  }
  out.push('', '反映にはClaude Codeの再起動が必要です。')
  return out.join('\n')
}
