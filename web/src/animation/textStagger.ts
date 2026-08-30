import { animate, splitText, stagger } from "animejs";
import { prefersReducedMotion } from "../lib/env";

/**
 * `[data-stagger-text]` бар әр элементтің мәтінін әріп-әріп ("T→E→C→H…")
 * ашады — элемент бірінші рет viewport-қа кіргенде, бір рет қана.
 */
export function initTextStagger(): void {
  const targets = document.querySelectorAll<HTMLElement>("[data-stagger-text]");
  if (!targets.length) return;

  if (prefersReducedMotion) {
    targets.forEach((el) => el.classList.add("is-revealed"));
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target as HTMLElement;
        io.unobserve(el);
        el.classList.add("is-revealed");

        const splitter = splitText(el, { chars: true, includeSpaces: true });
        animate(splitter.chars, {
          opacity: [0, 1],
          translateY: [18, 0],
          filter: ["blur(6px)", "blur(0px)"],
          delay: stagger(24),
          duration: 620,
          ease: "outQuad",
        });
      }
    },
    { threshold: 0.4 }
  );
  targets.forEach((el) => io.observe(el));
}
