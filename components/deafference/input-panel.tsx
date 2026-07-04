"use client"

import { useState } from "react"
import { Eraser, FileText, Keyboard, Mic, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useSettings } from "./settings-provider"
import type { Status } from "./data"

type Mode = "speak" | "type"

const WAVE_BARS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

export function InputPanel({
  mode,
  setMode,
  input,
  setInput,
  status,
  onTranslate,
  onClear,
  onShowTextCard,
  onSpeak,
}: {
  mode: Mode
  setMode: (m: Mode) => void
  input: string
  setInput: (v: string) => void
  status: Status
  onTranslate: () => void
  onClear: () => void
  onShowTextCard: () => void
  onSpeak: () => void
}) {
  const { settings } = useSettings()
  const [holding, setHolding] = useState(false)
  const listening = holding || status === "listening"
  const big = settings.largeButtons

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const nativeComposing =
      (e.nativeEvent as unknown as { isComposing?: boolean }).isComposing ||
      e.keyCode === 229
    if (e.key === "Enter" && !e.shiftKey && !nativeComposing) {
      e.preventDefault()
      onTranslate()
    }
  }

  function startHold() {
    setHolding(true)
  }
  function endHold() {
    if (!holding) return
    setHolding(false)
    onSpeak()
  }

  return (
    <div className="flex h-full flex-col gap-5">
      {/* Mode tabs */}
      <div
        role="tablist"
        aria-label="Input mode"
        className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1"
      >
        {(["speak", "type"] as const).map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={cn(
              "flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              mode === m
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {m === "speak" ? <Mic className="size-4" /> : <Keyboard className="size-4" />}
            {m === "speak" ? "Speak" : "Type"}
          </button>
        ))}
      </div>

      {mode === "speak" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 py-4">
          <div className="relative flex items-center justify-center">
            {listening && (
              <>
                <span className="absolute size-40 animate-ping rounded-full bg-brand-orange/20 [animation-duration:1.6s]" />
                <span className="absolute size-32 rounded-full bg-brand-orange/10" />
              </>
            )}
            <button
              type="button"
              aria-label="Hold to speak"
              aria-pressed={listening}
              onPointerDown={startHold}
              onPointerUp={endHold}
              onPointerLeave={endHold}
              className={cn(
                "brand-gradient relative flex size-28 items-center justify-center rounded-full text-white shadow-lg transition-transform focus-visible:ring-4 focus-visible:ring-ring focus-visible:outline-none",
                listening ? "scale-105 brand-glow" : "hover:scale-105 active:scale-95",
              )}
            >
              <Mic className="size-11" />
            </button>
          </div>

          {/* Fake waveform */}
          <div
            aria-hidden="true"
            className={cn(
              "flex h-8 items-center gap-1 transition-opacity",
              listening ? "opacity-100" : "opacity-30",
            )}
          >
            {WAVE_BARS.map((i) => (
              <span
                key={i}
                className="w-1 rounded-full bg-brand-red"
                style={{
                  height: listening ? "100%" : "22%",
                  animation: listening
                    ? `waveform-bounce ${0.7 + (i % 4) * 0.18}s ease-in-out ${i * 0.05}s infinite`
                    : "none",
                }}
              />
            ))}
          </div>

          <p className="text-sm font-medium text-muted-foreground">
            {listening ? "Listening… release to translate" : "Hold to Speak"}
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col">
          <label htmlFor="phrase" className="sr-only">
            Type what you want to say
          </label>
          <textarea
            id="phrase"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type what you want to say..."
            rows={5}
            className="w-full flex-1 resize-none rounded-xl border border-border bg-background p-4 text-base leading-relaxed text-foreground shadow-sm placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Press Enter to translate · Shift + Enter for a new line
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        <Button
          onClick={onTranslate}
          disabled={mode === "type" && input.trim().length === 0}
          className={cn(
            "brand-gradient w-full border-0 font-semibold text-white",
            big ? "h-14 text-lg" : "h-12 text-base",
          )}
        >
          <Sparkles className="size-5" />
          Translate
        </Button>
        <div className="grid grid-cols-2 gap-2.5">
          <Button variant="outline" onClick={onClear} className={cn(big ? "h-12" : "h-10")}>
            <Eraser className="size-4" />
            Clear
          </Button>
          <Button
            variant="outline"
            onClick={onShowTextCard}
            className={cn(big ? "h-12" : "h-10")}
          >
            <FileText className="size-4" />
            Show Text Card
          </Button>
        </div>
      </div>
    </div>
  )
}
