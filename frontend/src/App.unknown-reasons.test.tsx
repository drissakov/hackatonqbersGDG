import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import transientUnknown from '../../contracts/examples/transient-event-unknown.test.json'
import type { Locale, MissingField, SearchRequest } from './lib/types'

const privateMessage =
  'TEST ONLY untrusted backend warning prose; never show or parse this message.'
const languageNames = { kk: 'Қазақша', ru: 'Русский', en: 'English' }
const reasonFields = [
  'child_suitability',
  'age_restrictions',
  'power_outlets',
] as const satisfies readonly MissingField[]
type ReasonField = (typeof reasonFields)[number]
type SearchKind = 'recommendations' | 'events'

const reasons: Record<Locale, Record<ReasonField, string>> = {
  en: {
    child_suitability:
      'We cannot confirm whether this place or event is suitable for children.',
    age_restrictions: 'We do not have confirmed age restrictions.',
    power_outlets:
      'We cannot confirm that power outlets or device charging are available.',
  },
  ru: {
    child_suitability:
      'Не можем подтвердить, подходит ли это место или событие для детей.',
    age_restrictions: 'Нет подтверждённых данных о возрастных ограничениях.',
    power_outlets:
      'Не можем подтвердить наличие розеток или возможности зарядить устройство.',
  },
  kk: {
    child_suitability:
      'Бұл орынның немесе іс-шараның балаларға жарамдылығы расталмаған.',
    age_restrictions: 'Жас шектеулері туралы расталған деректер жоқ.',
    power_outlets:
      'Розеткалардың немесе құрылғыны қуаттау мүмкіндігінің бар-жоғы расталмаған.',
  },
}

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    headers: { 'content-type': 'application/json' },
  })
}

async function search(kind: SearchKind, fields?: MissingField[]) {
  const posts: { path: string; body: SearchRequest }[] = []
  const fetch = vi.fn<typeof globalThis.fetch>(async (url, options) => {
    if (url === '/api/health') return json({ status: 'ok' })
    expect(options?.method).toBe('POST')
    expect(url).toBe(
      kind === 'events' ? '/api/events/search' : '/api/recommendations',
    )
    const body = JSON.parse(String(options?.body)) as SearchRequest
    posts.push({ path: String(url), body })
    const response =
      kind === 'events'
        ? structuredClone(transientUnknown)
        : { status: 'unknown', items: [], sources: [] }
    return json({
      ...response,
      request_id: body.request_id,
      warnings: [
        {
          code: 'missing_input',
          message: privateMessage,
          ...(fields === undefined ? {} : { fields }),
        },
      ],
    })
  })
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<App />)
  if (kind === 'events')
    await user.click(
      screen.getByRole('button', { name: i18n.t('states.events') }),
    )
  await user.type(
    screen.getByRole('textbox', { name: i18n.t('search.query') }),
    'TEST ONLY synthetic family activity with device charging',
  )
  await user.click(
    screen.getByRole('button', {
      name: i18n.t(kind === 'events' ? 'search.submitEvents' : 'search.submit'),
    }),
  )
  expect(
    await screen.findByText(i18n.t('codes.response_status.unknown'), {
      selector: 'strong',
    }),
  ).toBeVisible()
  return { user, posts, fetch }
}

function assertReasons(fields: readonly ReasonField[], locale: Locale) {
  for (const field of reasonFields) {
    if (fields.includes(field))
      expect(
        screen.getByText(reasons[locale][field], { exact: false }),
      ).toBeVisible()
    else
      expect(
        screen.queryByText(reasons[locale][field], { exact: false }),
      ).not.toBeInTheDocument()
  }
  if (fields.length > 0)
    expect(
      screen.getAllByText(
        i18n.t('unknownReasons.checkWithVenue', { lng: locale }),
        {
          exact: false,
        },
      ),
    ).not.toHaveLength(0)
  expect(document.body).not.toHaveTextContent(privateMessage)
}

beforeEach(async () => {
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  await act(() => i18n.changeLanguage('en'))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('specific unknown constraint reasons through the complete HTTP flow', () => {
  it.each(reasonFields)(
    'translates the %s reason locally without repeating a place search',
    async (field) => {
      const { user, posts, fetch } = await search('recommendations', [field])
      assertReasons([field], 'en')
      const receivedCalls = fetch.mock.calls.length
      for (const locale of ['ru', 'kk', 'en'] as const) {
        await user.click(
          screen.getByRole('button', { name: languageNames[locale] }),
        )
        assertReasons([field], locale)
        for (const otherLocale of (['kk', 'ru', 'en'] as const).filter(
          (value) => value !== locale,
        ))
          expect(
            screen.queryByText(reasons[otherLocale][field], { exact: false }),
          ).not.toBeInTheDocument()
        expect(posts).toHaveLength(1)
        expect(fetch).toHaveBeenCalledTimes(receivedCalls)
      }
      expect(posts[0].body.locale).toBe('en')
    },
  )

  it.each(['recommendations', 'events'] as const)(
    'keeps all combined reasons in %s responses when the language changes',
    async (kind) => {
      const { user, posts, fetch } = await search(kind, [...reasonFields])
      assertReasons(reasonFields, 'en')
      const receivedCalls = fetch.mock.calls.length
      for (const locale of ['ru', 'kk', 'en'] as const) {
        await user.click(
          screen.getByRole('button', { name: languageNames[locale] }),
        )
        assertReasons(reasonFields, locale)
        expect(posts).toHaveLength(1)
        expect(fetch).toHaveBeenCalledTimes(receivedCalls)
      }
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    },
  )

  it.each([
    { kind: 'recommendations', fields: [] },
    { kind: 'recommendations', fields: undefined },
    { kind: 'events', fields: [] },
    { kind: 'events', fields: undefined },
  ] satisfies { kind: SearchKind; fields: MissingField[] | undefined }[])(
    'retains a safe generic fallback for an older $kind warning with fields=$fields',
    async ({ kind, fields }) => {
      const { user, posts, fetch } = await search(kind, fields)
      expect(
        screen.getByText(i18n.t('codes.warning_codes.missing_input')),
      ).toBeVisible()
      assertReasons([], 'en')
      const receivedCalls = fetch.mock.calls.length
      for (const locale of ['ru', 'kk', 'en'] as const) {
        await user.click(
          screen.getByRole('button', { name: languageNames[locale] }),
        )
        expect(
          screen.getByText(
            i18n.t('codes.warning_codes.missing_input', { lng: locale }),
          ),
        ).toBeVisible()
        assertReasons([], locale)
        expect(posts).toHaveLength(1)
        expect(fetch).toHaveBeenCalledTimes(receivedCalls)
      }
    },
  )
})
