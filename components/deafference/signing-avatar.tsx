"use client"

import { motion } from "framer-motion"
import { useSettings } from "./settings-provider"

/**
 * A calm, human-centered avatar illustration built with SVG. When `signing`
 * is true, the hands gesture gently to suggest sign language. Motion respects
 * the reduce-motion accessibility setting.
 */
export function SigningAvatar({ signing }: { signing: boolean }) {
  const { settings } = useSettings()
  const animate = signing && !settings.reduceMotion

  const leftHand = animate
    ? { y: [0, -14, -4, -18, 0], x: [0, -4, 2, -2, 0], rotate: [0, -8, 4, -6, 0] }
    : { y: 0, x: 0, rotate: 0 }
  const rightHand = animate
    ? { y: [0, -18, -6, -12, 0], x: [0, 4, -2, 3, 0], rotate: [0, 8, -4, 6, 0] }
    : { y: 0, x: 0, rotate: 0 }

  const loop = { duration: 2.4, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" as const }

  return (
    <svg
      viewBox="0 0 320 320"
      className="h-full w-full"
      role="img"
      aria-label={
        signing ? "Avatar performing a sign-language gesture" : "Sign-language avatar, ready"
      }
    >
      <defs>
        <radialGradient id="halo" cx="50%" cy="42%" r="60%">
          <stop offset="0%" stopColor="var(--brand-yellow)" stopOpacity="0.35" />
          <stop offset="55%" stopColor="var(--brand-orange)" stopOpacity="0.14" />
          <stop offset="100%" stopColor="var(--brand-red)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="body" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--brand-orange)" />
          <stop offset="100%" stopColor="var(--brand-red)" />
        </linearGradient>
        <linearGradient id="skin" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--brand-yellow)" />
          <stop offset="100%" stopColor="var(--brand-orange)" />
        </linearGradient>
      </defs>

      {/* warm halo */}
      <circle cx="160" cy="140" r="150" fill="url(#halo)" />

      {/* shoulders / torso */}
      <path
        d="M60 320 C60 236 104 196 160 196 C216 196 260 236 260 320 Z"
        fill="url(#body)"
        opacity="0.95"
      />
      {/* neck */}
      <rect x="142" y="150" width="36" height="46" rx="18" fill="url(#skin)" />

      {/* head */}
      <circle cx="160" cy="112" r="52" fill="url(#skin)" />
      {/* calm face */}
      <circle cx="142" cy="108" r="5.5" fill="oklch(0.28 0.03 40)" />
      <circle cx="178" cy="108" r="5.5" fill="oklch(0.28 0.03 40)" />
      <path
        d="M144 130 Q160 142 176 130"
        stroke="oklch(0.28 0.03 40)"
        strokeWidth="5"
        strokeLinecap="round"
        fill="none"
      />

      {/* hands */}
      <motion.g
        style={{ originX: "118px", originY: "230px" }}
        animate={leftHand}
        transition={loop}
      >
        <ellipse cx="112" cy="226" rx="26" ry="30" fill="url(#skin)" />
        <rect x="98" y="196" width="10" height="26" rx="5" fill="url(#skin)" />
        <rect x="112" y="192" width="10" height="30" rx="5" fill="url(#skin)" />
        <rect x="126" y="196" width="10" height="26" rx="5" fill="url(#skin)" />
      </motion.g>

      <motion.g
        style={{ originX: "202px", originY: "230px" }}
        animate={rightHand}
        transition={loop}
      >
        <ellipse cx="208" cy="226" rx="26" ry="30" fill="url(#skin)" />
        <rect x="194" y="196" width="10" height="26" rx="5" fill="url(#skin)" />
        <rect x="208" y="192" width="10" height="30" rx="5" fill="url(#skin)" />
        <rect x="222" y="196" width="10" height="26" rx="5" fill="url(#skin)" />
      </motion.g>
    </svg>
  )
}
