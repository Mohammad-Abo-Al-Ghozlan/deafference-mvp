"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"

type SectionTitleProps = {
  eyebrow?: string
  title: string
  description?: string
  align?: "left" | "center"
  className?: string
}

export function SectionTitle({
  eyebrow,
  title,
  description,
  align = "left",
  className,
}: SectionTitleProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
      transition={{ duration: 0.55, ease: "easeOut" }}
      className={cn(align === "center" && "mx-auto text-center", className)}
    >
      {eyebrow ? (
        <p className="text-sm font-medium tracking-[0.22em] text-muted-foreground uppercase">
          {eyebrow}
        </p>
      ) : null}
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-balance text-foreground sm:text-4xl">
        {title}
      </h2>
      {description ? (
        <p className="mt-4 max-w-2xl text-base leading-7 text-pretty text-muted-foreground sm:text-lg">
          {description}
        </p>
      ) : null}
    </motion.div>
  )
}
