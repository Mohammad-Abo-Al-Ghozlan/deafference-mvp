"use client"

import { motion } from "framer-motion"
import { Card } from "@/components/ui/card"

export function StatusCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut", delay: 0.05 }}
    >
      <Card className="p-5">
        <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
          Current Status
        </p>
        <div className="mt-4 flex items-center gap-3">
          <span className="size-3 rounded-full bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.16)]" />
          <p className="text-lg font-semibold text-foreground">Ready to Listen</p>
        </div>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          The system is waiting for sign language input.
        </p>
      </Card>
    </motion.div>
  )
}
