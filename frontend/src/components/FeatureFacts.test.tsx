import { act, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import i18n from '../i18n'
import { parseSearchResponse } from '../lib/api'
import { formatDateTime } from '../lib/format'
import type { Locale } from '../lib/types'
import { syntheticFeatureResponse } from '../test/featureEvidence'
import { ResultCard } from './ResultCard'

beforeEach(async () => {
  await i18n.changeLanguage('en')
})
afterEach(() => {
  vi.unstubAllGlobals()
})

const labels = {
  en: {
    title: 'Visit conditions from sources',
    playground: 'Children’s playground',
    access: 'Public access',
    outlets: 'Customer power outlets',
    yes: 'Source says yes',
    no: 'Source says no',
    notice:
      'Checked against the source, not on site. Safety, age suitability and current availability remain unconfirmed.',
    derived:
      'This descriptive name was composed from the feature type; the official name is unknown.',
    checked: 'Source checked',
    updated: 'Source last edited',
    observed: 'Fact observed',
    unknown: 'Unknown',
  },
  ru: {
    title: 'Условия посещения по источникам',
    playground: 'Детская игровая площадка',
    access: 'Публичный доступ',
    outlets: 'Розетки для посетителей',
    yes: 'В источнике указано: да',
    no: 'В источнике указано: нет',
    notice:
      'Сверено с источником, без проверки на месте. Безопасность, соответствие возрасту и текущая доступность не подтверждены.',
    derived:
      'Описательное название составлено по типу объекта; официальное название неизвестно.',
    checked: 'Источник сверён',
    updated: 'Последнее изменение источника',
    observed: 'Наблюдение факта',
    unknown: 'Неизвестно',
  },
  kk: {
    title: 'Дереккөздегі келу шарттары',
    playground: 'Балалар ойын алаңы',
    access: 'Жалпыға қолжетімділік',
    outlets: 'Келушілерге арналған розеткалар',
    yes: 'Дереккөзде: иә',
    no: 'Дереккөзде: жоқ',
    notice:
      'Дереккөзбен салыстырылды, орнында тексерілмеді. Қауіпсіздік, жасқа сәйкестік және қазіргі қолжетімділік расталмаған.',
    derived:
      'Бұл сипаттамалық атау нысан түрінен құрастырылды; ресми атауы белгісіз.',
    checked: 'Дереккөз тексерілді',
    updated: 'Дереккөздің соңғы өзгерісі',
    observed: 'Фактіні бақылау',
    unknown: 'Белгісіз',
  },
}

function responseWithConditions() {
  const value = syntheticFeatureResponse()
  const card = value.items[0]
  const base = card.feature_evidence![0]
  card.feature_evidence!.push(
    {
      ...base,
      field: 'public_access',
      value: false,
      source_field: 'access',
      source_value: 'private',
    },
    {
      ...base,
      field: 'power_outlets',
      source_field: 'service:electricity',
      source_value: 'limited',
    },
  )
  card.missing_fields = ['age_restrictions']
  return parseSearchResponse(value, 'recommendations', 'en')
}

describe('visit condition source facts', () => {
  it.each(['kk', 'ru', 'en'] as Locale[])(
    'shows literal feature labels, honest check dates and derived names in %s',
    async (locale) => {
      await i18n.changeLanguage(locale)
      const response = responseWithConditions()
      const card = response.items[0]
      render(<ResultCard card={card} locale={locale} />)
      const text = labels[locale]
      const facts = screen.getByRole('region', { name: text.title })
      for (const label of [text.playground, text.access, text.outlets])
        expect(within(facts).getByText(`${label}:`)).toBeInTheDocument()
      expect(within(facts).getAllByText(text.yes)).toHaveLength(2)
      expect(within(facts).getByText(text.no)).toBeInTheDocument()
      expect(within(facts).getByText(text.notice)).toBeInTheDocument()
      expect(screen.getByText(text.derived)).toBeInTheDocument()
      expect(
        within(facts).getAllByText(
          `${text.checked}: ${formatDateTime(card.feature_evidence![0].checked_at, locale)}`,
        ),
      ).toHaveLength(3)
      expect(
        within(facts).getAllByText(
          `${text.updated}: ${formatDateTime(card.feature_evidence![0].source_updated_at, locale)}`,
        ),
      ).toHaveLength(3)
      expect(
        within(facts).getAllByText(`${text.observed}: ${text.unknown}`),
      ).toHaveLength(3)
      expect(within(facts).getByText('leisure=playground')).toHaveAttribute(
        'lang',
        '',
      )
      for (const link of within(facts).getAllByRole('link')) {
        expect(link).toHaveAttribute('href', card.poi.sources[0].url)
        expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      }
    },
  )

  it('switches existing evidence and missing public access without fetching', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const response = parseSearchResponse(
      syntheticFeatureResponse(),
      'recommendations',
      'en',
    )
    const { rerender } = render(
      <ResultCard card={response.items[0]} locale="en" />,
    )
    for (const locale of ['ru', 'kk', 'en'] as const) {
      await act(async () => {
        await i18n.changeLanguage(locale)
      })
      rerender(<ResultCard card={response.items[0]} locale={locale} />)
      expect(screen.getByText(labels[locale].access)).toBeInTheDocument()
      expect(screen.getByText(labels[locale].notice)).toBeInTheDocument()
    }
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps older omitted fields quiet without inventing source checks', () => {
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    render(<ResultCard card={response.items[0]} locale="en" />)
    expect(
      screen.queryByRole('region', { name: labels.en.title }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(labels.en.derived)).not.toBeInTheDocument()
  })
})
