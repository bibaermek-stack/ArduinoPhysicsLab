import * as THREE from "three";

export interface ExplodedPart {
  node: THREE.Object3D;
  original: THREE.Vector3;
  exploded: THREE.Vector3;
  originalRotation: THREE.Euler;
  spinOffset: THREE.Euler;
  label: string | null;
}

/**
 * root-тың әр top-level баласы үшін "жиналған" (original) және "жарылған"
 * (exploded) позицияны есептейді.
 *
 * МАҢЫЗДЫ (алдыңғы vanilla-JS нұсқада расталған bug): node.position — root-тың
 * ЛОКАЛЬ кеңістігінде, ал root-тың өзі fit-scale-ге ие болады. Сондықтан
 * "жарылу" қашықтығы да СОЛ ЛОКАЛЬ бірліктерде есептелуі керек — world-space
 * радиусты (scale-мен көбейтілген) осында пайдалансақ, соңғы world-position
 * scale-мен ЕКІНШІ РЕТ көбейтіліп, бөлшектер камерадан жүздеген есе алыс
 * ұшып кетеді.
 */
export function computeExplodedParts(root: THREE.Object3D, labels: string[]): ExplodedPart[] {
  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  box.getSize(size);
  const radius = Math.max(size.length() * 0.5, 0.001);

  const pieces = root.children.length ? root.children : [root];
  return pieces.map((node, i) => {
    const original = node.position.clone();
    const dir = original.clone();
    if (dir.lengthSq() < 0.0001) {
      dir.set(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5);
    }
    dir.normalize();
    const distance = radius * (1.6 + Math.random() * 1.6);
    const exploded = original.clone().addScaledVector(dir, distance);
    // МАҢЫЗДЫ (расталған bug): GLB-де бөлшектердің көбінде "жиналған"
    // бастапқы бұрылысы (0,0,0) ЕМЕС (мыс. robot_arm/instax-тың барлық
    // балаларында -90° X бұрылысы бар — gltf-transform-ның Z-up→Y-up
    // түзетуі). Бұл бұрылысты САҚТАП, "жиналу" анимациясы соған қайтуы
    // керек — әйтпесе бүкіл модель толық жиналған кезде 90°-қа "аударылып"
    // тұрады (robot қол бүйіріне құлаған сияқты көрінген, расталған).
    const originalRotation = node.rotation.clone();
    const spinOffset = new THREE.Euler(
      (Math.random() - 0.5) * Math.PI * 1.4,
      (Math.random() - 0.5) * Math.PI * 1.4,
      (Math.random() - 0.5) * Math.PI * 1.4
    );
    return { node, original, exploded, originalRotation, spinOffset, label: labels[i] ?? null };
  });
}

/** root-ты бірлік өлшемге ("targetSize" диаметріне) сыйдырып, центрлейді. */
export function fitAndCenter(root: THREE.Object3D, targetSize = 2.6): number {
  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);
  const scale = targetSize / Math.max(size.x, size.y, size.z, 0.001);
  root.scale.setScalar(scale);
  root.position.sub(center.multiplyScalar(scale));
  return scale;
}
