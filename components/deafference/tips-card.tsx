"use client"

import { motion } from "framer-motion"
import { Check } from "lucide-react"
import { Card } from "@/components/ui/card"

const tips = [
  "Use good lighting",
  "One signer at a time",
  "Keep hands visible",
  "Face the camera",
  "Avoid cluttered backgrounds",
]

export function TipsCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut", delay: 0.14 }}
    >
      <Card className="p-5 sm:p-6">
        <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
          Best Recognition Tips
        </p>
        <ul className="mt-4 space-y-3">
          {tips.map((tip) => (
            <li key={tip} className="flex items-start gap-3 text-sm text-foreground">
              <Check className="mt-0.5 size-4 shrink-0 text-emerald-500" />
              <span>{tip}</span>
            </li>
          ))}
        </ul>
      </Card>
    </motion.div>
  )
}
