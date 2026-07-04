"use client"

import { ResultPanel } from "./result-panel"
import type { Status, TranslationResult } from "./data"

export function OutputPanel({
  result,
  status,
}: {
  result: TranslationResult | null
  status: Status
}) {
  return <ResultPanel result={result} status={status} />
}
