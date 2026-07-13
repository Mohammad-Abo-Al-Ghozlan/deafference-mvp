import { cn } from "@/lib/utils"

/**
 * Deafference wordmark. Rendered from alpha-transparent PNGs (background
 * chroma-keyed out) so it sits directly on the page with no bounding box.
 * The wordmark ink is baked dark-on-transparent for light mode and
 * light-on-transparent for dark mode, swapped via the `dark:` variant,
 * since a single static raster can't adapt its own ink color at runtime.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center bg-transparent", className)}>
      <img
        src="/deafference-logo-transparent.png"
        alt="Deafference"
        className="h-9 w-auto object-contain dark:hidden"
      />
      <img
        src="/deafference-logo-transparent-dark.png"
        alt="Deafference"
        className="hidden h-9 w-auto object-contain dark:block"
      />
    </span>
  )
}
