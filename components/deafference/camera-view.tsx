"use client"

import { motion } from "framer-motion"
import { Camera } from "lucide-react"
import { Card } from "@/components/ui/card"

export function CameraView() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
    >
      <Card className="overflow-hidden p-0">
        <div className="border-b border-border px-6 py-5">
          <p className="text-xs font-semibold tracking-[0.22em] text-muted-foreground uppercase">
            Live Camera
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Point your camera toward the signer.
          </p>
        </div>
        <div className="p-4 sm:p-6">
          <div className="relative aspect-video rounded-3xl border-2 border-dashed border-border bg-muted/35">
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-center">
              <div className="flex size-20 items-center justify-center rounded-full bg-background shadow-sm ring-1 ring-border">
                <Camera className="size-9 text-muted-foreground" />
              </div>
              <div>
                <p className="text-base font-semibold text-foreground sm:text-lg">
                  Live camera preview will appear here.
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  This space is reserved for the future webcam and recognition pipeline.
                </p>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  )
}
