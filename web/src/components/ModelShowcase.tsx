import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { createTimeline, onScroll, type Timeline } from "animejs";
import { computeExplodedParts, fitAndCenter } from "../lib/explode";
import { prefersReducedMotion } from "../lib/env";

interface ModelShowcaseProps {
  glbUrl: string;
  cameraPos: [number, number, number];
  labels: string[];
  sectionEl: HTMLElement;
  onReveal?: (label: string) => void;
}

const STAGGER_MS = 90;
const TWEEN_MS = 700;

function Scene({ glbUrl, labels, sectionEl, onReveal, onReady }: ModelShowcaseProps & { onReady: () => void }) {
  const { scene } = useGLTF(glbUrl, true);
  const groupRef = useRef<THREE.Group>(null);
  const timelineRef = useRef<Timeline | null>(null);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    // useGLTF кэштелген ортақ scene-ді қайтарады (StrictMode/remount кезінде
    // ҚАЙТА пайдаланылады) — сол объектіні тікелей мутациялау (scale/
    // position/explode) remount-та бүлінген (жартылай tween-делген)
    // "original" мәндер оқылуына әкеледі. clone(true) геометрия/материалды
    // бөліспей, тек node graph-ты дербестендіреді.
    const root = scene.clone(true);
    group.add(root);
    // МАҢЫЗДЫ: computeExplodedParts әр баланың ЛОКАЛЬ радиусын
    // fitAndCenter-ге ДЕЙІНГІ (масштабталмаған) bbox-тан есептеуі керек.
    // fitAndCenter root.scale-ді өзгертеді — сол СОҢ шақырылса, "радиус"
    // world-scale өлшемінен (~2.6) есептеліп, бөлшектер камерадан
    // жүздеген есе алыс "жарылады" (бұрын vanilla-JS нұсқасында да дәл
    // осы қате табылған, енді функцияларды бөлгенде қайта еніп кеткен).
    const parts = computeExplodedParts(root, labels);
    fitAndCenter(root);

    const revealed = new Set<number>();
    // Әр бөлшектің "ашылды" деп есептелетін timeline-currentTime шегі —
    // scroll ілгері/кері жүрсе де дұрыс жұмыс істеу үшін onBegin (ол
    // sync-seek режимінде әр әдіске бірдей сенімді триггерленбеуі мүмкін)
    // орнына ортақ onUpdate ішінде currentTime-мен салыстырамыз.
    const revealAt: Array<{ time: number; label: string; index: number }> = [];

    const timeline = createTimeline({
      // enter/leave-ді ӘДЕЙІ көрсетпейміз: onScroll-тың ӨЗ дефолты дәл
      // керегіміз — target-тың ЖОҒАРЫ шеті container-дың ТӨМЕНГІ шетіне
      // жеткенде басталып (секция төменнен енді "кіре" бастағанда),
      // target-тың ТӨМЕН шеті container-дың ЖОҒАРҒЫ шетіне жеткенде
      // аяқталады (секция толық скролл етіп өткенде). enter/leave string-ті
      // "[container] [target]" ретімен қолмен жазу оңай шатастырады —
      // расталды: бастапқы `enter:"top bottom", leave:"bottom top"`
      // нұсқасы ДӘЛ КЕРІСІНШЕ (leave-ге сай "enter", enter-ге сай "leave")
      // орналасып, canvas бос қалуына әкелген.
      autoplay: onScroll({ target: sectionEl, sync: true }),
      onUpdate: (self) => {
        const t = self.currentTime;
        for (const entry of revealAt) {
          if (t >= entry.time && !revealed.has(entry.index)) {
            revealed.add(entry.index);
            onReveal?.(entry.label);
          }
        }
      },
    });
    timelineRef.current = timeline;

    parts.forEach((part, i) => {
      const offset = i * STAGGER_MS;
      // Бастапқы күй — "жарылған" (parentless бөлшектер шашылған), scroll
      // ілгерілеген сайын өз орнына жиналады (§5: originalPosition ↔
      // explodedPosition).
      part.node.position.copy(part.exploded);
      part.node.rotation.copy(part.spin);

      timeline.add(
        part.node.position,
        { x: part.original.x, y: part.original.y, z: part.original.z, ease: "outCubic" },
        offset
      );
      timeline.add(
        part.node.rotation,
        { x: 0, y: 0, z: 0, ease: "outCubic" },
        offset
      );

      if (part.label) {
        revealAt.push({ time: offset + TWEEN_MS * 0.55, label: part.label, index: i });
      }
    });

    onReady();

    return () => {
      timeline.revert();
      group.remove(root);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene]);

  useFrame(({ clock }) => {
    if (prefersReducedMotion || !groupRef.current) return;
    // Толық 360° айналдыру моделді кез келген сәтте "теріс" бұрышта
    // көрсете алады — сондықтан таңдалған жақсы бұрыштан шектеулі
    // ауытқумен ғана тербейміз (расталған UX түзету).
    groupRef.current.rotation.y = Math.sin(clock.elapsedTime * 0.35) * 0.16;
  });

  return <group ref={groupRef} />;
}

export default function ModelShowcase(props: ModelShowcaseProps) {
  const [ready, setReady] = useState(false);
  const dpr = useMemo<[number, number]>(() => [1, Math.min(window.devicePixelRatio || 1, 2)], []);

  return (
    <div className={`model-canvas-wrap${ready ? " is-ready" : ""}`}>
      <Canvas
        className="model-canvas"
        dpr={dpr}
        camera={{ fov: 36, position: props.cameraPos, near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: true }}
      >
        <hemisphereLight args={[0xdbe9ff, 0x1a2230, 1.2]} />
        <directionalLight position={[3, 5, 4]} intensity={2.3} />
        <directionalLight position={[-4, -1, -3]} intensity={1.1} color="#5eead4" />
        <Suspense fallback={null}>
          <Scene {...props} onReady={() => setReady(true)} />
        </Suspense>
      </Canvas>
    </div>
  );
}
