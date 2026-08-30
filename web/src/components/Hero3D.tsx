import { Suspense, useEffect, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { fitAndCenter } from "../lib/explode";
import { isTouchDevice, prefersReducedMotion } from "../lib/env";

const GLB_URL = "/static/models/instax.glb";

// Тышқан позициясы React state-ке ЕМЕС, plain объектіге жазылады — әр
// pointermove-де re-render болмас үшін (§14 "React state-ті әр frame сайын
// update етпе").
const pointer = { x: 0, y: 0 };

function HeroModel() {
  const { scene } = useGLTF(GLB_URL, true);
  const groupRef = useRef<THREE.Group>(null);
  const { camera } = useThree();

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    const root = scene.clone(true);
    fitAndCenter(root, 2.2);
    group.add(root);
    camera.position.set(0, 1.8, 5.2);
    camera.lookAt(0, 0, 0);
    return () => {
      group.remove(root);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene]);

  useFrame((_, delta) => {
    const group = groupRef.current;
    if (!group) return;
    if (!prefersReducedMotion) {
      group.rotation.y += delta * 0.18;
    }
    if (!isTouchDevice) {
      // Smooth parallax tilt — damped lerp (кадр ұзақтығына тәуелсіз).
      const targetX = pointer.y * 0.18;
      const targetZ = -pointer.x * 0.18;
      group.rotation.x = THREE.MathUtils.damp(group.rotation.x, targetX, 4, delta);
      group.rotation.z = THREE.MathUtils.damp(group.rotation.z, targetZ, 4, delta);
    }
  });

  return <group ref={groupRef} />;
}

export default function Hero3D() {
  useEffect(() => {
    if (isTouchDevice) return;
    const onMove = (e: PointerEvent) => {
      pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  return (
    <Canvas
      className="hero-canvas"
      dpr={[1, Math.min(window.devicePixelRatio || 1, 2)]}
      camera={{ fov: 34, position: [0, 1.8, 5.2], near: 0.1, far: 100 }}
      gl={{ antialias: true, alpha: true }}
    >
      <hemisphereLight args={[0xdbe9ff, 0x1a2230, 1.3]} />
      <directionalLight position={[3, 5, 4]} intensity={2.4} />
      <directionalLight position={[-4, -1, -3]} intensity={1.1} color="#5eead4" />
      <Suspense fallback={null}>
        <HeroModel />
      </Suspense>
    </Canvas>
  );
}
