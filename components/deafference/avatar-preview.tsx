"use client"

import { useState } from "react"
import { Maximize2, RotateCcw, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { SigningAvatar } from "./signing-avatar"
import { STATUS_LABEL, type Status } from "./data"

function StatusBadge({ status }: { status: Status }) {
  const active = status !== "idle" && status !== "complete"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold",
        status === "complete"
          ? "bg-brand-orange/15 text-brand-red"
          : active
            ? "brand-gradient text-white"
            : "bg-muted text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-2 rounded-full",
          status === "complete"
            ? "bg-brand-red"
            : active
              ? "animate-pulse bg-white"
              : "bg-muted-foreground/60",
        )}
      />
      {STATUS_LABEL[status]}
    </span>
  )
}

export function AvatarPreview({
  status,
  phrase,
  progress,
  signing,
  canReplay,
  onReplay,
}: {
  status: Status
  phrase: string
  progress: number
  signing: boolean
  canReplay: boolean
  onReplay: () => void
}) {
  const [fullscreen, setFullscreen] = useState(false)

  const caption =
    phrase ||
    (status === "idle"
      ? "Your sign animation will appear here"
      : "Preparing your phrase…")

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Avatar preview
        </span>
        <StatusBadge status={status} />
      </div>

      <div className="relative flex flex-1 items-center justify-center overflow-hidden rounded-2xl border border-border bg-gradient-to-b from-accent/50 to-card p-2">
        <div className="aspect-square w-full max-w-[280px]">
          <SigningAvatar signing={signing} />
        </div>
      </div>

      {/* Caption */}
      <div className="rounded-xl bg-muted/70 px-4 py-3 text-center">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Now signing
        </p>
        <p className="mt-1 text-lg font-semibold text-balance text-foreground">{caption}</p>
      </div>

      {/* Progress */}
      <div>
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="brand-gradient h-full rounded-full transition-[width] duration-200 ease-out"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={Math.round(progress)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Signing progress"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <Button
          variant="outline"
          onClick={onReplay}
          disabled={!canReplay}
          className="h-11"
        >
          <RotateCcw className="size-4" />
          Replay Sign
        </Button>
        <Button variant="outline" onClick={() => setFullscreen(true)} className="h-11">
          <Maximize2 className="size-4" />
          Fullscreen
        </Button>
      </div>

      {fullscreen && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background/98 backdrop-blur-sm">
          <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-6">
            <StatusBadge status={status} />
            <Button
              variant="ghost"
              size="icon"
              aria-label="Exit fullscreen"
              onClick={() => setFullscreen(false)}
            >
              <X />
            </Button>
          </div>
          <div className="flex flex-1 flex-col items-center justify-center gap-8 p-6">
            <div className="aspect-square w-full max-w-md">
              <SigningAvatar signing={signing} />
            </div>
            <p className="max-w-2xl text-center text-3xl font-semibold text-balance sm:text-4xl">
              {caption}
            </p>
            <div className="h-3 w-full max-w-md overflow-hidden rounded-full bg-muted">
              <div
                className="brand-gradient h-full rounded-full transition-[width] duration-200"
                style={{ width: `${progress}%` }}
              />
            </div>
            <Button
              onClick={onReplay}
              disabled={!canReplay}
              className="brand-gradient h-12 border-0 px-8 text-base font-semibold text-white"
            >
              <RotateCcw className="size-5" />
              Replay Sign
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
