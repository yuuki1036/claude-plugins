// code-review の guide-diff mod（hooks/guide-diff.tsx）のテスト。`claude plugin test` で走る
//
// 配布物にテストを混ぜないので、ここに置いてプラグインの複製へ重ねてから走らせる
// （起動口は test_code_review_mods.py）。git とファイルは test の on が engine の代わりに答える:
// この kit の環境には fs も process も無い
import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import { MAX_SOURCE, trimDiff } from '../hooks/guide-diff-lib'

const ROOT = '/work/repo'
const GIT_DIR = '/work/repo/.git'
const RECORD_PATH = `${GIT_DIR}/claude-review-guide.json`
const BASE = '1111111111111111111111111111111111111111'
const HEAD = '2222222222222222222222222222222222222222'
const SURFACES = ['terminal', 'desktop'] as const

const FILES = [
  { path: 'src/a.ts', group: 'read' },
  { path: 'src/new.ts', group: 'read' },
  { path: 'docs/c.md', group: 'skip' },
]

function diffOf(path: string, body: string) {
  return [
    `diff --git a/${path} b/${path}`,
    'index 0000000..1111111 100644',
    `--- a/${path}`,
    `+++ b/${path}`,
    '@@ -1,2 +1,2 @@',
    ` keep ${path}`,
    `-old ${body}`,
    `+new ${body}`,
    '',
  ].join('\n')
}

type World = {
  record?: unknown
  head?: string
  isRepo?: boolean
  placed?: boolean
  diffs?: Record<string, string>
  untracked?: Record<string, string>
  numstat?: string
  opened: string[]
  closed: string[]
  copied: string[]
  toasts: string[]
  gitCalls: string[][]
}

function newWorld(over: Partial<World> = {}): World {
  return {
    record: { schema: 1, base_branch: 'develop', base_source: 'reflog', diff_base: BASE, head: HEAD, files: FILES },
    diffs: { 'src/a.ts': diffOf('src/a.ts', 'alpha'), 'docs/c.md': diffOf('docs/c.md', 'gamma') },
    untracked: { 'src/new.ts': '--- /dev/null\n+++ b/src/new.ts\n@@ -0,0 +1 @@\n+brand new\n' },
    numstat: '1\t1\tsrc/a.ts\n1\t1\tdocs/c.md\n',
    opened: [],
    closed: [],
    copied: [],
    toasts: [],
    gitCalls: [],
    ...over,
  }
}

function out(stdout: string, exitCode = 0) {
  return { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false }
}

/** このテストに要る分だけの git。知らない呼び出しは失敗で返す（黙って空を返すと見落とす） */
function fakeGit(w: World, argv: readonly string[]) {
  w.gitCalls.push([...argv])
  if (argv[0] !== 'git') return out('', 127)
  // `app/[id].tsx` のようなパスを glob として読ませない（読ませると隣のファイルの差分が混ざる）
  if (argv[1] !== '--literal-pathspecs') return out('', 128)
  const a = argv.slice(2)
  const cmd = a.join(' ')
  if (w.isRepo === false) return out('', 128)
  if (cmd === 'rev-parse --show-toplevel') return out(`${ROOT}\n`)
  if (cmd === 'rev-parse --absolute-git-dir') return out(`${GIT_DIR}\n`)
  if (cmd === 'rev-parse -q --verify HEAD') return out(`${w.head ?? HEAD}\n`)
  if (a[0] === 'cat-file' && a[1] === '-e') return out('', a[2] === `${BASE}^{commit}` ? 0 : 1)
  if (a[0] === 'diff' && a[1] === '--numstat') return out(w.numstat ?? '')
  const path = a[a.length - 1] ?? ''
  if (cmd === `diff --no-color --no-ext-diff ${BASE} -- ${path}`) return out(w.diffs?.[path] ?? '')
  if (cmd === `ls-files --error-unmatch -- ${path}`) return out('', w.untracked?.[path] === undefined ? 0 : 1)
  if (cmd === `diff --no-color --no-index -- /dev/null ${path}`) return out(w.untracked?.[path] ?? '', 1)
  return out(`unexpected: ${cmd}`, 2)
}

function stub(on: On, w: World) {
  on('session.cwd', () => ({ value: ROOT }))
  on('fs.read', (_$, e) =>
    e.path === RECORD_PATH && w.record !== undefined
      ? { value: typeof w.record === 'string' ? w.record : JSON.stringify(w.record) }
      : { deny: `ENOENT: ${e.path}` },
  )
  on('process.run', (_$, e) => ({ value: fakeGit(w, e.argv) }))
  on('command.register', (_$, e) => ({ value: { command: e.name } }))
  on('ui.open', (_$, e) => {
    w.opened.push(e.id)
    return { value: w.placed === false ? { isPlaced: false, reason: 'narrow terminal' } : { isPlaced: true } }
  })
  on('ui.close', (_$, e) => {
    w.closed.push(e.id)
    return { value: undefined }
  })
  on('ui.copy', (_$, e) => {
    w.copied.push(e.text)
    return { value: { isCopied: true } }
  })
  on('ui.toast', (_$, e) => {
    w.toasts.push(typeof e === 'string' ? e : JSON.stringify(e))
    return { value: undefined }
  })
}

function paneProps(surface: string) {
  return {
    title: 'guide diff · develop',
    isFocused: true,
    bodyColumns: 100,
    placement: surface === 'terminal' ? ('dock' as const) : ('inline' as const),
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  }
}

/** 利用者が `/guide-diff <args>` と打ったときの実行 */
async function run($: Engine, args = '') {
  return $.command.run({
    command: 'guide-diff',
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 120 },
  })
}

test('コマンドの答えに比較先と読み順が出る（ペインを描けない場所でも読める）', async ($, on) => {
  const w = newWorld({ placed: false })
  stub(on, w)
  const r = await run($)
  expect(r.text).toContain('base: develop（このブランチを作った起点）・比較先: 1111111')
  expect(r.text).toContain(`git diff ${BASE}`)
  expect(r.text).toContain('1. [精読] src/a.ts +1 −1')
  expect(r.text).toContain('2. [精読] src/new.ts')
  expect(r.text).toContain('3. [読まなくてよい] docs/c.md +1 −1')
  expect(r.text).toContain('（ペインはまだ描かれていない: narrow terminal。')
  expect(r.text).not.toContain('⚠️')
  expect(w.opened).toEqual(['guide-diff'])
})

test('ペインが置かれたときは「描かれていない」と言わない', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  const r = await run($)
  expect(r.text).not.toContain('描かれていない')
})

test('記録が読めないときは理由だけを返し、ペインを開かない', async ($, on) => {
  const cases: [Partial<World>, string][] = [
    [{ record: undefined }, '読み順の記録が無い'],
    [{ record: '{not json' }, 'JSON として読めない'],
    [{ record: { schema: 2, diff_base: BASE, files: FILES } }, '版が違う'],
    [{ record: { schema: 1, diff_base: 'HEAD~1', files: FILES } }, '比較先のコミットが記録に無い'],
    [{ record: { schema: 1, diff_base: BASE, files: [{ path: 'a', group: 'later' }] } }, 'ファイルが無い'],
    [{ record: { schema: 1, diff_base: '3333333', files: FILES } }, 'このリポジトリに無い'],
    [{ isRepo: false }, 'git の作業ツリーではない'],
  ]
  const w = newWorld()
  stub(on, w)
  for (const [over, reason] of cases) {
    Object.assign(w, newWorld(over), { opened: w.opened })
    const r = await run($)
    expect(r.text, JSON.stringify(over)).toStartWith('guide-diff: ')
    expect(r.text, JSON.stringify(over)).toContain(reason)
  }
  expect(w.opened).toEqual([])
})

test('ガイドを作った後にコミットが進んだら知らせる', async ($, on) => {
  const w = newWorld({ head: '4444444444444444444444444444444444444444' })
  stub(on, w)
  const r = await run($)
  expect(r.text).toContain('⚠️')
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ plugin: 'code-review', surface, component: 'Pane', requestId: 'guide-diff', props: paneProps(surface) })
    expect(await ui.find({ type: 'Text', text: /コミットが進んでいる/ })).toBeDefined()
    await ui.unmount()
  }
})

test('ペインで読み順どおりにファイルを送る（端で止まる）', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  await run($)
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ plugin: 'code-review', surface, component: 'Pane', requestId: 'guide-diff', props: paneProps(surface) })
    const header = async () => (await ui.find({ type: 'Text', text: /^\d+\/3 / }))?.text
    const code = async () => (await ui.find({ type: 'Code' }))?.text ?? ''

    await ui.press({ key: 'prev' })
    expect(await header()).toBe('1/3 [精読] src/a.ts')
    expect(await code()).toStartWith('--- a/src/a.ts')
    expect(await code()).toContain('+new alpha')
    expect(await code()).not.toContain('diff --git')

    await ui.press({ key: 'next' })
    expect(await header()).toBe('2/3 [精読] src/new.ts')
    expect(await code()).toContain('+brand new')

    await ui.press({ key: 'next' })
    await ui.press({ key: 'next' })
    expect(await header()).toBe('3/3 [読まなくてよい] docs/c.md')
    expect(await code()).toContain('+new gamma')

    await ui.press({ key: 'prev' })
    await ui.press({ key: 'prev' })
    await ui.press({ key: 'prev' })
    expect(await header()).toBe('1/3 [精読] src/a.ts')
    await ui.unmount()
  }
})

test('引数の N 番目から開く（範囲外は端、数でなければ先頭）', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  const cases: [string, string][] = [
    ['2', '2/3 [精読] src/new.ts'],
    ['99', '3/3 [読まなくてよい] docs/c.md'],
    ['0', '1/3 [精読] src/a.ts'],
    ['abc', '1/3 [精読] src/a.ts'],
  ]
  for (const [args, expected] of cases) {
    await run($, args)
    const ui = await $.ui.mount({ plugin: 'code-review', surface: 'terminal', component: 'Pane', requestId: 'guide-diff', props: paneProps('terminal') })
    expect((await ui.find({ type: 'Text', text: /^\d+\/3 / }))?.text, args).toBe(expected)
    await ui.unmount()
  }
})

test('比較先をコピーし、閉じる', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  await run($)
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ plugin: 'code-review', surface, component: 'Pane', requestId: 'guide-diff', props: paneProps(surface) })
    await ui.press({ key: 'copy' })
    await ui.press({ key: 'close' })
    await ui.unmount()
  }
  expect(w.copied).toEqual([BASE, BASE])
  expect(w.closed).toEqual(['guide-diff', 'guide-diff'])
})

test('読み込む前のペインは、コマンドを案内する', async $ => {
  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ plugin: 'code-review', surface, component: 'Pane', requestId: 'guide-diff', props: paneProps(surface) })
    expect(await ui.find({ type: 'Text', text: /\/guide-diff/ })).toBeDefined()
    expect(await ui.find({ type: 'Button' })).toBeUndefined()
    await ui.unmount()
  }
})

test('長い diff はハンクの境目で切って、そう書く', async ($, on) => {
  const hunk = (n: number) => [`@@ -${n},1 +${n},1 @@`, `-${'o'.repeat(3000)}`, `+${'n'.repeat(3000)}`].join('\n')
  const big = ['diff --git a/src/a.ts b/src/a.ts', '--- a/src/a.ts', '+++ b/src/a.ts', hunk(1), hunk(10), hunk(20), ''].join('\n')
  const w = newWorld({ diffs: { 'src/a.ts': big } })
  stub(on, w)
  await run($)
  const ui = await $.ui.mount({ plugin: 'code-review', surface: 'terminal', component: 'Pane', requestId: 'guide-diff', props: paneProps('terminal') })
  const code = (await ui.find({ type: 'Code' }))?.text ?? ''
  expect(code.length).toBeLessThanOrEqual(MAX_SOURCE)
  expect(code).toContain('@@ -1,1 +1,1 @@')
  expect(code).not.toContain('@@ -10,1 +10,1 @@')
  expect(await ui.find({ type: 'Text', text: /長いので途中まで/ })).toBeDefined()
  await ui.unmount()
})

test('trimDiff: ハンク 1 つで上限を超えるときだけ途中で切る / 制御文字を落とす', () => {
  const one = trimDiff(`--- a/x\n+++ b/x\n@@ -1 +1 @@\n+${'z'.repeat(MAX_SOURCE * 2)}\n`)
  expect(one.isTruncated).toBe(true)
  expect(one.diff.length).toBeLessThanOrEqual(MAX_SOURCE)
  expect(one.diff).toStartWith('--- a/x')

  const fits = trimDiff(`--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\r\n+b\u001b[31m\tc\n`)
  expect(fits.isTruncated).toBe(false)
  expect(fits.diff).toBe('--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b[31m\tc')

  const binary = trimDiff('diff --git a/i.png b/i.png\nBinary files a/i.png and b/i.png differ\n')
  expect(binary.diff).toContain('Binary files')
})

test('review-guide が読み順を記録したときだけ、開けることを知らせる', async ($, on) => {
  const w = newWorld()
  stub(on, w)
  let answer: { text: string; isError?: true } = { text: '' }
  on('tool.call', () =>
    answer.isError
      ? { result: { stdout: '', stderr: answer.text, interrupted: false }, text: answer.text, isError: true }
      : { result: { stdout: answer.text, stderr: '', interrupted: false }, text: answer.text },
  )
  const cases: [string, { text: string; isError?: true }, boolean][] = [
    ['bash /p/scripts/guide-order.sh --diff-base abc --base develop --read a', { text: `guide_order=${RECORD_PATH}` }, true],
    ['bash /p/scripts/guide-order.sh --diff-base abc', { text: 'FATAL: --diff-base と --base は必須', isError: true }, false],
    ['echo guide_order=x', { text: 'guide_order=x' }, false],
    ['git status', { text: '' }, false],
  ]
  for (const [command, a, expected] of cases) {
    answer = a
    const before = w.toasts.length
    await $.tool.call({ tool: 'Bash', command })
    expect(w.toasts.length > before, command).toBe(expected)
  }
})
