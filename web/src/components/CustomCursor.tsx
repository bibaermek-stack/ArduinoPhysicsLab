import { useEffect, useRef } from "react";
import { isTouchDevice, prefersReducedMotion } from "../lib/env";

const MAGNETIC_SELECTOR = "a, button, .btn, .nav-links a, .brand, [data-cursor-magnetic]";
const GLOW_SELECTOR = ".model-canvas, .hero-canvas, canvas";

export default function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isTouchDevice || prefersReducedMotion) return;

    const dot = dotRef.current;
    const ring = ringRef.current;
    if (!dot || !ring) return;

    let mouseX = window.innerWidth / 2;
    let mouseY = window.innerHeight / 2;
    let ringX = mouseX;
    let ringY = mouseY;
    let magnetTarget: { x: number; y: number } | null = null;

    const onMove = (e: PointerEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;

      const el = document.elementFromPoint(mouseX, mouseY);
      const magnetic = el?.closest(MAGNETIC_SELECTOR);
      if (magnetic) {
        const rect = magnetic.getBoundingClientRect();
        magnetTarget = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        ring.classList.add("is-magnetic");
      } else {
        magnetTarget = null;
        ring.classList.remove("is-magnetic");
      }
      ring.classList.toggle("is-glow", !!el?.closest(GLOW_SELECTOR));
    };

    const onDown = () => ring.classList.add("is-active");
    const onUp = () => ring.classList.remove("is-active");

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);

    let raf = 0;
    const tick = () => {
      const tx = magnetTarget ? mouseX + (magnetTarget.x - mouseX) * 0.35 : mouseX;
      const ty = magnetTarget ? mouseY + (magnetTarget.y - mouseY) * 0.35 : mouseY;
      ringX += (tx - ringX) * 0.18;
      ringY += (ty - ringY) * 0.18;
      dot.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0) translate(-50%, -50%)`;
      ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0) translate(-50%, -50%)`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    document.body.classList.add("has-custom-cursor");
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      document.body.classList.remove("has-custom-cursor");
    };
  }, []);

  if (isTouchDevice || prefersReducedMotion) return null;

  return (
    <>
      <div ref={dotRef} className="cursor-dot" aria-hidden="true" />
      <div ref={ringRef} className="cursor-ring" aria-hidden="true" />
    </>
  );
}
