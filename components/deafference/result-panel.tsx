"use client"

import { BadgeCheck, Languages, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"
import type { TranslationResult, Status } from "./data"

function Field({
  label,
  value,
  emphasize,
}: {
  label: string
  value: string
  emphasize?: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-background/60 px-4 py-3">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 text-pretty text-foreground",
          emphasize ? "text-lg font-semibold" : "text-base",
        )}
      >
        {value}
      </p>
    </div>
  )
}

export function ResultPanel({
  result,
  status,
}: {
  result: TranslationResult | null
  status: Status
}) {
  if (!result) {
    return (
      <div className="flex h-full flex-col">
        <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Translation result
        </span>
        <div className="mt-4 flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border p-6 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted">
            <Languages className="size-6 text-muted-foreground" />
          </span>
          <p className="text-sm text-muted-foreground text-balance">
            {status === "idle"
              ? "Speak or type a phrase, then press Translate to see the result here."
              : "Working on your translation…"}
          </p>
        </div>
      </div>
    )
  }

  const confident = result.confidence >= 90

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Translation result
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground">
          <Sparkles className="size-3.5" />
          {result.category}
        </span>
      </div>

      <div className="flex flex-col gap-2.5">
        <Field label="Original phrase" value={result.original} />
        <Field label="Simplified phrase" value={result.simplified} />
        <Field label="Matched sign phrase" value={result.matchedSign} emphasize />
      </div>

      {/* Confidence */}
      <div className="rounded-xl border border-border bg-background/60 px-4 py-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Confidence
          </p>
          <span
            className={cn(
              "inline-flex items-center gap-1 text-sm font-bold",
              confident ? "text-brand-red" : "text-muted-foreground",
            )}
          >
            <BadgeCheck className="size-4" />
            {result.confidence}%
          </span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="brand-gradient h-full rounded-full transition-[width] duration-500"
            style={{ width: `${result.confidence}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <Field label="Category" value={result.category} />
        <Field label="Animation status" value={result.animationStatus} />
      </div>
    </div>
  )
}
