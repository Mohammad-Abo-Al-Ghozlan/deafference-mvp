import { cn } from "@/lib/utils"

/**
 * Deafference wordmark. The source asset is a square canvas with generous
 * whitespace, so we present it on a white chip with object-contain to keep
 * the full mark (icon + wordmark) crisp and uncropped in the header.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-xl bg-white px-2 py-1 shadow-sm ring-1 ring-black/5",
        className,
      )}
    >
      <img
        src="/deafference-logo.png"
        alt="Deafference"
        className="h-9 w-auto object-contain"
      />
    </span>
  )
}
