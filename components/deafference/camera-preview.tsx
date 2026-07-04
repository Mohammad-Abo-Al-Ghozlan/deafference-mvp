"use client"

import { Camera } from "lucide-react"
import { Card } from "@/components/ui/card"

export function CameraPreview() {
  return (
    <Card className="flex min-h-56 items-center justify-center border-dashed">
      <div className="text-center">
        <Camera className="mx-auto size-8 text-muted-foreground" />
        <p className="mt-3 text-sm font-medium text-foreground">Camera preview placeholder</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Reserved for the future translation workflow.
        </p>
      </div>
    </Card>
  )
}
