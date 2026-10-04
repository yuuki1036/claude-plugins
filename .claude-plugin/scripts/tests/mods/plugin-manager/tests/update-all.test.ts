// plugin-manager の update-all mod（hooks/update-all.ts）のテスト。`claude plugin test` で走る
//
// `claude plugin` CLI と ~/.claude 配下のファイルは、状態を持つ偽物で答える（実物は e2e で確かめた）
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { expect, mock, test } from 'claude-code/testing'

import { changelogBetween, parseConfig } from '../hooks/update-all-lib'

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
  mock.env(on, { HOME })
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
  expect((await updateAll($)).text).toContain(`| alpha@${MP} | 1.0.0 | - | エラー |`)

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

test('changelogBetween / parseConfig', () => {
  const text = '## [2.0.0]\n- b\n\n## [1.5.0]\n- a\n\n## [1.0.0]\n- old\n'
  expect(changelogBetween(text, '1.0.0', '2.0.0')).toBe('## [2.0.0]\n- b\n\n## [1.5.0]\n- a')
  expect(changelogBetween(text.trimEnd(), '0.9.0', '2.0.0')).toBe(text.trimEnd())
  expect(changelogBetween(text, '1.0.0', '3.0.0')).toBeNull()
  expect(parseConfig(null)).toEqual({ autoMigrate: true, ignorePlugins: [], ignoreMarketplaces: [] })
  expect(parseConfig('{"auto_migrate": false}').autoMigrate).toBe(false)
  expect(parseConfig('{"auto_migrate": null}').autoMigrate).toBe(true)
  expect(parseConfig('{').autoMigrate).toBe(true)
})
