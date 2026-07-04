"use client"

import { cn } from "@/lib/utils"
import { CATEGORIES, QUICK_PHRASES, type CategoryId } from "./data"

export function QuickPhrases({
  activeCategory,
  setCategory,
  onSelect,
}: {
  activeCategory: CategoryId
  setCategory: (c: CategoryId) => void
  onSelect: (phrase: string) => void
}) {
  const group = QUICK_PHRASES.find((g) => g.id === activeCategory) ?? QUICK_PHRASES[0]

  return (
    <section id="phrases" className="scroll-mt-20">
      <div className="mb-5 text-center">
        <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
          Quick Phrases
        </h2>
        <p className="mx-auto mt-2 max-w-lg text-pretty text-muted-foreground">
          Tap a common phrase to translate it instantly. Choose a setting to fit where
          you are.
        </p>
      </div>

      {/* Mode selector pills */}
      <div
        role="tablist"
        aria-label="Quick phrase category"
        className="mb-5 flex flex-wrap justify-center gap-2"
      >
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            role="tab"
            aria-selected={activeCategory === c.id}
            onClick={() => setCategory(c.id)}
            className={cn(
              "rounded-full px-4 py-2 text-sm font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              activeCategory === c.id
                ? "brand-gradient border-transparent text-white shadow-sm"
                : "border border-border bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Phrase buttons */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {group.phrases.map((phrase) => (
          <button
            key={phrase}
            onClick={() => onSelect(phrase)}
            className="flex min-h-16 items-center justify-center rounded-2xl border border-border bg-card px-4 py-3 text-center text-base font-semibold text-balance text-foreground shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-orange/60 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {phrase}
          </button>
        ))}
      </div>
    </section>
  )
}
