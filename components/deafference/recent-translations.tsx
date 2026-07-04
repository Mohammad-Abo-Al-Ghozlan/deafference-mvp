"use client"

import { motion } from "framer-motion"
import { Card } from "@/components/ui/card"

export function RecentTranslations() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut", delay: 0.12 }}
    >
      <Card className="p-5 sm:p-6">
        <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
          Recent Translations
        </p>
        <div className="mt-4 rounded-2xl border border-dashed border-border bg-background/60 px-4 py-8 text-sm text-muted-foreground">
          No translations yet.
        </div>
      </Card>
    </motion.div>
  )
}
