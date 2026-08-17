"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { AlertTriangle, Bug, Loader2, RotateCcw, ShieldAlert, VideoOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

type CameraStatus = "loading" | "streaming" | "denied" | "unsupported" | "error" | "no-devices" | "simulation"

const LOG_PREFIX = "[CameraView]"

// Some headless/fake-device environments never resolve (or reject) the
// getUserMedia promise. This bounds how long we wait before dropping into a
// friendly simulation fallback instead of hanging on "Requesting camera
// access..." forever.
const REQUEST_TIMEOUT_MS = 6000

export function CameraView() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const settledRef = useRef(false)

  const [status, setStatus] = useState<CameraStatus>("loading")
  const [retryToken, setRetryToken] = useState(0)
  const [resolution, setResolution] = useState<{ width: number; height: number } | null>(null)
  const [errorInfo, setErrorInfo] = useState<{ name: string; message: string } | null>(null)
  const [debugOpen, setDebugOpen] = useState(process.env.NODE_ENV !== "production")

  useEffect(() => {
    let cancelled = false
    settledRef.current = false
    setErrorInfo(null)
    setResolution(null)

    async function attach() {
      // Arm the stuck-request watchdog for the whole lifecycle up front,
      // since enumerateDevices() and getUserMedia() can both hang
      // indefinitely in some camera-less/headless environments.
      timeoutRef.current = setTimeout(() => {
        if (!settledRef.current && !cancelled) {
          console.warn(
            `${LOG_PREFIX} Camera lifecycle did not settle within ${REQUEST_TIMEOUT_MS}ms. Falling back to Camera Simulation Mode.`,
          )
          settledRef.current = true
          setStatus("simulation")
        }
      }, REQUEST_TIMEOUT_MS)

      // ---- Phase 1: check device support ----
      setStatus("loading")
      console.log(`${LOG_PREFIX} Phase 1: checking device support…`)

      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        console.error(`${LOG_PREFIX} Phase 1 FAILED: navigator.mediaDevices.getUserMedia is unavailable in this browser.`)
        settledRef.current = true
        if (timeoutRef.current) clearTimeout(timeoutRef.current)
        if (!cancelled) setStatus("unsupported")
        return
      }

      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const videoInputs = devices.filter((d) => d.kind === "videoinput")
        console.log(
          `${LOG_PREFIX} Phase 1 result: ${devices.length} device(s) found, ${videoInputs.length} video input(s).`,
          devices,
        )

        if (videoInputs.length === 0) {
          console.warn(`${LOG_PREFIX} Phase 1: no video input devices detected.`)
          settledRef.current = true
          if (timeoutRef.current) clearTimeout(timeoutRef.current)
          if (!cancelled) setStatus("no-devices")
          return
        }
      } catch (err) {
        console.warn(`${LOG_PREFIX} Phase 1: enumerateDevices() failed, attempting getUserMedia anyway.`, err)
      }

      if (settledRef.current) return // watchdog already fired while Phase 1 was hanging

      // ---- Phase 2: call getUserMedia ----
      const constraints: MediaStreamConstraints = { video: { facingMode: "user" }, audio: false }
      console.log(`${LOG_PREFIX} Phase 2: calling getUserMedia() with constraints:`, constraints)

      try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints)
        settledRef.current = true
        if (timeoutRef.current) clearTimeout(timeoutRef.current)

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        // ---- Phase 3: resolution of the stream ----
        streamRef.current = stream
        const tracks = stream.getVideoTracks()
        console.log(`${LOG_PREFIX} Phase 3: stream resolved. active=${stream.active}, track count=${tracks.length}`)
        tracks.forEach((track) => {
          const settings = track.getSettings()
          console.log(
            `${LOG_PREFIX} Phase 3 track detail: label="${track.label || "unlabeled"}" readyState=${track.readyState} enabled=${track.enabled} width=${settings.width} height=${settings.height}`,
          )
        })

        // ---- Phase 4: attach stream to <video> ----
        if (videoRef.current) {
          const video = videoRef.current
          video.srcObject = stream
          console.log(`${LOG_PREFIX} Phase 4: srcObject attached, waiting for onLoadedMetadata…`)
          video.onloadedmetadata = () => {
            console.log(
              `${LOG_PREFIX} Phase 4: onLoadedMetadata fired. videoWidth=${video.videoWidth} videoHeight=${video.videoHeight}`,
            )
            setResolution({ width: video.videoWidth, height: video.videoHeight })
          }
        } else {
          console.error(`${LOG_PREFIX} Phase 4 FAILED: <video> ref is not mounted, cannot attach stream.`)
        }
        setStatus("streaming")
      } catch (err: unknown) {
        settledRef.current = true
        if (timeoutRef.current) clearTimeout(timeoutRef.current)
        if (cancelled) return

        const name = err instanceof DOMException ? err.name : "UnknownError"
        const message = err instanceof DOMException ? err.message : String(err)
        console.error(`${LOG_PREFIX} Phase 2 FAILED: getUserMedia() rejected — ${name}: ${message}`, err)
        setErrorInfo({ name, message })
        setStatus(name === "NotAllowedError" || name === "PermissionDeniedError" ? "denied" : "error")
      }
    }

    attach()

    return () => {
      cancelled = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      streamRef.current?.getTracks().forEach((track) => {
        track.stop()
        console.log(`${LOG_PREFIX} Stopped track: ${track.kind}/${track.label || "unlabeled"}`)
      })
      streamRef.current = null
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }
  }, [retryToken])

  const handleRetry = useCallback(() => {
    console.log(`${LOG_PREFIX} Retry requested by user.`)
    setRetryToken((t) => t + 1)
  }, [])

  const statusCopy: Record<
    Exclude<CameraStatus, "streaming">,
    { icon: React.ReactNode; title: string; desc: string; retry: boolean }
  > = {
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
    "no-devices": {
      icon: <VideoOff className="size-9 text-muted-foreground" />,
      title: "No camera detected",
      desc: "Connect a webcam or check your device's camera privacy settings, then retry.",
      retry: true,
    },
    simulation: {
      icon: <AlertTriangle className="size-9 text-muted-foreground" />,
      title: "Camera Simulation Mode",
      desc: "We couldn't get a live feed in time, so we're running in simulation mode. You can still retry camera access.",
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
              status === "streaming"
                ? "state-active-ring border-indicator-indigo/40 bg-black"
                : "border-dashed border-border bg-muted/35",
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
                  {statusCopy[status].icon}
                </div>
                <div>
                  <p className="text-base font-semibold text-foreground sm:text-lg">
                    {statusCopy[status].title}
                  </p>
                  <p className="mt-2 text-sm text-muted-foreground">{statusCopy[status].desc}</p>
                  {errorInfo && (status === "denied" || status === "error" || status === "no-devices") && (
                    <p className="mt-2 font-mono text-xs text-destructive/80">{errorInfo.name}</p>
                  )}
                </div>
                {statusCopy[status].retry && (
                  <Button variant="outline" onClick={handleRetry}>
                    <RotateCcw className="size-4" />
                    Try Again
                  </Button>
                )}
              </div>
            )}

            {/* Dev debug toggle — NON-PRODUCTION ONLY. End users must never see the
                raw camera-state overlay or the bug button over their video feed. */}
            {process.env.NODE_ENV !== "production" && (
              <button
                type="button"
                onClick={() => setDebugOpen((v) => !v)}
                aria-label="Toggle camera debug overlay"
                className="absolute right-2 top-2 z-10 flex size-6 items-center justify-center rounded-full bg-black/60 text-white/80 transition-colors hover:text-white"
              >
                <Bug className="size-3.5" />
              </button>
            )}

            {process.env.NODE_ENV !== "production" && debugOpen && (
              <div className="absolute left-2 top-2 z-10 max-w-[220px] rounded-lg bg-black/75 px-2.5 py-2 font-mono text-[10px] leading-relaxed text-emerald-300 shadow-lg backdrop-blur-sm">
                <div>
                  state: <span className="text-white">{status}</span>
                </div>
                <div>
                  resolution:{" "}
                  <span className="text-white">{resolution ? `${resolution.width}x${resolution.height}` : "—"}</span>
                </div>
                {errorInfo && <div className="text-red-400">error: {errorInfo.name}</div>}
              </div>
            )}
          </div>
        </div>
      </Card>
    </motion.div>
  )
}
