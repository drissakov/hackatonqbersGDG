import { ApiError, parseSearchResponse } from '../lib/api'
import type {
  EventSearchResponse,
  RecommendationResponse,
  ResponseStatus,
} from '../lib/types'

export function loadFixture(
  kind: 'recommendations',
  status: ResponseStatus,
): Promise<RecommendationResponse>
export function loadFixture(
  kind: 'events',
  status?: ResponseStatus,
): Promise<EventSearchResponse>
export async function loadFixture(
  kind: 'recommendations' | 'events',
  status: ResponseStatus = 'partial',
): Promise<RecommendationResponse | EventSearchResponse> {
  if (!import.meta.env.DEV) throw new ApiError('not_ready')
  if (kind === 'events') {
    const fixture =
      await import('../../../contracts/examples/event-search-response.test.json')
    return parseSearchResponse(fixture.default, 'events', 'en')
  }
  const loaders = {
    ok: () => import('../../../contracts/examples/recommendation-ok.test.json'),
    partial: () =>
      import('../../../contracts/examples/recommendation-partial.test.json'),
    unknown: () =>
      import('../../../contracts/examples/recommendation-unknown.test.json'),
    unavailable: () =>
      import('../../../contracts/examples/recommendation-unavailable.test.json'),
    no_match: () =>
      import('../../../contracts/examples/recommendation-no_match.test.json'),
  }
  const fixture = await loaders[status]()
  return parseSearchResponse(fixture.default, 'recommendations', 'en')
}
