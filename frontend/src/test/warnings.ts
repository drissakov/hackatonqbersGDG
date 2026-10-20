/** Add internal response defaults to synthetic raw fixtures without mutating them. */
export function withWarningDefaults<T extends { warnings: object[] }>(
  value: T,
) {
  return {
    ...value,
    warnings: value.warnings.map((warning) => ({
      ...warning,
      clarifications: [],
    })),
  } as T & {
    warnings: (T['warnings'][number] & { clarifications: never[] })[]
  }
}
