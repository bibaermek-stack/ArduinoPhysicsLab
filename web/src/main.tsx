import { createRoot } from "react-dom/client";
import { StrictMode } from "react";
import { useGLTF } from "@react-three/drei";
import CustomCursor from "./components/CustomCursor";
import Hero3D from "./components/Hero3D";
import LoadingScreen from "./components/LoadingScreen";
import ModelShowcase from "./components/ModelShowcase";
import { initNavGlass } from "./animation/navGlass";
import { initTextStagger } from "./animation/textStagger";
import { hasWebGL } from "./lib/env";
import "./styles/app.css";

useGLTF.setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/libs/draco/");

function mountCursor() {
  const el = document.createElement("div");
  el.id = "cursor-root";
  document.body.appendChild(el);
  createRoot(el).render(
    <StrictMode>
      <CustomCursor />
    </StrictMode>
  );
}

function mountHero() {
  const heroRoot = document.getElementById("hero-3d-root");
  if (heroRoot) {
    createRoot(heroRoot).render(
      <StrictMode>
        <Hero3D />
      </StrictMode>
    );
    // CSS-тегі .atom (progressive-enhancement fallback: JS өшірулі/WebGL
    // жоқ болғанда серверде рендерленген статикалық анимация) енді 3D
    // canvas-пен ауыстырылды.
    document.documentElement.classList.add("js-3d-ready");
  }
  const loadingRoot = document.getElementById("hero-loading-root");
  if (loadingRoot) {
    createRoot(loadingRoot).render(
      <StrictMode>
        <LoadingScreen />
      </StrictMode>
    );
  }
}

function mountShowcases() {
  const sections = document.querySelectorAll<HTMLElement>(".model-showcase[data-glb]");
  sections.forEach((section) => {
    const mountEl = section.querySelector<HTMLElement>(".model-canvas-root");
    const readoutList = section.querySelector<HTMLUListElement>(".model-readout ul");
    if (!mountEl) return;

    const glbUrl = section.dataset.glb ?? "";
    const cameraRaw = (section.dataset.camera ?? "0,2.2,4.4").split(",").map(Number);
    const cameraPos: [number, number, number] =
      cameraRaw.length === 3 && cameraRaw.every(Number.isFinite)
        ? (cameraRaw as [number, number, number])
        : [0, 2.2, 4.4];
    let labels: string[] = [];
    try {
      labels = section.dataset.labels ? JSON.parse(section.dataset.labels) : [];
    } catch (err) {
      console.error("model-showcase: data-labels JSON қате", err);
    }

    const onReveal = (label: string) => {
      if (!readoutList) return;
      if (Array.from(readoutList.children).some((li) => li.textContent === label)) return;
      const li = document.createElement("li");
      li.textContent = label;
      readoutList.appendChild(li);
      requestAnimationFrame(() => li.classList.add("is-in"));
    };

    createRoot(mountEl).render(
      <StrictMode>
        <ModelShowcase glbUrl={glbUrl} cameraPos={cameraPos} labels={labels} sectionEl={section} onReveal={onReveal} />
      </StrictMode>
    );
  });
}

function init() {
  if (!hasWebGL()) {
    // WebGL жоқ құрылғыда 3D witrina мүлде орнатылмайды — CSS-тегі
    // статикалық fallback (.hero-visual/.model-showcase-дегі градиент
    // фон) көрінеді (§14 graceful fallback).
    document.documentElement.classList.add("no-webgl");
    initTextStagger();
    initNavGlass();
    return;
  }
  mountCursor();
  mountHero();
  mountShowcases();
  initTextStagger();
  initNavGlass();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
