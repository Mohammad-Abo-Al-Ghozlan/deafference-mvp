"use client"

import { InputPanel } from "./input-panel"
import { OutputPanel } from "./output-panel"
import { AvatarPreview } from "./avatar-preview"
import type { Status, TranslationResult } from "./data"

export function Translator({
  mode,
  setMode,
  input,
  setInput,
  status,
  result,
  progress,
  currentPhrase,
  onTranslate,
  onClear,
  onShowTextCard,
  onSpeak,
  canReplay,
  onReplay,
}: {
  mode: "speak" | "type"
  setMode: (mode: "speak" | "type") => void
  input: string
  setInput: (value: string) => void
  status: Status
  result: TranslationResult | null
  progress: number
  currentPhrase: string
  onTranslate: () => void
  onClear: () => void
  onShowTextCard: () => void
  onSpeak: () => void
  canReplay: boolean
  onReplay: () => void
}) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <InputPanel
          mode={mode}
          setMode={setMode}
          input={input}
          setInput={setInput}
          status={status}
          onTranslate={onTranslate}
          onClear={onClear}
          onShowTextCard={onShowTextCard}
          onSpeak={onSpeak}
        />
      </div>
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <AvatarPreview
          status={status}
          phrase={currentPhrase}
          progress={progress}
          signing={status === "signing"}
          canReplay={canReplay}
          onReplay={onReplay}
        />
      </div>
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <OutputPanel result={result} status={status} />
      </div>
    </div>
  )
}
