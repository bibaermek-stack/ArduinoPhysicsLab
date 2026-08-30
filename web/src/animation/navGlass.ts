import { animate, onScroll } from "animejs";
import { prefersReducedMotion } from "../lib/env";

/**
 * §11: navigation scroll кезінде transparent → glass (blur + border)
 * transition жасайды. Тригер аймағы — hero секциясының биіктігі: hero
 * толық көрінгенде nav мөлдір, hero-дан асып скролл жасаса glass-қа
 * ауысады.
 */
export function initNavGlass(): void {
  const nav = document.querySelector<HTMLElement>(".nav");
  const hero = document.querySelector<HTMLElement>(".hero");
  if (!nav) return;

  if (prefersReducedMotion || !hero) {
    nav.classList.add("is-glass");
    return;
  }

  animate(nav, {
    backgroundColor: ["rgba(255, 255, 255, 0)", "rgba(255, 255, 255, 0.86)"],
    backdropFilter: ["blur(0px)", "blur(16px)"],
    borderColor: ["rgba(215, 222, 232, 0)", "rgba(215, 222, 232, 1)"],
    boxShadow: ["0 0px 0px rgba(15, 23, 42, 0)", "0 8px 24px rgba(15, 23, 42, 0.06)"],
    ease: "linear",
    // onScroll enter/leave string форматы "[container] [target]" (СЫРТҚЫ
    // ретпен ЕМЕС) — бұрын "bottom top" деп жазылған leave іс жүзінде
    // "hero-дың ЖОҒАРЫ шеті viewport-тың ТӨМЕНІНЕ жетті" дегенді білдіріп,
    // scroll басталғанда бірден "аяқталып", nav лезде glass-қа өтіп кеткен
    // (расталған қате). Керегіміз: "hero-дың ТӨМЕН шеті viewport-тың
    // ЖОҒАРЫСЫНА жетті" — container='top', target='bottom'.
    autoplay: onScroll({
      target: hero,
      sync: true,
      enter: "top top",
      leave: "top bottom",
    }),
  });
}
