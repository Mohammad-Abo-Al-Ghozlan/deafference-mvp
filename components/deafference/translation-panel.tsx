"use client"

import { motion } from "framer-motion"
import { Sparkles } from "lucide-react"
import { Card } from "@/components/ui/card"

export function TranslationPanel() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: "easeOut", delay: 0.08 }}
    >
      <Card className="min-h-[18rem] p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
            Live Translation
          </p>
          <span className="inline-flex items-center gap-2 rounded-full bg-brand-orange/12 px-3 py-1 text-xs font-semibold text-brand-red">
            <Sparkles className="size-3.5" />
            Preview
          </span>
        </div>
        <div className="mt-6 flex min-h-[14rem] items-center justify-center rounded-3xl border border-dashed border-border bg-background/65 px-6 text-center">
          <motion.p
            animate={{ opacity: [0.55, 1, 0.55] }}
            transition={{ duration: 2.2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
            className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl"
          >
            Waiting for sign language...
          </motion.p>
        </div>
      </Card>
    </motion.div>
  )
}
