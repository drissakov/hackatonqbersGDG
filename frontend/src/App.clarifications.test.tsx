import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import transientUnknown from '../../contracts/examples/transient-event-unknown.test.json'
import type {
  ConstraintClarification,
  Locale,
  MissingField,
  SearchRequest,
} from './lib/types'

type SearchKind = 'recommendations' | 'events'
const languageNames = { kk: 'Қазақша', ru: 'Русский', en: 'English' }
const privateQuery = 'TEST ONLY synthetic preference that must stay unchanged'
const privateMessage =
  'TEST ONLY backend prose containing private query and coordinates 51.128, 71.43'
const budgetMessages = {
  en: {
    conflicting_constraints:
      'The budget is ambiguous or conflicting. Enter one amount per person in tenge and make it consistent with your query.',
    unparsed_constraint:
      'We could not read the budget from your query. Enter a whole, non-negative amount in tenge in “Budget per person”, then clarify your query.',
  },
  ru: {
    conflicting_constraints:
      'Бюджет указан неоднозначно или противоречиво. Укажите одну сумму на человека в тенге и согласуйте её с текстом запроса.',
    unparsed_constraint:
      'Не удалось распознать бюджет в тексте. Введите целую неотрицательную сумму в тенге в поле «Бюджет на человека» и уточните текст запроса.',
  },
  kk: {
    conflicting_constraints:
      'Бюджет екіұшты немесе қайшы көрсетілген. Бір адамға арналған бір соманы теңгемен енгізіп, оны сұрау мәтінімен сәйкестендіріңіз.',
    unparsed_constraint:
      'Сұрау мәтінінен бюджетті анықтай алмадық. «Бір адамға бюджет» өрісіне теңгемен теріс емес бүтін соманы енгізіңіз, содан кейін сұрау мәтінін нақтылаңыз.',
  },
}
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
const unparsed: ConstraintClarification[] = [
  { field: 'available_minutes', reason: 'unparsed_constraint' },
  { field: 'budget_kzt_per_person', reason: 'unparsed_constraint' },
]
const unknownFields = [
  'child_suitability',
  'age_restrictions',
  'power_outlets',
] as const satisfies readonly MissingField[]

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    headers: { 'content-type': 'application/json' },
  })
}

function clarificationPayload(
  kind: SearchKind,
  body: SearchRequest,
  clarifications?: ConstraintClarification[],
  missingFields: readonly MissingField[] = [],
) {
  return {
    ...(kind === 'events'
      ? structuredClone(transientUnknown)
      : { status: 'unknown', items: [], sources: [] }),
    request_id: body.request_id,
    warnings: [
      {
        code: 'missing_input',
        message: privateMessage,
        fields: missingFields,
        ...(clarifications === undefined ? {} : { clarifications }),
      },
    ],
  }
}

async function search(
  kind: SearchKind,
  clarifications?: ConstraintClarification[],
  missingFields: readonly MissingField[] = [],
  onPost?: (
    body: SearchRequest,
    attempt: number,
  ) => Response | Promise<Response> | undefined,
) {
  const posts: SearchRequest[] = []
  const fetch = vi.fn<typeof globalThis.fetch>(async (url, options) => {
    if (url === '/api/health') return json({ status: 'ok' })
    expect(options?.method).toBe('POST')
    expect(url).toBe(
      kind === 'events' ? '/api/events/search' : '/api/recommendations',
    )
    const body = JSON.parse(String(options?.body)) as SearchRequest
    posts.push(body)
    return (
      onPost?.(body, posts.length) ??
      json(clarificationPayload(kind, body, clarifications, missingFields))
    )
  })
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<App />)
  if (kind === 'events')
    await user.click(
      screen.getByRole('button', { name: i18n.t('states.events') }),
    )
  const query = screen.getByRole('textbox', { name: i18n.t('search.query') })
  const latitude = screen.getByRole('spinbutton', {
    name: i18n.t('location.latitude'),
  })
  const longitude = screen.getByRole('spinbutton', {
    name: i18n.t('location.longitude'),
  })
  const minutes = screen.getByRole('spinbutton', {
    name: i18n.t('search.minutes'),
  })
  const budget = screen.getByRole('spinbutton', {
    name: i18n.t('search.budget'),
  })
  const returnToStart = screen.getByRole('checkbox', {
    name: i18n.t('search.returnToStart'),
  })
  const indoor = screen.getByRole('checkbox', { name: i18n.t('search.indoor') })
  const dateTime = screen.getByLabelText(i18n.t('search.dateTime'))
  await user.type(query, privateQuery)
  fireEvent.change(latitude, { target: { value: '51.128' } })
  fireEvent.change(longitude, { target: { value: '71.43' } })
  fireEvent.change(minutes, { target: { value: '60' } })
  fireEvent.change(budget, { target: { value: '0' } })
  fireEvent.change(dateTime, { target: { value: '2030-01-15T12:00' } })
  for (const checkbox of [returnToStart, indoor]) {
    await user.click(checkbox)
    await user.click(checkbox)
  }
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

  function assertFormUnchanged() {
    expect(query).toHaveValue(privateQuery)
    expect(latitude).toHaveValue(51.128)
    expect(longitude).toHaveValue(71.43)
    expect(minutes).toHaveValue(60)
    expect(budget).toHaveValue(0)
    expect(dateTime).toHaveValue('2030-01-15T12:00')
    expect(returnToStart).not.toBeChecked()
    expect(indoor).not.toBeChecked()
    expect(posts).toHaveLength(1)
    expect(posts[0]).toMatchObject({
      query: privateQuery,
      origin: { latitude: 51.128, longitude: 71.43 },
      available_minutes: 60,
      budget_kzt_per_person: 0,
      date_time: '2030-01-15T07:00:00.000Z',
      return_to_start: false,
      indoor_only: false,
      explicit_fields: expect.arrayContaining([...fields]),
    })
  }
  assertFormUnchanged()
  return { user, posts, fetch, assertFormUnchanged }
}

function assertClarifications(
  clarifications: ConstraintClarification[],
  locale: Locale,
) {
  const warningList = screen
    .getByText(i18n.t('codes.warning_codes.missing_input', { lng: locale }))
    .closest('ul')!
  for (const { field, reason } of clarifications) {
    const key = `constraintClarifications.${reason}.${field}`
    const translated = i18n.t(key, { lng: locale })
    expect(translated).not.toBe(key)
    expect(within(warningList).getByText(translated)).toBeVisible()
    if (field === 'budget_kzt_per_person')
      expect(
        within(warningList).getByText(budgetMessages[locale][reason]),
      ).toBeVisible()
    for (const otherLocale of (['en', 'kk', 'ru'] as const).filter(
      (other) => other !== locale,
    ))
      expect(
        within(warningList).queryByText(i18n.t(key, { lng: otherLocale })),
      ).not.toBeInTheDocument()
  }
  expect(warningList).not.toHaveTextContent(privateMessage)
  expect(warningList).not.toHaveTextContent(privateQuery)
  expect(warningList).not.toHaveTextContent('51.128')
  expect(warningList).not.toHaveTextContent('71.43')
  if (clarifications.length > 0)
    expect(
      screen.getByText(
        i18n.t('constraintClarifications.resubmit', { lng: locale }),
      ),
    ).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
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

describe.each(['recommendations', 'events'] as const)(
  'actionable constraint clarifications through the %s HTTP flow',
  (kind) => {
    it.each([
      { reason: 'conflicting constraints', clarifications: conflicts },
      { reason: 'unparsed numeric constraints', clarifications: unparsed },
    ])(
      'translates $reason without a search or automatic form changes',
      async ({ clarifications }) => {
        const { user, fetch, assertFormUnchanged } = await search(
          kind,
          clarifications,
        )
        const receivedCalls = fetch.mock.calls.length
        assertClarifications(clarifications, 'en')
        for (const locale of ['ru', 'kk', 'en'] as const) {
          await user.click(
            screen.getByRole('button', { name: languageNames[locale] }),
          )
          assertClarifications(clarifications, locale)
          assertFormUnchanged()
          expect(fetch).toHaveBeenCalledTimes(receivedCalls)
        }
      },
    )

    it.each([
      { label: 'omitted', clarifications: undefined },
      { label: 'empty', clarifications: [] },
    ])(
      'keeps a safe generic warning for an older $label list',
      async ({ clarifications }) => {
        const { user, fetch, assertFormUnchanged } = await search(
          kind,
          clarifications,
        )
        const receivedCalls = fetch.mock.calls.length
        for (const locale of ['en', 'ru', 'kk'] as const) {
          if (locale !== 'en')
            await user.click(
              screen.getByRole('button', { name: languageNames[locale] }),
            )
          expect(
            screen.getByText(
              i18n.t('codes.warning_codes.missing_input', { lng: locale }),
            ),
          ).toBeVisible()
          expect(
            screen.queryByText(
              i18n.t('constraintClarifications.resubmit', { lng: locale }),
            ),
          ).not.toBeInTheDocument()
          assertClarifications([], locale)
          assertFormUnchanged()
          expect(fetch).toHaveBeenCalledTimes(receivedCalls)
        }
      },
    )

    it('retains child, age and charging uncertainty alongside actionable clarifications', async () => {
      const clarifications = [conflicts[1], unparsed[1]]
      const { user, fetch } = await search(kind, clarifications, unknownFields)
      const receivedCalls = fetch.mock.calls.length
      for (const locale of ['en', 'ru', 'kk'] as const) {
        if (locale !== 'en')
          await user.click(
            screen.getByRole('button', { name: languageNames[locale] }),
          )
        assertClarifications(clarifications, locale)
        for (const field of unknownFields)
          expect(
            screen.getByText(
              i18n.t(`unknownReasons.${field}`, { lng: locale }),
            ),
          ).toBeVisible()
        expect(
          screen.getByText(
            i18n.t('unknownReasons.checkWithVenue', { lng: locale }),
          ),
        ).toBeVisible()
        expect(fetch).toHaveBeenCalledTimes(receivedCalls)
      }
    })
  },
)

describe.each(['recommendations', 'events'] as const)(
  'editing constraint corrections for %s',
  (kind) => {
    const initial = [conflicts[1], unparsed[1]]
    const replacement = [conflicts[5]]
    const hint = (
      clarification: ConstraintClarification,
      locale: Locale = 'en',
    ) =>
      i18n.t(
        `constraintClarifications.${clarification.reason}.${clarification.field}`,
        { lng: locale },
      )

    it('retains previous-search corrections through edits and language changes, then replaces and clears them on submission', async () => {
      let finish!: (response: Response) => void
      const { user, posts, fetch } = await search(
        kind,
        initial,
        unknownFields,
        (body, attempt) => {
          if (attempt === 2)
            return new Promise((resolve) => {
              finish = resolve
            })
          if (attempt === 3) return json(clarificationPayload(kind, body, []))
        },
      )
      const calls = fetch.mock.calls.length
      const query = screen.getByRole('textbox', {
        name: i18n.t('search.query'),
      })
      const minutes = screen.getByRole('spinbutton', {
        name: i18n.t('search.minutes'),
      })
      const budget = screen.getByRole('spinbutton', {
        name: i18n.t('search.budget'),
      })
      fireEvent.change(minutes, { target: { value: '90' } })
      fireEvent.change(budget, { target: { value: '5000' } })
      const editedQuery = `${privateQuery} clarified`
      fireEvent.change(query, { target: { value: editedQuery } })

      for (const locale of ['en', 'ru', 'kk', 'en'] as const) {
        await user.click(
          screen.getByRole('button', { name: languageNames[locale] }),
        )
        expect(
          screen.getByText(
            i18n.t('states.previousClarifications', { lng: locale }),
          ),
        ).toBeVisible()
        for (const clarification of initial)
          expect(screen.getByText(hint(clarification, locale))).toBeVisible()
        expect(
          screen.getByText(
            i18n.t('constraintClarifications.resubmit', { lng: locale }),
          ),
        ).toBeVisible()
        expect(query).toHaveValue(editedQuery)
        expect(minutes).toHaveValue(90)
        expect(budget).toHaveValue(5000)
        expect(fetch).toHaveBeenCalledTimes(calls)
      }
      for (const field of unknownFields)
        expect(
          screen.queryByText(i18n.t(`unknownReasons.${field}`)),
        ).not.toBeInTheDocument()
      expect(document.body).not.toHaveTextContent(privateMessage)
      expect(screen.queryByRole('article')).not.toBeInTheDocument()
      expect(
        screen.queryByRole('region', { name: i18n.t('map.title') }),
      ).not.toBeInTheDocument()

      const submitName = i18n.t(
        kind === 'events' ? 'search.submitEvents' : 'search.submit',
      )
      await user.click(screen.getByRole('button', { name: submitName }))
      expect(posts).toHaveLength(2)
      expect(posts[1]).toMatchObject({
        query: editedQuery,
        available_minutes: 90,
        budget_kzt_per_person: 5000,
      })
      expect(posts[1].request_id).not.toBe(posts[0].request_id)
      for (const clarification of initial)
        expect(screen.queryByText(hint(clarification))).not.toBeInTheDocument()
      expect(
        screen.queryByText(i18n.t('states.previousClarifications')),
      ).not.toBeInTheDocument()

      await act(async () =>
        finish(json(clarificationPayload(kind, posts[1], replacement))),
      )
      expect(await screen.findByText(hint(replacement[0]))).toBeVisible()
      for (const clarification of initial)
        expect(screen.queryByText(hint(clarification))).not.toBeInTheDocument()
      fireEvent.change(screen.getByLabelText(i18n.t('search.dateTime')), {
        target: { value: '2030-01-15T13:00' },
      })
      expect(
        screen.getByText(i18n.t('states.previousClarifications')),
      ).toBeVisible()
      expect(screen.getByText(hint(replacement[0]))).toBeVisible()
      await user.click(screen.getByRole('button', { name: submitName }))
      expect(posts).toHaveLength(3)
      expect(posts[2].date_time).toBe('2030-01-15T08:00:00.000Z')
      expect(screen.queryByText(hint(replacement[0]))).not.toBeInTheDocument()
      expect(
        screen.queryByText(i18n.t('states.previousClarifications')),
      ).not.toBeInTheDocument()
      fireEvent.change(minutes, { target: { value: '100' } })
      expect(screen.queryByText(hint(replacement[0]))).not.toBeInTheDocument()
    })

    it('clears previous-search corrections when the search mode changes', async () => {
      const { user, posts } = await search(kind, initial)
      fireEvent.change(screen.getByLabelText(i18n.t('search.minutes')), {
        target: { value: '90' },
      })
      expect(
        screen.getByText(i18n.t('states.previousClarifications')),
      ).toBeVisible()
      for (const mode of [
        kind === 'events' ? 'places' : 'events',
        kind === 'events' ? 'events' : 'places',
      ]) {
        await user.click(
          screen.getByRole('button', { name: i18n.t(`states.${mode}`) }),
        )
        expect(
          screen.queryByText(i18n.t('states.previousClarifications')),
        ).not.toBeInTheDocument()
        for (const clarification of initial)
          expect(
            screen.queryByText(hint(clarification)),
          ).not.toBeInTheDocument()
      }
      expect(screen.getByLabelText(i18n.t('search.minutes'))).toHaveValue(90)
      expect(posts).toHaveLength(1)
    })

    it.each(['live', 'preview'] as const)(
      'clears previous-search corrections for the development %s action',
      async (action) => {
        const { user, posts } = await search(kind, initial)
        fireEvent.change(screen.getByLabelText(i18n.t('search.minutes')), {
          target: { value: '90' },
        })
        expect(
          screen.getByText(i18n.t('states.previousClarifications')),
        ).toBeVisible()
        await user.click(
          screen.getByText(i18n.t('dev.title'), { selector: 'summary' }),
        )
        await user.click(
          screen.getByRole('button', { name: i18n.t(`dev.${action}`) }),
        )
        expect(
          screen.queryByText(i18n.t('states.previousClarifications')),
        ).not.toBeInTheDocument()
        for (const clarification of initial)
          expect(
            screen.queryByText(hint(clarification)),
          ).not.toBeInTheDocument()
        expect(posts).toHaveLength(1)
      },
    )

    it('does not restore corrections from a late response after another edit and search', async () => {
      let finish!: (response: Response) => void
      const { user, posts, fetch } = await search(
        kind,
        initial,
        [],
        (body, attempt) => {
          if (attempt === 2)
            return new Promise((resolve) => {
              finish = resolve
            })
          if (attempt === 3) return json(clarificationPayload(kind, body, []))
        },
      )
      const minutes = screen.getByLabelText(i18n.t('search.minutes'))
      fireEvent.change(minutes, { target: { value: '90' } })
      const submitName = i18n.t(
        kind === 'events' ? 'search.submitEvents' : 'search.submit',
      )
      await user.click(screen.getByRole('button', { name: submitName }))
      const secondSignal = fetch.mock.calls.at(-1)![1]!.signal!
      fireEvent.change(minutes, { target: { value: '100' } })
      expect(secondSignal.aborted).toBe(true)
      await user.click(screen.getByRole('button', { name: submitName }))
      expect(posts).toHaveLength(3)
      expect(posts[2].available_minutes).toBe(100)
      await act(async () =>
        finish(json(clarificationPayload(kind, posts[1], replacement))),
      )
      expect(screen.queryByText(hint(replacement[0]))).not.toBeInTheDocument()
      expect(
        screen.queryByText(i18n.t('states.previousClarifications')),
      ).not.toBeInTheDocument()
      expect(
        screen.getByText(i18n.t('codes.response_status.unknown'), {
          selector: 'strong',
        }),
      ).toBeVisible()
    })
  },
)
