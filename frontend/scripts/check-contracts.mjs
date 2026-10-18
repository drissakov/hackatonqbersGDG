import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const root = new URL('../../', import.meta.url)
const readJson = async (path) =>
  JSON.parse(await readFile(new URL(path, root), 'utf8'))
const [codes, request, recommendations, events, types] = await Promise.all([
  readJson('contracts/codes.json'),
  readJson('contracts/recommendation-request.schema.json'),
  readJson('contracts/recommendation-response.schema.json'),
  readJson('contracts/event-search-response.schema.json'),
  readFile(new URL('frontend/src/lib/types.ts', root), 'utf8'),
])
const source = ts.createSourceFile(
  'types.ts',
  types,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TS,
)
const aliases = new Map(
  source.statements
    .filter(ts.isTypeAliasDeclaration)
    .map((statement) => [statement.name.text, statement.type]),
)
const declarations = new Map(
  source.statements
    .filter(ts.isInterfaceDeclaration)
    .map((statement) => [statement.name.text, statement]),
)

function check(condition, message) {
  if (!condition) throw new Error(message)
}

function sameValues(actual, expected, label) {
  check(
    actual.length === expected.length &&
      actual.every((value) => expected.includes(value)),
    `${label} drifted from contract v${codes.contract_version}`,
  )
}

const unions = {
  Locale: 'locale',
  ResponseStatus: 'response_status',
  RouteStatus: 'route_status',
  FitStatus: 'fit_status',
  ActivityCode: 'activity_code',
  ReasonCode: 'reason_codes',
  WarningCode: 'warning_codes',
  ConstraintField: 'explicit_fields',
  MissingField: 'missing_fields',
  SourceProvider: 'source_provider',
}
for (const [name, key] of Object.entries(unions)) {
  const type = aliases.get(name)
  check(type, `Missing TypeScript union ${name}`)
  sameValues(literalValues(type), codes[key], name)
}

function literalValues(type) {
  if (ts.isParenthesizedTypeNode(type)) return literalValues(type.type)
  if (ts.isUnionTypeNode(type)) return type.types.flatMap(literalValues)
  check(
    ts.isLiteralTypeNode(type) && ts.isStringLiteral(type.literal),
    'Contract codes must use TypeScript string literal unions.',
  )
  return [type.literal.text]
}

function interfaceFields(name) {
  const declaration = declarations.get(name)
  check(declaration, `Missing TypeScript interface ${name}`)
  const own = declaration.members.map((member) => {
    check(
      ts.isPropertySignature(member) &&
        (ts.isIdentifier(member.name) || ts.isStringLiteral(member.name)),
      `Unsupported contract interface member in ${name}`,
    )
    return member.name.text
  })
  const inherited = (declaration.heritageClauses ?? []).flatMap((clause) =>
    clause.types.flatMap((base) =>
      interfaceFields(base.expression.getText(source)),
    ),
  )
  return [...inherited, ...own]
}

const interfaces = [
  ['SearchRequest', request],
  ['SearchResponse', recommendations],
  ['Coordinates', recommendations.$defs.Coordinates],
  ['Source', recommendations.$defs.Source],
  ['Provenance', recommendations.$defs.Provenance],
  ['POIRecord', recommendations.$defs.POIRecord],
  ['Action', recommendations.$defs.Action],
  ['RecommendationCard', recommendations.$defs.POICard],
  ['EventRecord', events.$defs.EventRecord],
  ['EventSession', events.$defs.EventSession],
  ['EventCardData', events.$defs.EventCard],
  ['SearchWarning', recommendations.$defs.Warning],
]
for (const [name, schema] of interfaces)
  sameValues(
    interfaceFields(name),
    Object.keys(schema.properties),
    `${name} fields`,
  )

// The runtime evaluator intentionally implements only the project's current
// generated keyword set. Fail here if a contract introduces a new constraint.
const supported = new Set([
  '$schema',
  '$defs',
  '$ref',
  'title',
  'description',
  'default',
  'type',
  'anyOf',
  'enum',
  'const',
  'properties',
  'required',
  'additionalProperties',
  'items',
  'minItems',
  'maxItems',
  'minLength',
  'maxLength',
  'minimum',
  'maximum',
  'exclusiveMinimum',
  'format',
])
function checkKeywords(schema) {
  for (const key of Object.keys(schema))
    check(supported.has(key), `Unsupported runtime schema keyword: ${key}`)
  for (const child of Object.values(schema.$defs ?? {})) checkKeywords(child)
  for (const child of Object.values(schema.properties ?? {}))
    checkKeywords(child)
  for (const child of schema.anyOf ?? []) checkKeywords(child)
  if (schema.items) checkKeywords(schema.items)
}
for (const schema of [request, recommendations, events]) checkKeywords(schema)
console.log(
  `Contract v${codes.contract_version}: frontend enums, field names and runtime schema keywords match.`,
)
