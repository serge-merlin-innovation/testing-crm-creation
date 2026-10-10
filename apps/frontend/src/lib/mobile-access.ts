/** Tailwind's `md` breakpoint (48rem) is the same width, so CSS and script agree. */
export const MOBILE_BREAKPOINT_PX = 768;

export function hidesEditActions(mobileReadOnly: boolean, viewportWidth: number): boolean {
  return mobileReadOnly && viewportWidth < MOBILE_BREAKPOINT_PX;
}

export function editActionClassName(mobileReadOnly: boolean): string {
  return mobileReadOnly ? "hidden md:contents" : "contents";
}
