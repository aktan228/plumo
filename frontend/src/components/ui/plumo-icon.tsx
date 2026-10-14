import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";

/** Decorative interface icon. Give its containing control an accessible name. */
export function PlumoIcon({ icon, size = 20, className }: { icon: IconSvgElement; size?: number; className?: string }) {
  return <HugeiconsIcon icon={icon} size={size} strokeWidth={1.7} color="currentColor" className={`shrink-0 ${className ?? ""}`} aria-hidden="true" focusable="false" />;
}
