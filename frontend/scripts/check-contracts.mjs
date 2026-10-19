import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const root = new URL('../../', import.meta.url)
const readJson = async (path) =>
  JSON.parse(await readFile(new URL(path, root), 'utf8'))
const [
  codes,
  request,
  recommendations,
  legacyEvents,
  snapshot,
  events,
  routeRequest,
  routeResponse,
  types,
] = await Promise.all([
  readJson('contracts/codes.json'),
  readJson('contracts/recommendation-request.schema.json'),
  readJson('contracts/recommendation-response.schema.json'),
  readJson('contracts/event-search-response.schema.json'),
  // Keep the older integration only as explicit backwards compatibility.
  readJson('frontend/src/lib/event-search-response.schema.json'),
  readJson('contracts/transient-event-search-response.schema.json'),
  readJson('contracts/route-request.schema.json'),
  readJson('contracts/route-response.schema.json'),
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

// The transient discovery extension must preserve every legacy property and
// definition. Shared contract edits belong to Sabyrzhan, never this checker.
for (const [name, schema] of Object.entries(legacyEvents.$defs))
  check(
    JSON.stringify(snapshot.$defs[name]) === JSON.stringify(schema),
    `Event snapshot changed legacy definition ${name}`,
  )
for (const [name, schema] of Object.entries(legacyEvents.properties))
  check(
    JSON.stringify(snapshot.properties[name]) === JSON.stringify(schema),
    `Event snapshot changed legacy field ${name}`,
  )
sameValues(
  snapshot.required,
  legacyEvents.required,
  'Event legacy required fields',
)

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
sameValues(
  literalValues(aliases.get('RouteFailureReason')),
  routeResponse.$defs.RouteLeg.properties.reason.anyOf[0].enum,
  'RouteFailureReason',
)

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
  ['RouteRequest', routeRequest],
  ['RouteResponse', routeResponse],
  ['RouteLeg', routeResponse.$defs.RouteLeg],
  ['RouteProvenance', routeResponse.$defs.RouteProvenance],
  ['SearchResponse', recommendations],
  ['Coordinates', recommendations.$defs.Coordinates],
  ['Source', recommendations.$defs.Source],
  ['Provenance', recommendations.$defs.Provenance],
  ['POIRecord', recommendations.$defs.POIRecord],
  ['Action', recommendations.$defs.Action],
  ['RecommendationCard', recommendations.$defs.POICard],
  ['EventRecord', snapshot.$defs.EventRecord],
  ['EventSession', snapshot.$defs.EventSession],
  ['EventCardData', snapshot.$defs.EventCard],
  ['LegacyEventSearchResponse', snapshot],
  ['EventEvidenceSource', snapshot.$defs.EventDiscoverySource],
  ['EventCitation', snapshot.$defs.EventDiscoveryCitation],
  ['EventEvidence', snapshot.$defs.EventDiscoveryEvidence],
  ['EventVenue', events.$defs.VenueMatch],
  ['EventFieldCheck', events.$defs.FieldCheck],
  ['DiscoveredSession', events.$defs.NormalizedSession],
  ['DiscoveredEvent', events.$defs.NormalizedEvent],
  ['EventDiscovery', snapshot.$defs.EventDiscoveryPayload],
  ['TransientEventSource', events.$defs.TransientEventSource],
  ['TransientEvent', events.$defs.TransientEvent],
  ['TransientEventCardData', events.$defs.TransientEventCard],
  ['TransientEventSearchResponse', events],
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
  'pattern',
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
for (const schema of [
  request,
  recommendations,
  legacyEvents,
  snapshot,
  events,
  routeRequest,
  routeResponse,
])
  checkKeywords(schema)
console.log(
  `Shared v${codes.contract_version} including transient events: frontend enums, wire fields, legacy compatibility and runtime schema keywords match.`,
)
