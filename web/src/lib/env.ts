export const prefersReducedMotion =
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const isTouchDevice =
  typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;

export const isNarrowViewport =
  typeof window !== "undefined" && window.matchMedia("(max-width: 860px)").matches;

export function hasWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/** Desktop/tablet-те 2, ауыр GPU жүктемесін үнемдеу үшін мобильде 1. */
export const targetPixelRatio = () =>
  Math.min(window.devicePixelRatio || 1, isNarrowViewport ? 1 : 2);
