import type { Locale } from '../lib/types'

type Resources = Record<Locale, object>
const pluralSuffix = /_(zero|one|two|few|many|other)$/

function leaves(value: object, prefix = ''): Map<string, string> {
  return new Map(
    Object.entries(value).flatMap(([key, entry]): [string, string][] =>
      entry !== null && typeof entry === 'object'
        ? [...leaves(entry, `${prefix}${key}.`)]
        : [[`${prefix}${key}`, typeof entry === 'string' ? entry : '']],
    ),
  )
}

function placeholders(value: string): string[] {
  return [
    ...new Set(
      [...value.matchAll(/\{\{\s*-?\s*([\w.]+)(?:,[^}]*)?\s*\}\}/gu)].map(
        (match) => match[1],
      ),
    ),
  ].sort()
}

/** Compare meaning keys; locale-specific plural categories need not be identical. */
export function auditDictionaries(resources: Resources): string[] {
  const issues: string[] = []
  const pluralBases = new Set(
    Object.values(resources).flatMap((dictionary) =>
      [...leaves(dictionary).keys()].flatMap((key) => {
        const suffix = pluralSuffix.exec(key)
        return suffix ? [key.slice(0, -suffix[0].length)] : []
      }),
    ),
  )
  const baseline = new Map<string, string>()
  let baselineKeys: string[] | undefined

  for (const [locale, dictionary] of Object.entries(resources)) {
    const entries = leaves(dictionary)
    const groups = new Map<string, Map<string, string>>()
    for (const [key, value] of entries) {
      if (!value.trim()) issues.push(`${locale}:${key}: empty translation`)
      const suffix = pluralSuffix.exec(key)
      const base = suffix ? key.slice(0, -suffix[0].length) : key
      const forms = groups.get(base) ?? new Map<string, string>()
      forms.set(suffix?.[1] ?? '', value)
      groups.set(base, forms)
    }
    const keys = [...groups.keys()].sort()
    if (baselineKeys && JSON.stringify(keys) !== JSON.stringify(baselineKeys))
      issues.push(`${locale}: base keys differ`)
    baselineKeys ??= keys
    const categories = new Intl.PluralRules(locale).resolvedOptions()
      .pluralCategories
    for (const [base, forms] of groups) {
      if (pluralBases.has(base)) {
        for (const category of categories) {
          if (!forms.has(category))
            issues.push(`${locale}:${base}: missing plural ${category}`)
        }
        for (const category of forms.keys()) {
          // i18next also permits a dedicated exact-zero override.
          if (
            category !== '' &&
            category !== 'zero' &&
            !categories.includes(category as Intl.LDMLPluralRule)
          )
            issues.push(`${locale}:${base}: invalid plural ${category}`)
        }
      }
      for (const value of forms.values()) {
        const names = JSON.stringify(placeholders(value))
        const expected = baseline.get(base)
        if (expected !== undefined && names !== expected)
          issues.push(`${locale}:${base}: interpolation placeholders differ`)
        baseline.set(base, expected ?? names)
      }
    }
  }
  return issues
}
