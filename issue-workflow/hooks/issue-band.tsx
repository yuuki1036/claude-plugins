// issue-band: 作業中の Issue（ID・タイトル・状態・タスクの進み・ブランチ）をプロンプトの上の帯に出す mod
//
// どの Issue の作業中かは issue-workflow:start が書く `.claude/session-context.md` で決まり、今まではテキストの
// 注入（scope の超過は PostToolUse の check-scope-size.sh）でしか見えなかった。ここは読むだけで何も書かない。
// session-context のブランチが今のブランチと違えば（別の作業に移った）出さない
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { IssueBand } from '../types'
import { bandLine, issueSummary, overLine, sessionContext } from './issue-band-lib'

const band = atom({ plugin: 'issue-workflow', key: 'band' } as const, null)
const isHidden = atom({ plugin: 'issue-workflow', key: 'bandHidden' } as const, false)

/** 帯を読み直すきっかけになる Bash（ブランチの切り替え） */
const BRANCH_RE = /\bgit\b.*\b(checkout|switch)\b/
/** 帯を読み直すきっかけになるファイル（Issue と session-context） */
const FILE_RE = /\.claude\/((indie|linear)\/[^/]+\/issues\/[^/]+\.md|session-context\.md)$/

async function git($: EngineInterface, args: string[], cwd: string): Promise<string | null> {
  try {
    const r = await $.process.run(['git', ...args], { cwd, timeoutMs: 5000 })
    return r.exitCode === 0 ? r.stdout.trim() : null
  } catch {
    return null
  }
}

async function text($: EngineInterface, path: string): Promise<string | null> {
  try {
    const t = await $.fs.read(path)
    return typeof t === 'string' ? t : null
  } catch {
    return null
  }
}

/**
 * linked worktree の中ならメインのチェックアウトの絶対パス、それ以外は null。
 * Issue ファイルを gitignore している repo では worktree にデータ dir が無い（GitHub issue #280）
 */
async function mainCheckout($: EngineInterface, root: string): Promise<string | null> {
  const gitDir = await git($, ['rev-parse', '--absolute-git-dir'], root)
  const common = await git($, ['rev-parse', '--path-format=absolute', '--git-common-dir'], root)
  if (gitDir === null || common === null || gitDir === common || !common.endsWith('/.git')) return null
  return common.slice(0, -'/.git'.length)
}

/** 今の帯の中身。出すものが無ければ null */
export async function load($: EngineInterface): Promise<IssueBand | null> {
  const cwd = await $.session.cwd()
  const root = await git($, ['rev-parse', '--show-toplevel'], cwd)
  const branch = root === null ? null : await git($, ['rev-parse', '--abbrev-ref', 'HEAD'], root)
  if (root === null || branch === null) return null
  const ctxText = await text($, `${root}/.claude/session-context.md`)
  const ctx = ctxText === null ? null : sessionContext(ctxText)
  if (ctx === null || ctx.branch !== branch) return null
  const main = await mainCheckout($, root)
  for (const base of main === null ? [root] : [root, main]) {
    for (const backend of ['indie', 'linear']) {
      let slugs: { name: string }[]
      try {
        slugs = (await $.fs.list(`${base}/.claude/${backend}`)) as { name: string }[]
      } catch {
        continue
      }
      for (const s of slugs) {
        const issue = await text($, `${base}/.claude/${backend}/${s.name}/issues/${ctx.issueId}.md`)
        if (issue !== null) return issueSummary(issue, ctx.issueId, branch)
      }
    }
  }
  // Issue ファイルが見つからなくても、どの Issue の作業中かは出す
  return { issueId: ctx.issueId, title: '', status: '', type: '', branch, scopeSize: '', done: 0, total: 0, limit: null }
}

async function refresh($: EngineInterface) {
  const v = await load($)
  const prev = await read($, band)
  // 別の Issue に移ったら、隠していた帯をまた出す
  if (v !== null && prev?.issueId !== v.issueId) await update($, isHidden, () => false)
  await update($, band, () => v)
}

export function registerIssueBand(on: On) {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    await refresh($)
    return r
  })

  on('prompt.submit', async ($, e, next) => {
    await refresh($)
    return next(e)
  })

  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const r = await next(e)
    if (e.agentId === undefined && FILE_RE.test(e.file_path)) await refresh($)
    return r
  })

  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const r = await next(e)
    if (e.agentId === undefined && FILE_RE.test(e.file_path)) await refresh($)
    return r
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const r = await next(e)
    if (e.agentId === undefined && BRANCH_RE.test(e.command)) await refresh($)
    return r
  })

  // 他のプラグインの帯の上に重ねる（next を呼ばずに返すと、下の帯が消える）
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const below = await next(e)
    const b = await read($, band)
    if (b === null || e.props.hasSurvey || (await read($, isHidden))) return below
    const { Box, Button, Text } = $.ui.resolve(e)
    const over = overLine(b)
    return (
      <Box flexDirection="column">
        <Box gap={1}>
          <Text dimColor wrap="truncate-end">
            {bandLine(b)}
          </Text>
          <Button key="hide-issue" label="隠す" onPress={() => update($, isHidden, () => true)} />
        </Box>
        {over !== null && <Text color="warning">{over}</Text>}
        {below}
      </Box>
    )
  })
}
