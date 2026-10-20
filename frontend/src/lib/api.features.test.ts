import { describe, expect, it } from 'vitest'
import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import { syntheticFeatureResponse } from '../test/featureEvidence'
import { parseSearchResponse } from './api'

describe('sourced visit condition evidence', () => {
  it('accepts source checks without inventing a physical observation', () => {
    const value = syntheticFeatureResponse()
    const parsed = parseSearchResponse(value, 'recommendations', 'en')
    expect(parsed.items[0].feature_evidence).toEqual(
      value.items[0].feature_evidence,
    )
    expect(parsed.items[0].feature_evidence?.[0].observed_at).toBeNull()
    expect(parsed.items[0].name_is_derived).toBe(true)
  })

  it('accepts older cards with omitted additive fields and applies safe defaults', () => {
    const parsed = parseSearchResponse(recommendation, 'recommendations', 'en')
    expect(parsed.items[0].feature_evidence).toEqual([])
    expect(parsed.items[0].name_is_derived).toBe(false)
    expect(recommendation.items[0]).not.toHaveProperty('feature_evidence')
  })

  it.each([
    ['field', 'wifi'],
    ['value', 'true'],
    ['value', false],
    ['source_id', 'missing-source'],
    ['source_field', 'internet_access'],
    ['source_value', 'yes'],
    ['source_version', 0],
    ['checked_at', null],
    ['checked_at', '2030-01-15T10:00:00'],
    ['checked_at', '2030-02-30T10:00:00+05:00'],
    ['checked_at', '2030-01-16T10:00:00+05:00'],
    ['source_updated_at', '2030-01-16T10:00:00+05:00'],
    ['observed_at', '2030-01-15T10:00:00+05:00'],
  ])('rejects unsupported evidence %s=%s', (key, value) => {
    const response = syntheticFeatureResponse()
    Object.assign(response.items[0].feature_evidence![0], { [key]: value })
    expect(() =>
      parseSearchResponse(response, 'recommendations', 'en'),
    ).toThrow('invalid_response')
  })

  it('rejects missing required check dates rather than inventing them', () => {
    const value = syntheticFeatureResponse()
    delete (
      value.items[0].feature_evidence![0] as Partial<
        NonNullable<(typeof value.items)[0]['feature_evidence']>[number]
      >
    ).checked_at
    expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
      'invalid_response',
    )
  })

  it('rejects duplicate fields and null evidence lists', () => {
    const value = syntheticFeatureResponse()
    value.items[0].feature_evidence!.push(
      structuredClone(value.items[0].feature_evidence![0]),
    )
    expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
      'invalid_response',
    )
    Object.assign(value.items[0], { feature_evidence: null })
    expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
      'invalid_response',
    )
  })

  it('requires the source on the POI even when it is included in the envelope', () => {
    const value = syntheticFeatureResponse()
    const other = { ...value.sources[0], source_id: 'unrelated-source' }
    value.sources.push(other)
    value.items[0].feature_evidence![0].source_id = other.source_id
    expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
      'invalid_response',
    )
  })

  it.each(['storage_allowed', 'indexing_allowed'] as const)(
    'rejects a feature source without %s rights',
    (right) => {
      const value = syntheticFeatureResponse()
      value.items[0].poi.sources[0][right] = false
      value.sources[0][right] = false
      expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
        'invalid_response',
      )
    },
  )

  it.each(['url', 'license', 'rights_basis_url', 'retrieved_at'] as const)(
    'rejects evidence with differing envelope source %s',
    (key) => {
      const value = syntheticFeatureResponse()
      value.sources[0][key] =
        key === 'retrieved_at'
          ? '2030-01-16T10:00:00+05:00'
          : 'https://example.invalid/different'
      expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
        'invalid_response',
      )
    },
  )

  it('rejects credential-bearing feature sources before rendering a link', () => {
    const value = syntheticFeatureResponse()
    const url = 'https://secret:token@example.invalid/source'
    value.sources[0].url = url
    value.items[0].poi.sources[0].url = url
    expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
      'invalid_response',
    )
  })

  it('rejects unsupported source providers even with asserted rights', () => {
    const value = syntheticFeatureResponse()
    value.sources[0].provider = 'organizer'
    value.items[0].poi.sources[0].provider = 'organizer'
    expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
      'invalid_response',
    )
  })

  it.each(['family_playground_match', 'power_outlets_match'] as const)(
    'rejects %s without the matching true fact',
    (reason) => {
      const value = syntheticFeatureResponse()
      value.items[0].feature_evidence = []
      value.items[0].reason_codes = [reason]
      expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
        'invalid_response',
      )
    },
  )

  it.each([
    ['service:electricity', 'yes', true],
    ['service:electricity', 'limited', true],
    ['service:electricity', 'no', false],
    ['power_supply', 'yes', true],
    ['power_supply', 'no', false],
  ] as const)(
    'accepts explicit customer socket mapping %s=%s',
    (source_field, source_value, present) => {
      const value = syntheticFeatureResponse()
      Object.assign(value.items[0].feature_evidence![0], {
        field: 'power_outlets',
        source_field,
        source_value,
        value: present,
      })
      value.items[0].reason_codes = present
        ? ['power_outlets_match']
        : ['query_match']
      expect(() =>
        parseSearchResponse(value, 'recommendations', 'en'),
      ).not.toThrow()
    },
  )

  it.each([
    ['yes', true],
    ['public', true],
    ['no', false],
    ['private', false],
  ] as const)(
    'accepts explicit access=%s without a safety claim',
    (source_value, present) => {
      const value = syntheticFeatureResponse()
      Object.assign(value.items[0].feature_evidence![0], {
        field: 'public_access',
        source_field: 'access',
        source_value,
        value: present,
      })
      value.items[0].reason_codes = ['query_match']
      expect(() =>
        parseSearchResponse(value, 'recommendations', 'en'),
      ).not.toThrow()
    },
  )

  it.each(['electricity', 'socket:type2', 'internet_access'])(
    'does not infer customer outlets from %s',
    (source_field) => {
      const value = syntheticFeatureResponse()
      Object.assign(value.items[0].feature_evidence![0], {
        field: 'power_outlets',
        source_field,
        source_value: 'yes',
      })
      value.items[0].reason_codes = ['power_outlets_match']
      expect(() => parseSearchResponse(value, 'recommendations', 'en')).toThrow(
        'invalid_response',
      )
    },
  )
})
