import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

function initDroneScene(container: HTMLDivElement, modelUrl: string) {
  const width = container.clientWidth;
  const height = container.clientHeight;

  const scene = new THREE.Scene();
  scene.background = null; // Transparent background

  const camera = new THREE.PerspectiveCamera(30, width / height, 0.1, 1000);
  camera.position.set(0, 1.2, 4);
  camera.lookAt(0, 0, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  // High quality lighting without shadows (for performance in rows)
  const ambientLight = new THREE.AmbientLight(0xffffff, 2);
  scene.add(ambientLight);

  const topLight = new THREE.DirectionalLight(0xffffff, 2);
  topLight.position.set(0, 10, 5);
  scene.add(topLight);

  const blueFill = new THREE.PointLight(0x00a8ff, 4, 10);
  blueFill.position.set(0, -2, 0);
  scene.add(blueFill);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.5;

  const loader = new GLTFLoader();
  let drone: THREE.Group | null = null;

  loader.load(modelUrl, (gltf) => {
    drone = gltf.scene;
    const box = new THREE.Box3().setFromObject(drone);
    const center = box.getCenter(new THREE.Vector3());
    drone.position.sub(center);
    
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const scale = 2.8 / maxDim;
    drone.scale.setScalar(scale);
    
    drone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        if (mesh.material instanceof THREE.MeshStandardMaterial) {
          mesh.material.roughness = 0.3;
          mesh.material.metalness = 0.7;
        }
      }
    });

    scene.add(drone);
  });

  let frameId: number;
  const animate = () => {
    frameId = requestAnimationFrame(animate);
    controls.update();
    if (drone) {
      drone.position.y = Math.sin(Date.now() * 0.0025) * 0.1;
    }
    renderer.render(scene, camera);
  };

  animate();

  const handleResize = () => {
    if (!container) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  };

  window.addEventListener('resize', handleResize);

  return () => {
    window.removeEventListener('resize', handleResize);
    cancelAnimationFrame(frameId);
    renderer.dispose();
    controls.dispose();
    if (container.contains(renderer.domElement)) {
      container.removeChild(renderer.domElement);
    }
  };
}

export function Drone3DView({ drones }: { drones: { battery: number; id: string; status?: string }[] }) {
  const droneRefs = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];

  useEffect(() => {
    const cleanups: (() => void)[] = [];
    droneRefs.forEach((ref, i) => {
      if (ref.current && i < drones.length) {
        const cleanup = initDroneScene(ref.current, "/Drone.glb");
        cleanups.push(cleanup);
      }
    });
    return () => cleanups.forEach(cleanup => cleanup());
  }, [drones.length]);

  return (
    <div className="w-full h-full flex flex-col gap-4 bg-black/40 p-4 rounded-2xl border border-white/5 overflow-hidden">
      {drones.slice(0, 3).map((drone, idx) => (
        <div key={drone.id} className="flex-1 flex items-center bg-white/[0.03] border border-white/5 rounded-xl overflow-hidden hover:bg-white/[0.06] transition-colors group">
          {/* 3D Model Column */}
          <div className="w-1/3 h-full relative border-r border-white/5">
            <div ref={droneRefs[idx]} className="w-full h-full" />
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-r from-transparent to-black/20" />
          </div>

          {/* Telemetry Column */}
          <div className="flex-1 px-8 flex flex-col justify-center gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-[0.4em]">Hardware Identifier</span>
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-[0.4em]">Operational Status</span>
            </div>
            <div className="flex items-center justify-between">
              <h4 className="text-2xl font-black text-white tracking-widest uppercase font-mono">
                {drone.id.replace('drone_', 'UNIT-')}
              </h4>
              <div className="flex items-center gap-3 bg-white/10 px-4 py-1.5 rounded-full border border-white/10">
                <div className={`w-2 h-2 rounded-full animate-pulse ${drone.status === 'idle' ? 'bg-white/40' : 'bg-green-500 shadow-[0_0_8px_#22c55e]'}`} />
                <span className="text-xs font-bold text-white tracking-widest uppercase">
                  {drone.status || 'ACTIVE'}
                </span>
              </div>
            </div>

            {/* Battery Metrics */}
            <div className="mt-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em]">Power Capacity</span>
                <span className={`text-sm font-bold font-mono ${drone.battery < 20 ? 'text-red-500' : 'text-white'}`}>
                  {drone.battery.toFixed(1)}%
                </span>
              </div>
              <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
                <div 
                  className={`h-full transition-all duration-1000 ${drone.battery < 20 ? 'bg-red-500' : 'bg-white/80 shadow-[0_0_10px_rgba(255,255,255,0.4)]'}`}
                  style={{ width: `${drone.battery}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
