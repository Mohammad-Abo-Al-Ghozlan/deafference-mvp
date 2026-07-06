"use client"

import { Keyboard, Mic, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"

export function Hero({
  onSpeak,
  onType,
  onQuickPhrases,
}: {
  onSpeak: () => void
  onType: () => void
  onQuickPhrases: () => void
}) {
  return (
    <section className="relative overflow-hidden">
      {/* soft warm glow, decorative */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[42rem] -translate-x-1/2 rounded-full opacity-45 blur-3xl"
        style={{
          backgroundImage:
            "radial-gradient(closest-side, var(--brand-orange), transparent)",
        }}
      />
      <div className="mx-auto max-w-3xl px-4 pt-14 pb-8 text-center sm:px-6 sm:pt-20">
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-xs font-medium text-muted-foreground shadow-sm">
          <Sparkles className="size-3.5 text-brand-orange" />
          Accessibility-first communication
        </span>

        <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
          Instant Sign Translation for{" "}
          <span className="brand-gradient-text">Real Conversations</span>
        </h1>

        <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-pretty text-muted-foreground">
          Speak or type a phrase and show it as a clear sign-language-style avatar
          animation. Simple enough for anyone to use in under ten seconds.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button
            size="lg"
            onClick={onSpeak}
            className="brand-gradient brand-glow h-12 w-full min-w-44 border-0 px-6 text-base font-semibold text-white sm:w-auto"
          >
            <Mic className="size-5" />
            Speak to Sign
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={onType}
            className="h-12 w-full min-w-44 px-6 text-base font-semibold sm:w-auto"
          >
            <Keyboard className="size-5" />
            Type to Sign
          </Button>
        </div>

        <button
          onClick={onQuickPhrases}
          className="mt-5 inline-flex items-center rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          Try Quick Phrases
        </button>
      </div>
    </section>
  )
}
