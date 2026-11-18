// plugin-manager の update-all mod（hooks/update-all.ts）のテスト。`claude plugin test` で走る
//
// `claude plugin` CLI と ~/.claude 配下のファイルは、状態を持つ偽物で答える（実物は e2e で確かめた）
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { expect, mock, test } from 'claude-code/testing'

import { changelogBetween, hubRereadText, hubTargets, parseConfig } from '../hooks/update-all-lib'

const HOME = '/h'
const MP = 'mine'

type Cat = { version: string; supersededBy?: string }
type Cli = {
  installed: Map<string, string>
  catalogs: Record<string, Record<string, Cat>>
  failInstall: Set<string>
  /** `uninstall` の何段目まで失敗させるか（3 なら CLI は全部失敗し、手で外す段へ進む） */
  uninstallFailures: Map<string, number>
  /** marketplace update しても install に反映されない（キャッシュが古い）プラグインと、入ってしまう古い版 */
  stuck: Map<string, string>
  listFails: boolean
  calls: string[]
  config: string | null
  changelogs: Record<string, string>
  installedJson: string | null
  /** installed_plugins.json に載せない id（project scope などで、手で外す段でも外せない） */
  notInJson: Set<string>
  modelRan: boolean
  /** ~/.claude/project-hub/<PJ>/ の config.json と hub.json。null ならディレクトリごと無い */
  hubs: Record<string, { config?: string; hub?: string }> | null
  /** 届く宛先（名前・会話の ID。`sid:<id>` は { sessionId } で送った回） */
  reachable: Set<string>
  /** HOME 以外の環境変数 */
  env: Record<string, string>
  sends: { to: string; text: string }[]
}

function newCli(over: Partial<Cli> = {}): Cli {
  return {
    installed: new Map([
      [`plugin-manager@${MP}`, '1.0.0'],
      [`alpha@${MP}`, '1.0.0'],
      ['other@theirs', '2.0.0'],
    ]),
    catalogs: {
      [MP]: { 'plugin-manager': { version: '1.0.0' }, alpha: { version: '1.1.0' }, beta: { version: '0.1.0' } },
      theirs: { other: { version: '2.1.0' } },
    },
    failInstall: new Set(),
    uninstallFailures: new Map(),
    stuck: new Map(),
    listFails: false,
    calls: [],
    config: null,
    changelogs: {},
    installedJson: null,
    notInJson: new Set(),
    modelRan: false,
    hubs: null,
    reachable: new Set(),
    env: {},
    sends: [],
    ...over,
  }
}

function ok(stdout = '', exitCode = 0) {
  return { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}

function fakeClaude(c: Cli, argv: readonly string[]) {
  const [bin, sub, ...rest] = argv
  if (bin !== 'claude' || sub !== 'plugin') return ok('', 127)
  c.calls.push(rest.join(' '))
  const [cmd, a1] = rest
  if (cmd === 'list') {
    if (c.listFails) return ok('', 1)
    const rows = [...c.installed].map(([id, version]) => {
      const [name, mp] = id.split('@')
      return { id, version, scope: 'user', installPath: `/cache/${mp}/${name}/${version}` }
    })
    return ok(JSON.stringify(rows))
  }
  if (cmd === 'marketplace' && a1 === 'update') return ok()
  if (cmd === 'uninstall' && a1) {
    const n = c.uninstallFailures.get(a1) ?? 0
    const level = rest.includes('user') ? 2 : rest.includes('project') ? 3 : 1
    if (level <= n || !c.installed.has(a1)) return ok('', 1)
    c.installed.delete(a1)
    return ok()
  }
  if (cmd === 'install' && a1) {
    if (c.failInstall.has(a1)) return ok('', 1)
    const [name, mp] = a1.split('@')
    const entry = c.catalogs[mp ?? '']?.[name ?? '']
    if (!entry) return ok('', 1)
    c.installed.set(a1, c.stuck.get(a1) ?? entry.version)
    return ok()
  }
  return ok('', 2)
}

function stub(on: On, c: Cli) {
  mock.env(on, { HOME, ...c.env })
  on('process.run', (_$, e) => ({ value: fakeClaude(c, e.argv) }))
  on('fs.read', (_$, e) => {
    const p = e.path
    if (p === `${HOME}/.claude/plugin-manager/config.json` && c.config !== null) return { value: c.config }
    if (p === `${HOME}/.claude/plugins/known_marketplaces.json`) {
      return { value: JSON.stringify({ [MP]: { installLocation: '/src/mine' } }) }
    }
    const mp = p === '/src/mine/.claude-plugin/marketplace.json' ? MP
      : p === `${HOME}/.claude/plugins/marketplaces/theirs/.claude-plugin/marketplace.json` ? 'theirs' : null
    if (mp) {
      const plugins = Object.entries(c.catalogs[mp] ?? {}).map(([name, v]) => ({
        name, version: v.version, ...(v.supersededBy ? { _superseded_by: v.supersededBy } : {}),
      }))
      return { value: JSON.stringify({ name: mp, plugins }) }
    }
    if (p in c.changelogs) return { value: c.changelogs[p] as string }
    const hub = /^(?:\/h\/\.claude\/project-hub|\/hubs)\/([^/]+)\/(config|hub)\.json$/.exec(p)
    const file = hub ? c.hubs?.[hub[1] as string]?.[hub[2] as 'config' | 'hub'] : undefined
    if (file !== undefined) return { value: file }
    if (p === `${HOME}/.claude/plugins/installed_plugins.json`) {
      return { value: JSON.stringify({ version: 2, plugins: Object.fromEntries([...c.installed].filter(([id]) => !c.notInJson.has(id)).map(([id, v]) => [id, [{ version: v }]])) }) }
    }
    return { deny: `ENOENT ${p}` }
  })
  on('fs.write', (_$, e) => {
    if (e.path === `${HOME}/.claude/plugins/installed_plugins.json`) {
      c.installedJson = e.text
      const kept = Object.keys((JSON.parse(e.text) as { plugins: Record<string, unknown> }).plugins)
      for (const id of [...c.installed.keys()]) if (!kept.includes(id)) c.installed.delete(id)
    }
    return { value: undefined }
  })
  on('fs.list', (_$, e) => {
    const root = c.env.PROJECT_HUB_DIR ?? `${HOME}/.claude/project-hub`
    if (e.path !== root || c.hubs === null) return { deny: `ENOENT ${e.path}` }
    const dirs = Object.keys(c.hubs).map(name => ({ name, kind: 'dir' as const, size: 0, mtimeMs: 0, isLink: false }))
    return { value: [...dirs, { name: 'bin', kind: 'file' as const, size: 1, mtimeMs: 0, isLink: false }] }
  })
  // 実物のセッションへは送らない: 宛先と本文を控え、reachable にあるものだけ届いたことにする
  on('session.send', (_$, e) => {
    c.sends.push({ to: e.to, text: e.text })
    // { sessionId } の宛先の綴りは engine が決めるので、id を含むかで見る（会話の ID `local_<id>` は除く）
    const ok = c.reachable.has(e.to) || [...c.reachable].some(r => r.startsWith('sid:') && e.to.includes(r.slice(4)) && e.to !== `local_${r.slice(4)}`)
    return ok ? { isDelivered: true } : { isDelivered: false, reason: `no session named ${e.to}` }
  })
  on('session.id', () => ({ value: 'self-session' }))
  on('ui.status', () => ({ value: undefined }))
  on('command.run', () => {
    c.modelRan = true
    return { text: 'MODEL' }
  })
}

async function updateAll($: Engine, args = '', command = 'plugin-manager:update-all') {
  return $.command.run({ command, args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
}

test('自作プラグインだけを、モデルを呼ばずに更新して表で返す', async ($, on) => {
  const c = newCli({ changelogs: { [`/cache/${MP}/alpha/1.1.0/CHANGELOG.md`]: '# C\n\n## [1.1.0] - x\n\n- 新機能\n\n## [1.0.0] - y\n\n- 古い\n' } })
  stub(on, c)
  const r = await updateAll($)
  expect(c.modelRan).toBe(false)
  expect(r.text).toContain(`自作プラグイン（@${MP}）2 件を対象に更新しました`)
  expect(r.text).toContain(`| alpha@${MP} | 1.0.0 | 1.1.0 | 更新済み |`)
  expect(r.text).toContain(`| plugin-manager@${MP} | 1.0.0 | 1.0.0 | 変更なし |`)
  expect(r.text).not.toContain('other@theirs')
  expect(r.text).toContain('#### alpha (1.0.0 → 1.1.0)')
  expect(r.text).toContain('- 新機能')
  expect(r.text).not.toContain('- 古い')
  expect(r.text).toContain('動いているセッションには、そのセッションで使った skill が更新されていれば')
  expect(c.calls.filter(x => x.startsWith('marketplace update'))).toEqual([`marketplace update ${MP}`])
  expect(c.installed.get('other@theirs')).toBe('2.0.0')
})

test('--all は他のマーケットプレイスも更新する / 名前空間なしの起動でも動く', async ($, on) => {
  const c = newCli()
  stub(on, c)
  const r = await updateAll($, '--all', 'update-all')
  expect(c.modelRan).toBe(false)
  expect(r.text).toContain('インストール済みの全プラグイン 3 件')
  expect(r.text).toContain('| other@theirs | 2.0.0 | 2.1.0 | 更新済み |')
  expect(r.text).toContain('CHANGELOG なし')
  expect(c.calls.filter(x => x.startsWith('marketplace update')).sort()).toEqual([`marketplace update ${MP}`, 'marketplace update theirs'])
})

test('一覧が読めない・自分が見つからないときは、何も変えずにモデルの手順へ渡す', async ($, on) => {
  const c = newCli({ listFails: true })
  stub(on, c)
  expect((await updateAll($)).text).toBe('MODEL')
  expect(c.calls).toEqual(['list --json'])
  c.listFails = false
  c.installed.delete(`plugin-manager@${MP}`)
  c.modelRan = false
  expect((await updateAll($)).text).toBe('MODEL')
  expect(c.calls.filter(x => !x.startsWith('list'))).toEqual([])
})

test('uninstall は既定 → user → project → 手で外す、の順に試す', async ($, on) => {
  const c = newCli({ uninstallFailures: new Map([[`alpha@${MP}`, 3]]) })
  stub(on, c)
  const r = await updateAll($)
  expect(c.calls.filter(x => x.startsWith(`uninstall alpha@${MP}`))).toEqual([
    `uninstall alpha@${MP}`,
    `uninstall alpha@${MP} --scope user`,
    `uninstall alpha@${MP} --scope project`,
  ])
  expect(JSON.parse(c.installedJson ?? '{}').plugins).not.toHaveProperty(`alpha@${MP}`)
  expect(r.text).toContain(`| alpha@${MP} | 1.0.0 | 1.1.0 | 更新済み |`)
})

test('install に失敗したら エラー、反映されなければ 未反映（キャッシュは消さない）', async ($, on) => {
  const c = newCli({ failInstall: new Set([`alpha@${MP}`]) })
  stub(on, c)
  const failed = (await updateAll($)).text
  expect(failed).toContain(`| alpha@${MP} | 1.0.0 | - | エラー |`)
  // 更新が 1 件も無ければ、動いているセッションへの通知の行は出さない
  expect(failed).not.toContain('動いているセッションには')

  const d = newCli({ stuck: new Map([[`alpha@${MP}`, '1.0.0']]) })
  Object.assign(c, d)
  const r = await updateAll($)
  expect(r.text).toContain(`| alpha@${MP} | 1.0.0 | 1.0.0 | 未反映（marketplace: 1.1.0） |`)
  expect(r.text).toContain('claude plugin update')
  expect(c.calls.some(x => x.includes('cache'))).toBe(false)
})

test('どの段でも外せず install も失敗したら、残った版を「変更なし」とせず エラー にする / 載っていない記録は書き換えない', async ($, on) => {
  const c = newCli({
    uninstallFailures: new Map([[`alpha@${MP}`, 3]]),
    notInJson: new Set([`alpha@${MP}`]),
    failInstall: new Set([`alpha@${MP}`]),
  })
  stub(on, c)
  const r = await updateAll($)
  expect(c.installed.get(`alpha@${MP}`)).toBe('1.0.0')
  expect(r.text).toContain(`| alpha@${MP} | 1.0.0 | - | エラー |`)
  expect(c.installedJson).toBeNull()
})

test('deprecated は後継へ移行し、後継の install に失敗したら元に戻す', async ($, on) => {
  const c = newCli()
  c.catalogs[MP] = { ...c.catalogs[MP], alpha: { version: '1.1.0', supersededBy: 'beta' } }
  stub(on, c)
  const r = await updateAll($)
  expect(r.text).toContain(`- alpha@${MP} → beta@${MP} へ移行しました`)
  expect([...c.installed.keys()].sort()).toEqual([`beta@${MP}`, 'other@theirs', `plugin-manager@${MP}`])
  expect(r.text).not.toContain(`| alpha@${MP} |`)

  const d = newCli({ failInstall: new Set([`beta@${MP}`]) })
  d.catalogs[MP] = { ...d.catalogs[MP], alpha: { version: '1.1.0', supersededBy: 'beta' } }
  Object.assign(c, d)
  const r2 = await updateAll($)
  expect(r2.text).toContain('の移行に失敗')
  expect(c.installed.has(`alpha@${MP}`)).toBe(true)
})

test('auto_migrate が false なら移行せず候補として報告する', async ($, on) => {
  const c = newCli({ config: JSON.stringify({ auto_migrate: false }) })
  c.catalogs[MP] = { ...c.catalogs[MP], alpha: { version: '1.1.0', supersededBy: 'beta' } }
  stub(on, c)
  const r = await updateAll($)
  expect(r.text).toContain(`移行候補（auto_migrate=false のためスキップ）: alpha@${MP} → beta@${MP}`)
  expect(c.installed.has(`beta@${MP}`)).toBe(false)
})

test('未インストールの自作プラグインを挙げる（deprecated・ignore は除く）', async ($, on) => {
  const c = newCli()
  c.catalogs[MP] = { ...c.catalogs[MP], gamma: { version: '1.0.0' }, old: { version: '1.0.0', supersededBy: 'beta' } }
  stub(on, c)
  const r = await updateAll($)
  expect(r.text).toContain(`- beta@${MP}`)
  expect(r.text).toContain(`- gamma@${MP}`)
  expect(r.text).not.toContain(`- old@${MP}`)

  Object.assign(c, newCli({ config: JSON.stringify({ ignore_plugins: [`gamma@${MP}`] }) }), { catalogs: c.catalogs })
  const r2 = await updateAll($)
  expect(r2.text).not.toContain(`- gamma@${MP}`)
  Object.assign(c, newCli({ config: JSON.stringify({ ignore_marketplaces: [MP] }) }), { catalogs: c.catalogs })
  expect((await updateAll($)).text).not.toContain('### 未インストールの自作プラグイン')
})

const active = JSON.stringify({ status: 'active' })
function hubJson(sessionId: string, name: string) {
  return JSON.stringify({ session_id: sessionId, host_session_id: `local_${sessionId}`, name, updated: 'x' })
}
/** project-hub を 1.0.0 → 1.1.0 に上げる構成 */
function withProjectHub(over: Partial<Cli> = {}): Cli {
  const c = newCli(over)
  c.installed.set(`project-hub@${MP}`, '1.0.0')
  c.catalogs[MP] = { ...c.catalogs[MP], 'project-hub': { version: '1.1.0' } }
  return c
}

test('project-hub を更新したら、active な PJ の hub 系セッションへ読み直しを 1 回ずつ頼む', async ($, on) => {
  const c = withProjectHub({
    hubs: {
      a: { config: active, hub: hubJson('s1', 'hub a') },
      // 同じ会話が 2 つの PJ を兼ねる
      b: { config: active, hub: hubJson('s1', 'hub a') },
      closed: { config: JSON.stringify({ status: 'closed' }), hub: hubJson('s2', 'hub closed') },
      broken: { config: active, hub: '{' },
      nohub: { config: active },
    },
  })
  stub(on, c)
  const r = await updateAll($)
  expect(c.modelRan).toBe(false)
  // 同じ会話へは session_id → 会話の ID → 名前の 1 巡だけ。closed・壊れた・hub.json の無い PJ へは送らない
  expect(c.sends.length).toBe(3)
  expect(c.sends.map(x => x.to).slice(1)).toEqual(['local_s1', 'hub a'])
  const first = c.sends[0]
  expect(first?.to).toContain('s1')
  expect(first?.text).toContain('project-hub が 1.0.0 → 1.1.0 に更新された')
  expect(first?.text).toContain(`/cache/${MP}/project-hub/1.1.0/skills/<skill>/SKILL.md`)
  expect(r.text).toContain('### hub 系セッションへの読み直し依頼')
  expect(r.text).toContain('- 送らなかった: hub a（a, b） — ')
})

test('session_id → 会話の ID → 名前の順に、届いたところで止める', async ($, on) => {
  const c = withProjectHub({ hubs: { a: { config: active, hub: hubJson('s1', 'hub a') } }, reachable: new Set(['hub a']) })
  stub(on, c)
  const r = await updateAll($)
  expect(c.sends.map(x => x.to).slice(1)).toEqual(['local_s1', 'hub a'])
  expect(r.text).toContain('- 送った: hub a（a）')

  Object.assign(c, withProjectHub({ hubs: c.hubs, reachable: new Set(['local_s1']) }))
  await updateAll($)
  expect(c.sends.map(x => x.to).slice(1)).toEqual(['local_s1'])

  Object.assign(c, withProjectHub({ hubs: c.hubs, reachable: new Set(['sid:s1']) }))
  await updateAll($)
  expect(c.sends.length).toBe(1)

  // 会話の ID も名前も無い hub.json は session_id だけ試す
  Object.assign(c, withProjectHub({ hubs: { a: { config: active, hub: JSON.stringify({ session_id: 's9' }) } } }))
  const r4 = await updateAll($)
  expect(c.sends.length).toBe(1)
  expect(r4.text).toContain('- 送らなかった: s9（a） — no session named')
})

test('hub の会話で打った回は自分には送らず、そう報告する', async ($, on) => {
  const c = withProjectHub({ hubs: { a: { config: active, hub: hubJson('self-session', 'hub a') } }, reachable: new Set(['sid:self-session']) })
  stub(on, c)
  const r = await updateAll($)
  expect(c.sends).toEqual([])
  expect(r.text).toContain('- 送らなかった: hub a（a） — このセッション自身')
})

test('session_id が古くても、会話の ID が自分なら送らない', async ($, on) => {
  const c = withProjectHub({ hubs: { a: { config: active, hub: hubJson('old', 'hub a') } }, env: { CLAUDE_CODE_HOST_SESSION_ID: 'local_old' }, reachable: new Set(['local_old']) })
  stub(on, c)
  const r = await updateAll($)
  expect(c.sends).toEqual([])
  expect(r.text).toContain('- 送らなかった: hub a（a） — このセッション自身')
})

test('--all で別マーケットプレイスの project-hub だけが上がった回は送らない', async ($, on) => {
  const c = newCli({ hubs: { a: { config: active, hub: hubJson('s1', 'hub a') } }, reachable: new Set(['local_s1']) })
  c.installed.set('project-hub@theirs', '1.0.0')
  c.catalogs.theirs = { ...c.catalogs.theirs, 'project-hub': { version: '2.0.0' } }
  stub(on, c)
  const r = await updateAll($, '--all')
  expect(r.text).toContain('| project-hub@theirs | 1.0.0 | 2.0.0 | 更新済み |')
  expect(c.sends).toEqual([])
  expect(r.text).not.toContain('hub 系セッション')
})

test('PROJECT_HUB_DIR があればそこを project-hub のデータとして読む', async ($, on) => {
  const c = withProjectHub({ hubs: { a: { config: active, hub: hubJson('s1', 'hub a') } }, env: { PROJECT_HUB_DIR: '/hubs' }, reachable: new Set(['local_s1']) })
  stub(on, c)
  const r = await updateAll($)
  expect(r.text).toContain('- 送った: hub a（a）')
})

test('project-hub 以外の更新・project-hub が無い環境では送らない', async ($, on) => {
  const c = newCli({ hubs: { a: { config: active, hub: hubJson('s1', 'hub a') } } })
  stub(on, c)
  const r = await updateAll($)
  expect(r.text).toContain(`| alpha@${MP} | 1.0.0 | 1.1.0 | 更新済み |`)
  expect(c.sends).toEqual([])
  expect(r.text).not.toContain('hub 系セッション')

  Object.assign(c, withProjectHub())
  const r2 = await updateAll($)
  expect(r2.text).toContain(`| project-hub@${MP} | 1.0.0 | 1.1.0 | 更新済み |`)
  expect(c.sends).toEqual([])
  expect(r2.text).toContain('- 送らなかった: hub 系のセッションが無い')
})

test('hubRereadText は installPath が取れない回に壊れたパスを出さない', () => {
  const row = { id: `project-hub@${MP}`, before: '1.0.0', after: '1.1.0', result: 'updated' as const }
  expect(hubRereadText(row, '/cache/p/1.1.0')).toContain('新しい版: /cache/p/1.1.0/skills/<skill>/SKILL.md')
  const text = hubRereadText(row, '')
  expect(text).not.toContain(' /skills/')
  expect(text).toContain('installPath（1.1.0）')
})

test('hubTargets', () => {
  expect(hubTargets([])).toEqual([])
  expect(hubTargets([
    { project: 'a', config: active, hub: hubJson('s1', 'hub a') },
    { project: 'b', config: active, hub: JSON.stringify({ session_id: '' }) },
    { project: 'c', config: null, hub: hubJson('s3', 'hub c') },
    { project: 'd', config: active, hub: JSON.stringify({ session_id: 's4' }) },
  ])).toEqual([
    { sessionId: 's1', name: 'hub a', hostSessionId: 'local_s1', projects: ['a'] },
    { sessionId: 's4', name: null, hostSessionId: null, projects: ['d'] },
  ])
})

test('changelogBetween / parseConfig', () => {
  const text = '## [2.0.0]\n- b\n\n## [1.5.0]\n- a\n\n## [1.0.0]\n- old\n'
  expect(changelogBetween(text, '1.0.0', '2.0.0')).toBe('## [2.0.0]\n- b\n\n## [1.5.0]\n- a')
  expect(changelogBetween(text.trimEnd(), '0.9.0', '2.0.0')).toBe(text.trimEnd())
  expect(changelogBetween(text, '1.0.0', '3.0.0')).toBeNull()
  // backport（1.9.6）を時系列の位置に挟んだ CHANGELOG でも、before より新しく after 以下の節を全部拾う（GitHub issue #464）
  const backport = '# Changelog\n\n## [Unreleased]\n- u\n\n## [2.1.0]\n- d\n\n## [1.9.6]\n- c\n\n## [2.0.1]\n- b\n\n## [2.0.0]\n- a\n'
  expect(changelogBetween(backport, '2.0.0', '2.1.0')).toBe('## [2.1.0]\n- d\n\n## [2.0.1]\n- b')
  expect(changelogBetween(backport, '1.9.6', '2.1.0')).toBe('## [2.1.0]\n- d\n\n## [2.0.1]\n- b\n\n## [2.0.0]\n- a')
  expect(changelogBetween(backport, '2.0.0', '2.0.1')).toBe('## [2.0.1]\n- b')
  expect(changelogBetween(backport, '2.1.0', '2.1.0')).toBeNull()
  // 古さを比べられない（semver でない）版は、これまでどおり並び順で切り出す
  expect(changelogBetween('## [2.0.0]\n- b\n\n## [dev]\n- a\n\n## [0.9.0]\n- old\n', 'dev', '2.0.0')).toBe('## [2.0.0]\n- b')
  expect(parseConfig(null)).toEqual({ autoMigrate: true, ignorePlugins: [], ignoreMarketplaces: [] })
  expect(parseConfig('{"auto_migrate": false}').autoMigrate).toBe(false)
  expect(parseConfig('{"auto_migrate": null}').autoMigrate).toBe(true)
  expect(parseConfig('{').autoMigrate).toBe(true)
})
