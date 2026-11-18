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

const SEMVER_RE = /^(\d+)\.(\d+)\.(\d+)/
const HEADING_RE = /^## \[([^\]]+)\]/

function semver(ver: string): number[] | null {
  const m = SEMVER_RE.exec(ver)
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
}

function compareSemver(a: number[], b: number[]): number {
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] - b[i]
  return 0
}

/**
 * CHANGELOG のうち、before より新しく after 以下の版の節（見出しから次の版の見出しの手前まで）を、ファイルの並びのまま返す。
 * `## [after]` の見出しが無いか、該当する節が空なら null。
 * 並び順に頼らず版で比べる。backport を時系列の位置に挟んだ CHANGELOG では、before の見出しより下にも新しい節がある
 * （stale-skill の stale_skill.py の changelog_headings と同じ規則 / GitHub issue #464）。
 * semver でない見出し（Unreleased・版ラベル）は入っている版の変更ではないので含めない。
 * before か after が semver でなければ古さを比べられないので、`## [after]` から `## [before]` の直前までを並び順で切り出す
 */
export function changelogBetween(text: string, before: string, after: string): string | null {
  const lines = text.split('\n')
  const start = lines.findIndex(l => l.startsWith(`## [${after}]`))
  if (start < 0) return null
  const lo = semver(before)
  const hi = semver(after)
  let kept: string[]
  if (lo === null || hi === null) {
    let end = lines.findIndex((l, i) => i > start && l.startsWith(`## [${before}]`))
    if (end < 0) end = lines.length
    kept = lines.slice(start, end)
  } else {
    kept = []
    let keep = false
    for (const l of lines) {
      const m = HEADING_RE.exec(l)
      if (m) {
        const v = semver(m[1])
        keep = v !== null && compareSemver(v, lo) > 0 && compareSemver(v, hi) <= 0
      }
      if (keep) kept.push(l)
    }
  }
  const body = kept.join('\n').trim()
  return body === '' ? null : body
}

const RESULT_LABEL: Record<Row['result'], string> = {
  updated: '更新済み',
  unchanged: '変更なし',
  error: 'エラー',
  stale: '未反映',
}

/** 読み直しを頼む hub 系のセッション（project-hub の hub.json 1 つ。同じ会話が複数の PJ を兼ねることがある） */
export type HubTarget = { sessionId: string; name: string | null; hostSessionId: string | null; projects: string[] }

/** 読み直しの依頼を送った結果。届かなかった回は理由を必ず持つ（SDK の SessionSendResult と同じ形） */
export type HubNotice = { name: string; projects: string[] } & ({ delivered: true } | { delivered: false; reason: string })

/**
 * project-hub のデータの置き場所の `<PJ>/` にある config.json と hub.json から、依頼を送る hub 系のセッションを決める（Phase 4.8）。
 * config.json の status が active の PJ だけを数え、同じ session_id は 1 件にまとめる。
 * project-hub の内部ファイルを読むだけで project-hub には依存しない: 読めない・形が違う PJ は落とす
 */
export function hubTargets(entries: { project: string; config: string | null; hub: string | null }[]): HubTarget[] {
  const bySession = new Map<string, HubTarget>()
  for (const e of entries) {
    if (e.config === null || e.hub === null) continue
    try {
      const config = JSON.parse(e.config) as Record<string, unknown>
      const hub = JSON.parse(e.hub) as Record<string, unknown>
      if (config.status !== 'active' || typeof hub.session_id !== 'string' || hub.session_id === '') continue
      const str = (v: unknown) => (typeof v === 'string' && v !== '' ? v : null)
      const t = bySession.get(hub.session_id)
      if (t) t.projects.push(e.project)
      else bySession.set(hub.session_id, { sessionId: hub.session_id, name: str(hub.name), hostSessionId: str(hub.host_session_id), projects: [e.project] })
    } catch {
      continue
    }
  }
  return [...bySession.values()]
}

/** hub 系のセッションへ送る依頼の本文。1 行目だけで用件が分かるようにする（受け手の一覧は 1 行目しか見せない） */
export function hubRereadText(row: Row, installPath: string): string {
  return [
    `[plugin-manager] update-all で project-hub が ${row.before} → ${row.after} に更新された。次の発言から、project-hub の skill は新しい版の SKILL.md を Read し直してから使う。`,
    // installPath が取れなかった回は壊れたパスを見せず、版だけで探させる
    installPath !== ''
      ? `新しい版: ${installPath}/skills/<skill>/SKILL.md（同梱の scripts/ も同じ版を使う）`
      : `新しい版: ~/.claude/plugins/installed_plugins.json の project-hub の installPath（${row.after}）の skills/<skill>/SKILL.md`,
    '返事は不要。',
  ].join('\n')
}

/** Phase 5 の報告（commands/update-all.md のフォーマット）。hubNotices は project-hub を更新しなかった回は null */
export function report(
  scope: string,
  rows: Row[],
  migrations: Migration[],
  skippedMigrations: string[],
  missing: string[],
  hubNotices: HubNotice[] | null = null,
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
  if (hubNotices !== null) {
    out.push('', '### hub 系セッションへの読み直し依頼', '')
    if (hubNotices.length === 0) out.push('- 送らなかった: hub 系のセッションが無い（project-hub のデータに active な PJ が無い）')
    for (const n of hubNotices) {
      const who = `${n.name}（${n.projects.join(', ')}）`
      out.push(n.delivered ? `- 送った: ${who}` : `- 送らなかった: ${who} — ${n.reason}`)
    }
  }
  out.push('', '反映にはClaude Codeの再起動が必要です。')
  // 再起動しないで動き続けるセッションへは、stale-skill hook が次の発言で知らせる（GitHub issue #416）
  if (updated.length > 0) out.push('動いているセッションには、そのセッションで使った skill が更新されていれば、次の発言で読み直す SKILL.md のパスを知らせる。')
  return out.join('\n')
}
