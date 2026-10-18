import { readdir, readFile, stat } from 'node:fs/promises'
import { dirname, extname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(frontend, 'dist')
const examples = resolve(frontend, '..', 'contracts', 'examples')

function check(condition, message) {
  if (!condition) throw new Error(message)
}

async function filesInside(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const groups = await Promise.all(
    entries.map(async (entry) => {
      check(
        !entry.isSymbolicLink(),
        'Production output must not contain symbolic links.',
      )
      const path = join(directory, entry.name)
      return entry.isDirectory() ? filesInside(path) : [path]
    }),
  )
  return groups.flat()
}

const fixtureNames = new Set()
function collectFixtureNames(value) {
  if (!value || typeof value !== 'object') return
  if (value.is_test === true) {
    for (const key of ['name', 'title']) {
      if (typeof value[key] === 'string') fixtureNames.add(value[key])
    }
  }
  for (const child of Object.values(value)) collectFixtureNames(child)
}

for (const filename of await readdir(examples)) {
  if (filename.endsWith('.json'))
    collectFixtureNames(
      JSON.parse(await readFile(join(examples, filename), 'utf8')),
    )
}

const files = await filesInside(dist)
const html = await readFile(join(dist, 'index.html'), 'utf8')
const scripts = [
  ...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi),
].map((match) => match[1])
check(scripts.length > 0, 'Production index.html has no script asset.')

for (const source of scripts) {
  check(
    source.startsWith('/assets/') &&
      !source.includes('?') &&
      !source.includes('#'),
    'Production script must reference a built local /assets/ file.',
  )
  const asset = resolve(dist, `.${source}`)
  check(
    asset.startsWith(`${dist}${sep}`) && (await stat(asset)).isFile(),
    'Production index.html references a missing or invalid script asset.',
  )
}

const textExtensions = new Set([
  '.js',
  '.css',
  '.html',
  '.json',
  '.txt',
  '.svg',
  '.xml',
  '.webmanifest',
])
const forbidden = [
  [/example\.invalid/i, 'contract fixture source URL'],
  // The fixture marker is deliberately uppercase. The localized UI badge
  // "Synthetic test only" may remain in dictionaries without fixture data.
  [/SYNTHETIC TEST ONLY/, 'contract fixture payload'],
  [
    /\b(?:DATABASE_URL|OPENAI_API_KEY|TWOGIS_API_KEY)\b/,
    'server credential name',
  ],
  [
    /https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\]):8000\b/i,
    'absolute development backend URL',
  ],
  [/sourceMappingURL\s*=/, 'source map reference'],
]

for (const path of files) {
  const name = path.split(/[\\/]/).at(-1)
  check(
    !/^\.env(?:\.|$)/i.test(name),
    'Production output contains an environment file.',
  )
  check(
    !/\.map(?:\.gz|\.br)?$/i.test(name),
    'Production output contains a source map.',
  )
  if (!textExtensions.has(extname(path).toLowerCase())) continue
  const content = await readFile(path, 'utf8')
  for (const [pattern, label] of forbidden)
    check(
      !pattern.test(content),
      `Production output contains a forbidden ${label}.`,
    )
  for (const fixtureName of fixtureNames)
    check(
      !content.includes(fixtureName),
      'Production output contains a contract fixture venue/event name.',
    )
}

console.log(
  `Production build passed: ${files.length} files; local script assets exist; fixture payloads, server credential names, development backend URLs, environment files and source maps are absent.`,
)
