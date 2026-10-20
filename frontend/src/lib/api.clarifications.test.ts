import { describe, expect, it } from 'vitest'
import transientUnknown from '../../../contracts/examples/transient-event-unknown.test.json'
import routeUnknown from '../../../contracts/examples/route-response.test.json'
import { ApiError, parseRouteResponse, parseSearchResponse } from './api'
import type { ConstraintClarification } from './types'

const fields = [
  'origin',
  'available_minutes',
  'return_to_start',
  'budget_kzt_per_person',
  'indoor_only',
  'date_time',
] as const
const conflicts: ConstraintClarification[] = fields.map((field) => ({
  field,
  reason: 'conflicting_constraints',
}))
const numeric: ConstraintClarification[] = [
  { field: 'available_minutes', reason: 'unparsed_constraint' },
  { field: 'budget_kzt_per_person', reason: 'unparsed_constraint' },
]

type Envelope = 'recommendations' | 'events' | 'legacy-events' | 'route'

function response(kind: Envelope, clarifications?: unknown) {
  const common = {
    request_id: transientUnknown.request_id,
    status: 'unknown',
    items: [],
    sources: [],
  }
  const warning = {
    code: 'missing_input',
    message: 'TEST ONLY private warning prose, not a translation source.',
    fields: [],
    ...(clarifications === undefined ? {} : { clarifications }),
  }
  return {
    ...(kind === 'route'
      ? structuredClone(routeUnknown)
      : kind === 'events'
        ? structuredClone(transientUnknown)
        : common),
    warnings: [warning],
  }
}

function parse(value: unknown, kind: Envelope) {
  return kind === 'route'
    ? parseRouteResponse(value)
    : kind === 'recommendations'
      ? parseSearchResponse(value, 'recommendations', 'en')
      : parseSearchResponse(value, 'events', 'en')
}

describe.each(['recommendations', 'events', 'legacy-events', 'route'] as const)(
  'structured clarification boundary: %s',
  (kind) => {
    it.each([{ clarifications: conflicts }, { clarifications: numeric }])(
      'preserves supported metadata without changing the received response',
      ({ clarifications }) => {
        const value = response(kind, clarifications)
        const before = structuredClone(value)
        const result = parse(value, kind)
        expect(result.warnings[0].clarifications).toEqual(clarifications)
        expect(value).toEqual(before)
        expect(result.warnings[0]).not.toBe(value.warnings[0])
      },
    )

    it('normalizes an omitted list to an empty array without mutating the wire', () => {
      const value = response(kind)
      const before = structuredClone(value)
      expect(value.warnings[0]).not.toHaveProperty('clarifications')
      expect(parse(value, kind).warnings[0].clarifications).toEqual([])
      expect(value).toEqual(before)
      expect(value.warnings[0]).not.toHaveProperty('clarifications')
    })

    it.each([
      ['null list', null],
      ['object instead of list', {}],
      ['string instead of list', 'available_minutes'],
      ['null item', [null]],
      ['nested list', [[]]],
      [
        'unknown field',
        [{ field: 'child_suitability', reason: 'conflicting_constraints' }],
      ],
      ['unknown reason', [{ field: 'origin', reason: 'missing_origin' }]],
      ['missing field', [{ reason: 'conflicting_constraints' }]],
      ['missing reason', [{ field: 'origin' }]],
      ['null field', [{ field: null, reason: 'conflicting_constraints' }]],
      ['null reason', [{ field: 'origin', reason: null }]],
      ['numeric field', [{ field: 0, reason: 'conflicting_constraints' }]],
      ['numeric reason', [{ field: 'origin', reason: 1 }]],
      [
        'private value attached',
        [
          {
            field: 'origin',
            reason: 'conflicting_constraints',
            value: '51.128, 71.43',
          },
        ],
      ],
      [
        'query attached',
        [
          {
            field: 'origin',
            reason: 'conflicting_constraints',
            query: 'TEST ONLY private query',
          },
        ],
      ],
      ['too many items', [...conflicts, conflicts[0]]],
    ])('rejects malformed metadata: %s', (_label, clarifications) => {
      expect(() => parse(response(kind, clarifications), kind)).toThrow(
        ApiError,
      )
    })
  },
)
