"use client"

import { ArrowDown, ArrowRight, Camera, Hand, Languages, Sparkles } from "lucide-react"
import { motion } from "framer-motion"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

const PIPELINE_STEPS = [
  { label: "Camera", description: "Capture the live stream.", icon: Camera },
  { label: "Hand Detection", description: "Track hands and posture.", icon: Hand },
  { label: "AI Recognition", description: "Identify the sign pattern.", icon: Sparkles },
  { label: "Translation", description: "Render the translated message.", icon: Languages },
] as const

export function Pipeline({ currentStep = 0 }: { currentStep?: number }) {
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
          Pipeline
        </p>
        <span className="text-xs font-medium text-muted-foreground">Listening workflow</span>
      </div>
      <motion.ol
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="mt-5 grid gap-3 sm:grid-cols-4"
      >
        {PIPELINE_STEPS.map((step, index) => {
          const Icon = step.icon
          const done = currentStep > index
          const active = currentStep === index
          return (
            <li key={step.label} className="relative">
              <div
                className={cn(
                  "flex h-full flex-col items-center justify-center rounded-2xl border p-4 text-center transition-shadow",
                  done || active
                    ? "border-brand-orange/30 bg-brand-orange/10 shadow-sm"
                    : "border-border bg-background/70",
                )}
              >
                <div
                  className={cn(
                    "flex size-11 items-center justify-center rounded-full transition-colors",
                    done || active ? "brand-gradient text-white" : "bg-muted text-muted-foreground",
                    active && !done && "state-active-pulse",
                  )}
                >
                  <Icon className="size-5" />
                </div>
                <p
                  className={cn(
                    "mt-3 text-sm font-semibold",
                    done || active ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {step.label}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {step.description}
                </p>
              </div>
              {index < PIPELINE_STEPS.length - 1 ? (
                <>
                  <ArrowRight className="absolute -right-2 top-1/2 hidden size-4 -translate-y-1/2 text-muted-foreground sm:block" />
                  <ArrowDown className="mx-auto mt-2 size-4 text-muted-foreground sm:hidden" />
                </>
              ) : null}
            </li>
          )
        })}
      </motion.ol>
    </Card>
  )
}
