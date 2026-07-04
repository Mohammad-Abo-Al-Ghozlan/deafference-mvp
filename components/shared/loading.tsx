"use client"

import { motion } from "framer-motion"

export function Loading() {
  return (
    <div className="flex min-h-40 items-center justify-center rounded-3xl border border-border bg-card/80 p-8">
      <motion.div
        aria-label="Loading"
        className="size-10 rounded-full border-2 border-border border-t-brand-orange"
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
      />
    </div>
  )
}
