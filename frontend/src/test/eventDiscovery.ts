/** Synthetic HTTP/UI facts only. Never imported by the production application. */
import type {
  DiscoveredEvent,
  DiscoveredSession,
  EventSearchResponse,
  EventVenue,
} from '../lib/types'

const observed = '2030-01-01T10:00:00+05:00'
const sourceUrl = 'https://example.invalid/test-only-listing'
const venue: EventVenue = {
  poi_id: null,
  location: null,
  basis: 'unknown',
  source_ids: [],
  source_urls: [],
  coordinate_accuracy: 'unknown',
  geography_basis: 'unknown',
}

export function syntheticSession(): DiscoveredSession {
  return {
    session_id: 'test-session',
    event_id: 'test-event',
    source_url: sourceUrl,
    source_fetched_at: observed,
    city: 'Astana',
    venue_name: 'TEST ONLY venue',
    venue_address: null,
    venue: structuredClone(venue),
    starts_at: '2030-01-02T18:00:00+05:00',
    ends_at: null,
    price_from: 5000,
    currency: 'KZT',
    price_conditions: null,
    price_kind: 'starting',
    status: 'scheduled',
    verification_status: 'discovered',
    verified_fields: [],
    ticket_availability: 'unknown',
    missing_fields: ['ends_at', 'venue_address'],
    recommendation_candidate: true,
    exclusion_reasons: [],
  }
}

export function syntheticListing(): DiscoveredEvent {
  return {
    event_id: 'test-event',
    title: 'TEST ONLY fictional event listing',
    source_url: sourceUrl,
    source_fetched_at: observed,
    city: 'Astana',
    venue_name: 'TEST ONLY venue',
    venue_address: null,
    venue: structuredClone(venue),
    status: 'listing',
    schedule_hints: ['2 January (year not given)'],
    missing_fields: ['sessions', 'venue_address', 'location'],
    sessions: [],
  }
}

export function syntheticDiscoveryResponse(): EventSearchResponse {
  const context = 'TEST ONLY fictional event listing in Astana.'
  return {
    request_id: '00000000-0000-4000-8000-000000000001',
    status: 'partial',
    items: [],
    warnings: [
      {
        code: 'data_unknown',
        message: 'TEST ONLY incomplete listing.',
        fields: [],
      },
    ],
    sources: [],
    discovery: {
      provider_status: 'partial',
      provider_code: null,
      live_web_search: 'passed',
      excluded_sessions: 0,
      rejected_events: 0,
      events: [syntheticListing()],
      evidence: {
        text: context,
        sources: [
          {
            url: sourceUrl,
            fetched_at: observed,
            storage_allowed: false,
            indexing_allowed: false,
          },
        ],
        citations: [
          {
            url: sourceUrl,
            title: 'TEST ONLY citation',
            start_index: 0,
            end_index: context.length,
            text: context,
            context,
          },
        ],
      },
    },
  }
}
