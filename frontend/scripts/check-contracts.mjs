import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const root = new URL('../../', import.meta.url)
const readJson = async (path) =>
  JSON.parse(await readFile(new URL(path, root), 'utf8'))
const [
  codes,
  request,
  recommendations,
  legacyPersistentEvents,
  legacyDiscoverySnapshot,
  transientEvents,
  routeRequest,
  routeResponse,
  types,
] = await Promise.all([
  readJson('contracts/codes.json'),
  readJson('contracts/recommendation-request.schema.json'),
  readJson('contracts/recommendation-response.schema.json'),
  readJson('contracts/event-search-response.schema.json'),
  // Compatibility only: pre-S04 envelopes and synthetic development fixtures.
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

// The old frontend snapshot preserves the legacy persistent-event envelope.
// This compatibility check says nothing about the current S04 transient wire.
for (const [name, schema] of Object.entries(legacyPersistentEvents.$defs))
  check(
    JSON.stringify(legacyDiscoverySnapshot.$defs[name]) ===
      JSON.stringify(schema),
    `Legacy event snapshot changed persistent definition ${name}`,
  )
for (const [name, schema] of Object.entries(legacyPersistentEvents.properties))
  check(
    JSON.stringify(legacyDiscoverySnapshot.properties[name]) ===
      JSON.stringify(schema),
    `Legacy event snapshot changed persistent field ${name}`,
  )
sameValues(
  legacyDiscoverySnapshot.required,
  legacyPersistentEvents.required,
  'Legacy event required fields',
)

const unions = {
  Locale: 'locale',
  ResponseStatus: 'response_status',
  RouteStatus: 'route_status',
  FitStatus: 'fit_status',
  ActivityCode: 'activity_code',
  ReasonCode: 'reason_codes',
  FeatureField: 'feature_fields',
  WarningCode: 'warning_codes',
  ConstraintField: 'explicit_fields',
  ClarificationReason: 'clarification_reasons',
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
  ['FeatureEvidence', recommendations.$defs.FeatureEvidence],
  ['TransientEventSource', transientEvents.$defs.TransientEventSource],
  ['TransientEventHeader', transientEvents.$defs.TransientEvent],
  ['TransientEventCardData', transientEvents.$defs.TransientEventCard],
  ['TransientEventSearchResponse', transientEvents],
  ['EventVenue', transientEvents.$defs.VenueMatch],
  ['EventFieldCheck', transientEvents.$defs.FieldCheck],
  ['DiscoveredSession', transientEvents.$defs.NormalizedSession],
  ['DiscoveredEvent', transientEvents.$defs.NormalizedEvent],
  ['SearchWarning', recommendations.$defs.Warning],
  ['ConstraintClarification', recommendations.$defs.ConstraintClarification],
]
for (const [name, schema] of interfaces)
  sameValues(
    interfaceFields(name),
    Object.keys(schema.properties),
    `${name} fields`,
  )

// Legacy interfaces support old envelopes and development fixtures only.
// EventSearchResponse is an internal UI shape after adaptation, not a wire type.
const legacyInterfaces = [
  ['EventRecord', legacyPersistentEvents.$defs.EventRecord],
  ['EventSession', legacyPersistentEvents.$defs.EventSession],
  ['EventCardData', legacyPersistentEvents.$defs.EventCard],
  ['EventEvidenceSource', legacyDiscoverySnapshot.$defs.EventDiscoverySource],
  ['EventCitation', legacyDiscoverySnapshot.$defs.EventDiscoveryCitation],
  ['EventEvidence', legacyDiscoverySnapshot.$defs.EventDiscoveryEvidence],
  ['EventDiscovery', legacyDiscoverySnapshot.$defs.EventDiscoveryPayload],
]
for (const [name, schema] of legacyInterfaces)
  sameValues(
    interfaceFields(name),
    Object.keys(schema.properties),
    `Legacy ${name} fields`,
  )

for (const locale of codes.locale) {
  const translations = await readJson(
    `frontend/src/locales/${locale}/common.json`,
  )
  const clarifications = translations.constraintClarifications
  check(
    clarifications,
    `${locale}: missing constraint clarification translations`,
  )
  sameValues(
    Object.keys(clarifications),
    [...codes.clarification_reasons, 'resubmit'],
    `${locale} clarification translation groups`,
  )
  for (const reason of codes.clarification_reasons) {
    sameValues(
      Object.keys(clarifications[reason]),
      codes.explicit_fields,
      `${locale} ${reason} translation fields`,
    )
    for (const field of codes.explicit_fields)
      check(
        typeof clarifications[reason][field] === 'string' &&
          clarifications[reason][field].trim().length > 0,
        `${locale}: empty clarification translation for ${reason}.${field}`,
      )
  }
  check(
    typeof clarifications.resubmit === 'string' &&
      clarifications.resubmit.trim().length > 0,
    `${locale}: missing clarification resubmit guidance`,
  )
}

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
function checkKeywords(schema, label) {
  for (const key of Object.keys(schema))
    check(
      supported.has(key),
      `${label}: unsupported runtime schema keyword ${key}`,
    )
  for (const child of Object.values(schema.$defs ?? {}))
    checkKeywords(child, label)
  for (const child of Object.values(schema.properties ?? {}))
    checkKeywords(child, label)
  for (const child of schema.anyOf ?? []) checkKeywords(child, label)
  if (schema.items) checkKeywords(schema.items, label)
}
for (const schema of [
  request,
  recommendations,
  transientEvents,
  routeRequest,
  routeResponse,
])
  checkKeywords(schema, 'Shared contract')
for (const schema of [legacyPersistentEvents, legacyDiscoverySnapshot])
  checkKeywords(schema, 'Legacy event compatibility')
console.log(
  `Shared v${codes.contract_version}: frontend wire enums, field names and runtime schema keywords match. Legacy event snapshot compatibility checked separately.`,
)
