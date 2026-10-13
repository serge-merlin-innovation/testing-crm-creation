import type { ReactNode } from "react";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";

// WCAG 2.1.1: content that scrolls sideways on a 375 px phone needs a named tab stop.
export function ScrollRegion({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ScrollArea className="w-full">
      <div role="region" aria-label={label} tabIndex={0}>
        {children}
      </div>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}
