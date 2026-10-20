import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import type { FeatureEvidence, RecommendationResponse } from '../lib/types'

/** Synthetic only: this helper does not assert facts about an actual venue. */
export function syntheticFeatureResponse(): RecommendationResponse {
  const value = structuredClone(
    recommendation,
  ) as unknown as RecommendationResponse
  value.status = 'partial'
  const card = value.items[0]
  card.fit_status = 'unknown'
  card.missing_fields = ['public_access', 'age_restrictions']
  card.reason_codes = ['family_playground_match']
  card.name_is_derived = true
  const fact: FeatureEvidence = {
    field: 'family_playground',
    value: true,
    source_id: card.poi.primary_source_id,
    source_field: 'leisure',
    source_value: 'playground',
    source_version: 3,
    source_updated_at: '2029-12-01T10:00:00+05:00',
    checked_at: card.poi.sources[0].retrieved_at,
    observed_at: null,
  }
  card.feature_evidence = [fact]
  return value
}
