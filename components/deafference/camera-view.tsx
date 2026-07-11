"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { AlertTriangle, Loader2, RotateCcw, ShieldAlert, VideoOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

type CameraStatus = "loading" | "streaming" | "denied" | "unsupported" | "error"

export function CameraView() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [status, setStatus] = useState<CameraStatus>("loading")
  const [retryToken, setRetryToken] = useState(0)

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setStatus("unsupported")
      return
    }

    let cancelled = false
    setStatus("loading")

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
        setStatus("streaming")
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const name = err instanceof DOMException ? err.name : ""
        setStatus(name === "NotAllowedError" || name === "PermissionDeniedError" ? "denied" : "error")
      })

    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }
  }, [retryToken])

  const statusCopy: Record<Exclude<CameraStatus, "streaming">, { icon: React.ReactNode; title: string; desc: string; retry: boolean }> = {
    loading: {
      icon: <Loader2 className="size-9 animate-spin text-muted-foreground" />,
      title: "Requesting camera access…",
      desc: "Allow camera permissions when prompted by your browser.",
      retry: false,
    },
    denied: {
      icon: <ShieldAlert className="size-9 text-muted-foreground" />,
      title: "Camera access denied",
      desc: "Enable camera permissions for this site in your browser settings, then try again.",
      retry: true,
    },
    unsupported: {
      icon: <VideoOff className="size-9 text-muted-foreground" />,
      title: "Camera not supported",
      desc: "Your browser doesn't support live camera access. Try a recent version of Chrome, Edge, or Firefox.",
      retry: false,
    },
    error: {
      icon: <AlertTriangle className="size-9 text-muted-foreground" />,
      title: "Unable to access camera",
      desc: "Something went wrong while starting the camera. Please try again.",
      retry: true,
    },
  }

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
          <div
            className={cn(
              "relative aspect-video overflow-hidden rounded-3xl border-2",
              status === "streaming" ? "border-border bg-black" : "border-dashed border-border bg-muted/35",
            )}
          >
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={cn(
                "absolute inset-0 size-full object-cover",
                status === "streaming" ? "opacity-100" : "pointer-events-none opacity-0",
              )}
            />

            {status !== "streaming" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
                <div className="flex size-20 items-center justify-center rounded-full bg-background shadow-sm ring-1 ring-border">
                  {status === "loading" ? statusCopy.loading.icon : statusCopy[status].icon}
                </div>
                <div>
                  <p className="text-base font-semibold text-foreground sm:text-lg">
                    {statusCopy[status].title}
                  </p>
                  <p className="mt-2 text-sm text-muted-foreground">{statusCopy[status].desc}</p>
                </div>
                {statusCopy[status].retry && (
                  <Button variant="outline" onClick={() => setRetryToken((t) => t + 1)}>
                    <RotateCcw className="size-4" />
                    Try Again
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </Card>
    </motion.div>
  )
}
