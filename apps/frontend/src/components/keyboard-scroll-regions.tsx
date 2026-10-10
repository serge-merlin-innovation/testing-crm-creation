"use client";

import { useEffect } from "react";

const SCROLLERS = '[data-slot="table-container"], .overflow-x-auto, .overflow-auto, [data-slot="card-content"]';

/**
 * WCAG 2.1.1: a region that scrolls must be reachable by keyboard. Tables scroll sideways on a
 * 375 px phone, so every scroller that actually overflows gets a tab stop and a name. Done once
 * here rather than in each of the generated shadcn primitives, which are never edited by hand.
 */
export function KeyboardScrollRegions({ label }: { label: string }) {
  useEffect(() => {
    const mark = () => {
      for (const element of document.querySelectorAll<HTMLElement>(SCROLLERS)) {
        const scrolls = element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight;
        const style = getComputedStyle(element);
        const scrollable = /(auto|scroll)/.test(style.overflowX + style.overflowY);
        if (scrolls && scrollable && !element.hasAttribute("tabindex")) {
          element.tabIndex = 0;
          element.setAttribute("role", "region");
          element.setAttribute("aria-label", label);
          element.dataset.keyboardScroll = "";
        }
      }
    };
    mark();
    const observer = new MutationObserver(mark);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", mark);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", mark);
    };
  }, [label]);

  return null;
}
