// update-all mod: `/update-all` をモデルを呼ばずにその場で実行する
//
// 手順は commands/update-all.md が正本で、ここはそれを順に実行するだけ。モデルに Bash で回させると
// トークンを使い、手順の取り違えも起きた（GitHub issue #271 のキャッシュ削除）。mods が無効な環境では
// 今までどおり markdown のコマンドがモデルに渡る。最初の変更（marketplace の再取得）の前に
// 前提が崩れたら（CLI が無い・一覧が読めない）、何も変えずにモデルの経路へ戻す
import type { EngineInterface, On, SessionSendResult } from 'claude-code'

import {
  changelogBetween,
  hubRereadText,
  hubTargets,
  parseConfig,
  parseInstalled,
  parseMarketplace,
  report,
  type HubNotice,
  type Installed,
  type MarketplaceEntry,
  type Migration,
  type Row,
} from './update-all-lib'

type Run = { ok: boolean; stdout: string; stderr: string }

async function cli($: EngineInterface, args: string[], timeoutMs = 120_000): Promise<Run> {
  try {
    const r = await $.process.run(['claude', 'plugin', ...args], { timeoutMs })
    return { ok: r.exitCode === 0, stdout: r.stdout, stderr: r.stderr }
  } catch (err) {
    return { ok: false, stdout: '', stderr: String(err) }
  }
}

async function readText($: EngineInterface, path: string): Promise<string | null> {
  try {
    const t = await $.fs.read(path)
    return typeof t === 'string' ? t : null
  } catch {
    return null
  }
}

/** marketplace.json の中身。登録先（known_marketplaces.json の installLocation）を優先する */
async function marketplace($: EngineInterface, home: string, mp: string): Promise<MarketplaceEntry[]> {
  let dir = `${home}/.claude/plugins/marketplaces/${mp}`
  const known = await readText($, `${home}/.claude/plugins/known_marketplaces.json`)
  if (known !== null) {
    try {
      const loc = (JSON.parse(known) as Record<string, { installLocation?: unknown }>)[mp]?.installLocation
      if (typeof loc === 'string' && loc !== '') dir = loc
    } catch {
      // 既定の場所で読む
    }
  }
  const text = await readText($, `${dir}/.claude-plugin/marketplace.json`)
  return text === null ? [] : parseMarketplace(text)
}

/** Phase 3-1: 既定 → --scope user → --scope project → installed_plugins.json から手で外す */
async function uninstall($: EngineInterface, home: string, id: string): Promise<boolean> {
  for (const extra of [[], ['--scope', 'user'], ['--scope', 'project']]) {
    if ((await cli($, ['uninstall', id, ...extra])).ok) return true
  }
  const path = `${home}/.claude/plugins/installed_plugins.json`
  const text = await readText($, path)
  if (text === null) return false
  try {
    const data = JSON.parse(text) as { plugins?: Record<string, unknown> }
    if (!data.plugins || !(id in data.plugins)) return false
    delete data.plugins[id]
    await $.fs.write(path, JSON.stringify(data, null, 2))
    return true
  } catch {
    return false
  }
}

async function run($: EngineInterface, args: string): Promise<string | null> {
  const home = (await $.env.get('HOME')) ?? ''
  // Phase 0
  const list0 = await cli($, ['list', '--json'], 60_000)
  const all = list0.ok ? parseInstalled(list0.stdout) : null
  const self = all?.find(p => p.name === 'plugin-manager')
  if (!all || !self) return null
  const isAll = /(^|\s)--all(\s|$)/.test(args)
  const targets = isAll ? all : all.filter(p => p.marketplace === self.marketplace)
  const scope = isAll
    ? `インストール済みの全プラグイン ${targets.length} 件を対象に更新しました。`
    : `自作プラグイン（@${self.marketplace}）${targets.length} 件を対象に更新しました。全件対象にする場合は /update-all --all`
  const config = parseConfig(await readText($, `${home}/.claude/plugin-manager/config.json`))

  // Phase 1: キャッシュは消さない（#271）
  const mps = [...new Set(targets.map(t => t.marketplace))]
  for (const mp of mps) {
    $.ui.status(`update-all: marketplace ${mp} を再取得中`)
    await cli($, ['marketplace', 'update', mp])
  }
  const catalogs = new Map<string, MarketplaceEntry[]>()
  for (const mp of new Set([...mps, self.marketplace])) catalogs.set(mp, await marketplace($, home, mp))

  // Phase 2.5: deprecated → 後継（後継ごとに、全部 uninstall → 後継を 1 回 install）
  const migrations: Migration[] = []
  const skipped: string[] = []
  const migrated = new Set<string>()
  const groups = new Map<string, Installed[]>()
  for (const t of targets) {
    const succ = catalogs.get(t.marketplace)?.find(e => e.name === t.name)?.supersededBy
    if (!succ) continue
    const key = `${succ}@${t.marketplace}`
    groups.set(key, [...(groups.get(key) ?? []), t])
  }
  for (const [to, from] of groups) {
    if (!config.autoMigrate) {
      skipped.push(`${from.map(f => f.id).join(', ')} → ${to}`)
      continue
    }
    $.ui.status(`update-all: ${to} へ移行中`)
    for (const f of from) {
      await uninstall($, home, f.id)
      migrated.add(f.id)
    }
    const hasSucc = all.some(p => p.id === to)
    const ok = hasSucc || (await cli($, ['install', to])).ok
    if (!ok) {
      // ロールバック: プラグインが 1 つも無い状態で放置しない
      for (const f of from) await cli($, ['install', f.id])
    }
    migrations.push({ from: from.map(f => f.id), to, ok, detail: ok ? '' : `${to} を install できなかったので元に戻した` })
  }

  // Phase 3: 順に再インストール（並列にしない）
  const failed = new Set<string>()
  const rest = targets.filter(t => !migrated.has(t.id))
  for (const [i, t] of rest.entries()) {
    $.ui.status(`update-all: ${i + 1}/${rest.length} ${t.name}`)
    await uninstall($, home, t.id)
    if (!(await cli($, ['install', t.id])).ok) failed.add(t.id)
  }

  // Phase 4 / 4.5
  const list1 = await cli($, ['list', '--json'], 60_000)
  const after = new Map((parseInstalled(list1.stdout) ?? []).map(p => [p.id, p]))
  const rows: Row[] = []
  for (const t of rest) {
    const a = after.get(t.id)
    if (failed.has(t.id) || a === undefined) {
      rows.push({ id: t.id, before: t.version, after: null, result: 'error' })
      continue
    }
    const latest = catalogs.get(t.marketplace)?.find(e => e.name === t.name)?.version ?? null
    if (latest !== null && latest !== a.version) {
      rows.push({ id: t.id, before: t.version, after: a.version, result: 'stale', latest })
    } else if (a.version !== t.version) {
      const text = a.installPath ? await readText($, `${a.installPath}/CHANGELOG.md`) : null
      const changelog = text === null ? undefined : (changelogBetween(text, t.version, a.version) ?? undefined)
      rows.push({ id: t.id, before: t.version, after: a.version, result: 'updated', ...(changelog ? { changelog } : {}) })
    } else {
      rows.push({ id: t.id, before: t.version, after: a.version, result: 'unchanged' })
    }
  }

  // Phase 4.7: 自作マーケットプレイスの未インストール（deprecated は勧めない）
  const missing: string[] = []
  if (!config.ignoreMarketplaces.includes(self.marketplace)) {
    for (const e of catalogs.get(self.marketplace) ?? []) {
      const id = `${e.name}@${self.marketplace}`
      if (e.supersededBy || after.has(id) || config.ignorePlugins.includes(id)) continue
      missing.push(id)
    }
  }

  // Phase 4.8: project-hub を更新した回だけ、hub 系のセッションへ読み直しを頼む（GitHub issue #460）
  // `--all` で入る別マーケットプレイスの同名プラグインは、hub が使う project-hub ではないので数えない
  const hubRow = rows.find(r => r.result === 'updated' && r.id === `project-hub@${self.marketplace}`)
  const hubNotices = hubRow ? await notifyHubs($, home, hubRow, after.get(hubRow.id)?.installPath ?? '') : null

  $.ui.status(undefined)
  return report(scope, rows, migrations, skipped, missing, hubNotices)
}

/** 動いている hub 系のセッションへ、更新後の SKILL.md を読み直すよう送る。project-hub のデータが無ければ 0 件 */
async function notifyHubs($: EngineInterface, home: string, row: Row, installPath: string): Promise<HubNotice[]> {
  // project-hub のデータの置き場所の決め方（hub.py の PROJECT_HUB_DIR / CLAUDE_CONFIG_DIR）に合わせる
  const configDir = (await $.env.get('CLAUDE_CONFIG_DIR')) || `${home}/.claude`
  const root = (await $.env.get('PROJECT_HUB_DIR')) || `${configDir}/project-hub`
  let dirs: string[]
  try {
    dirs = (await $.fs.list(root)).filter(e => e.kind === 'dir').map(e => e.name).sort()
  } catch {
    return []
  }
  const entries = []
  for (const project of dirs) {
    entries.push({
      project,
      config: await readText($, `${root}/${project}/config.json`),
      hub: await readText($, `${root}/${project}/hub.json`),
    })
  }
  const text = hubRereadText(row, installPath)
  // hub の会話で /update-all を打った回は、この結果をそのまま読むので自分には送らない。
  // hub.json の session_id は開き直すと古いまま残ることがあるので、会話の ID でも照合する（hub.py の SessionStart と同じ照合）
  const selfId = await $.session.id().catch(() => '')
  const selfHost = (await $.env.get('CLAUDE_CODE_HOST_SESSION_ID')) ?? ''
  const notices: HubNotice[] = []
  for (const t of hubTargets(entries)) {
    if (t.sessionId === selfId || (selfHost !== '' && t.hostSessionId === selfHost)) {
      notices.push({ name: t.name ?? t.sessionId, projects: t.projects, delivered: false, reason: 'このセッション自身（この結果を読めば足りる）' })
      continue
    }
    $.ui.status(`update-all: ${t.name ?? t.sessionId} へ読み直しを依頼中`)
    // session_id → 会話の ID（host_session_id）→ 名前の順に、届くまで試す（commands/update-all.md の Phase 4.8）。
    // session_id は会話を開き直すと hub の status が直すまで古い。会話の ID は開き直しても改名しても変わらない。
    // 名前は重なると宛先が決まらないので最後に回す
    let sent = await send($, { sessionId: t.sessionId }, text)
    if (!sent.isDelivered && t.hostSessionId !== null) sent = await send($, t.hostSessionId, text)
    if (!sent.isDelivered && t.name !== null) sent = await send($, t.name, text)
    const who = { name: t.name ?? t.sessionId, projects: t.projects }
    notices.push(sent.isDelivered ? { ...who, delivered: true } : { ...who, delivered: false, reason: sent.reason })
  }
  return notices
}

async function send($: EngineInterface, to: string | { sessionId: string }, text: string): Promise<SessionSendResult> {
  try {
    return await $.session.send({ to, text })
  } catch (err) {
    return { isDelivered: false, reason: String(err) }
  }
}

export function registerUpdateAll(on: On) {
  // 前提が崩れた（CLI が無い・一覧が読めない）ときは、何も変えずに markdown の手順をモデルに渡す
  on('command.run', { command: 'plugin-manager:update-all' }, async ($, e, next) => {
    const text = await run($, e.args)
    return text === null ? next(e) : { text }
  })
  // 名前空間なしで打たれ、そのまま届いた回
  on('command.run', { command: 'update-all' }, async ($, e, next) => {
    const text = await run($, e.args)
    return text === null ? next(e) : { text }
  })
}
