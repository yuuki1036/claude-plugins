// guide-diff: review-guide の読み順で、タスクの diff（base branch との分岐点から）をペインに送る mod
//
// review-guide を PR 前に回した後、editor に移らずにタスクの diff だけを読みたい（GitHub issue #274 の続き）。
// Claude Code 組み込みの /diff は比較先を default branch までしか選べず、統合ブランチから切ったブランチでは
// 統合ブランチの他の変更が混ざる。入力は scripts/guide-order.sh が git dir に残す読み順の記録で、
// ここは git を読むだけ（書かない）。ペインを描けない場所では、同じ内容をコマンドの答えのテキストで返す
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { GuideFile, GuideView } from '../types'
import { GROUP_LABEL, baseLine, fileLine, parseNumstat, parseRecord, summaryText, trimDiff } from './guide-diff-lib'

const PANE = 'guide-diff'
const COMMAND = 'guide-diff'
const RECORD = 'claude-review-guide.json'
const view = atom({ plugin: 'code-review', key: 'guideDiff' } as const, null)

/**
 * パスは記録（= diff 由来）の文字列そのもの。git は既定でパスを glob として読み、`app/[id].tsx` が
 * `app/i.tsx` の差分まで拾うので、literal に固定する
 */
async function git($: EngineInterface, args: string[], cwd: string) {
  return $.process.run(['git', '--literal-pathspecs', ...args], { cwd })
}

/** 1 ファイルの diff。未追跡の新規ファイルは `git diff <base>` に出ないので /dev/null と比べる */
async function fileDiff($: EngineInterface, root: string, base: string, path: string) {
  const r = await git($, ['diff', '--no-color', '--no-ext-diff', base, '--', path], root)
  let raw = r.stdout
  if (raw.trim() === '') {
    const tracked = await git($, ['ls-files', '--error-unmatch', '--', path], root)
    if (tracked.exitCode !== 0) {
      raw = (await git($, ['diff', '--no-color', '--no-index', '--', '/dev/null', path], root)).stdout
    }
  }
  return trimDiff(raw)
}

/** 記録を読んでビューを組む。読めないときは利用者に返す文を返す */
async function load($: EngineInterface): Promise<GuideView | string> {
  const cwd = await $.session.cwd()
  const top = await git($, ['rev-parse', '--show-toplevel'], cwd)
  const gd = await git($, ['rev-parse', '--absolute-git-dir'], cwd)
  if (top.exitCode !== 0 || gd.exitCode !== 0) return 'git の作業ツリーではない'
  const root = top.stdout.trim()
  let text: string
  try {
    text = await $.fs.read(`${gd.stdout.trim()}/${RECORD}`)
  } catch {
    return '読み順の記録が無い。PR を作る前のブランチで review-guide を回すと記録される'
  }
  const rec = parseRecord(text)
  if (typeof rec === 'string') return rec
  const known = await git($, ['cat-file', '-e', `${rec.diff_base}^{commit}`], root)
  if (known.exitCode !== 0) return `比較先のコミット ${rec.diff_base.slice(0, 7)} がこのリポジトリに無い`
  const head = await git($, ['rev-parse', '-q', '--verify', 'HEAD'], root)
  const stat = parseNumstat(
    (await git($, ['diff', '--numstat', '--no-color', rec.diff_base, '--', ...rec.files.map(f => f.path)], root)).stdout,
  )
  const files: GuideFile[] = rec.files.map(f => ({
    path: f.path,
    group: f.group,
    added: stat.get(f.path)?.added ?? null,
    deleted: stat.get(f.path)?.deleted ?? null,
  }))
  return {
    root,
    baseBranch: rec.base_branch,
    baseSource: rec.base_source,
    diffBase: rec.diff_base,
    isHeadMoved: rec.head !== '' && head.stdout.trim() !== rec.head,
    files,
    index: 0,
    diff: '',
    isTruncated: false,
  }
}

/** index のファイルへ移り、その diff を読み込む。範囲外は端で止める */
async function show($: EngineInterface, move: (index: number, count: number) => number) {
  let target: { root: string; base: string; path: string; index: number } | null = null
  await update($, view, v => {
    if (v === null) return v
    const index = Math.min(Math.max(move(v.index, v.files.length), 0), v.files.length - 1)
    const file = v.files[index]
    target = file ? { root: v.root, base: v.diffBase, path: file.path, index } : null
    return { ...v, index }
  })
  const t = target as { root: string; base: string; path: string; index: number } | null
  if (t === null) return
  const { diff, isTruncated } = await fileDiff($, t.root, t.base, t.path)
  // 読み込む間に別のファイルへ移っていたら、古い diff で上書きしない
  await update($, view, v => (v !== null && v.index === t.index ? { ...v, diff, isTruncated } : v))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'review-guide の読み順で、base branch との分岐点からの diff をファイルごとに送る',
      argumentHint: '[N 番目から]',
      immediate: true,
    })
    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    const loaded = await load($)
    if (typeof loaded === 'string') return { text: `guide-diff: ${loaded}` }
    const n = Number.parseInt(e.args.trim(), 10)
    const start = Number.isFinite(n) ? n - 1 : 0
    await update($, view, () => loaded)
    await show($, (_, count) => Math.min(start, count - 1))
    const opened = await $.ui.open({ id: PANE, title: `guide diff · ${loaded.baseBranch}` })
    return { text: summaryText(loaded, opened.isPlaced ? undefined : opened.reason) }
  })

  // review-guide が読み順を記録したら、開けることを知らせる（開くのは利用者のコマンドで: 頼まれずに開いた
  // ペインは広いターミナルでしか置かれないため）
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny === undefined && ran.isError !== true && /guide-order\.sh/.test(e.command) && /guide_order=/.test(ran.text ?? '')) {
      $.ui.toast('読み順の diff を /guide-diff で開ける')
    }
    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Code } = $.ui.resolve(e)
    const v = await read($, view)
    if (v === null) {
      return <Text dimColor>/guide-diff で review-guide の読み順を読み込む</Text>
    }
    const file = v.files[v.index]
    const listRows = Math.min(v.files.length, 8)
    const first = Math.min(Math.max(v.index - 3, 0), Math.max(v.files.length - listRows, 0))
    return (
      <Box flexDirection="column">
        <Text dimColor>{baseLine(v)}</Text>
        {v.isHeadMoved && <Text color="warning">ガイドを作った後にコミットが進んでいる（diff は今の作業ツリーと比較先の差）</Text>}
        <Box flexDirection="column" marginTop={1}>
          {v.files.slice(first, first + listRows).map((f, i) => (
            <Text bold={first + i === v.index} dimColor={f.group === 'skip' && first + i !== v.index} wrap="truncate-middle">
              {fileLine(f, first + i === v.index, first + i + 1)}
            </Text>
          ))}
        </Box>
        <Box gap={1} marginTop={1}>
          <Button key="prev" label="前へ" hotkey="p" onPress={() => show($, i => i - 1)} />
          <Button key="next" label="次へ" hotkey="n" variant="primary" onPress={() => show($, i => i + 1)} />
          <Button
            key="copy"
            label="比較先をコピー"
            hotkey="c"
            onPress={async () => {
              const cur = await $.state.get({ plugin: 'code-review', key: 'guideDiff' } as const)
              if (cur.value) await $.ui.copy({ text: cur.value.diffBase, surface: e.surface })
            }}
          />
          <Button key="close" label="閉じる" role="dismiss" onPress={() => $.ui.close({ id: PANE })} />
        </Box>
        {file && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>
              {v.index + 1}/{v.files.length} [{GROUP_LABEL[file.group]}] {file.path}
            </Text>
            {v.diff === '' ? (
              <Text dimColor>（差分なし、または読み込み中）</Text>
            ) : (
              <Code source={v.diff} format="diff" path={file.path} />
            )}
            {v.isTruncated && <Text dimColor>（長いので途中まで。続きは editor で比較先と比べる）</Text>}
          </Box>
        )}
      </Box>
    )
  })
}
