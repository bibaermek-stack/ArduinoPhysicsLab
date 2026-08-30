import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { animate } from "animejs";

/**
 * Гибрид сайтта (§ Auto Mode шешімі) nav/hero мәтіні/карточкалар бәрі
 * Jinja арқылы БІРДЕН көрінеді — тек 3D witrina жүктелуде. Сондықтан бұл
 * толық экранды емес, hero-визуал ІШІНДЕГІ шағын "STEM · LOADING NN%"
 * индикатор: нақты мазмұнды жасанды түрде бөгемей, тек GLB жүктелу
 * барысын көрсетеді.
 */
export default function LoadingScreen() {
  const [percent, setPercent] = useState(0);
  const [done, setDone] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const manager = THREE.DefaultLoadingManager;
    const prevProgress = manager.onProgress;
    const prevLoad = manager.onLoad;

    manager.onProgress = (url, loaded, total) => {
      setPercent(total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0);
      prevProgress?.(url, loaded, total);
    };
    manager.onLoad = () => {
      setPercent(100);
      setDone(true);
      prevLoad?.();
    };

    // Кэштен/жылдам желіде жүктеу event шақырылмай қалуы мүмкін —
    // fallback: белгілі уақыттан кейін де жасырамыз.
    const fallback = window.setTimeout(() => setDone(true), 4000);

    return () => {
      manager.onProgress = prevProgress;
      manager.onLoad = prevLoad;
      window.clearTimeout(fallback);
    };
  }, []);

  useEffect(() => {
    if (!done || !rootRef.current) return;
    animate(rootRef.current, {
      opacity: [1, 0],
      duration: 520,
      ease: "outQuad",
      onComplete: () => {
        if (rootRef.current) rootRef.current.style.display = "none";
      },
    });
  }, [done]);

  return (
    <div ref={rootRef} className="model-loading" aria-hidden="true">
      <span className="model-loading-kicker">STEM</span>
      <span className="model-loading-percent">{String(percent).padStart(2, "0")}%</span>
      <div className="model-loading-bar">
        <div className="model-loading-bar-fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
