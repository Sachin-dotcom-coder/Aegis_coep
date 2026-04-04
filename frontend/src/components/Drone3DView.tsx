import { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { useGLTF, PerspectiveCamera, OrbitControls, Environment, ContactShadows } from '@react-three/drei';
import * as THREE from 'three';

function Model({ url, rotationSpeed = 0.5 }: { url: string; rotationSpeed?: number }) {
  const { scene } = useGLTF(url);
  const group = useRef<THREE.Group>(null);

  useFrame((state, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * rotationSpeed;
    }
  });

  return (
    <primitive 
      ref={group}
      object={scene.clone()} 
      scale={2.2} 
      position={[0, -0.2, 0]} 
    />
  );
}

function SceneView({ url }: { url: string }) {
  return (
    <Canvas shadows dpr={[1, 2]} camera={{ position: [0, 1.5, 4], fov: 40 }}>
      <ambientLight intensity={0.7} />
      <pointLight position={[10, 10, 10]} intensity={1.5} />
      <spotLight 
        position={[-10, 10, 10]} 
        angle={0.15} 
        penumbra={1} 
        intensity={2} 
        castShadow 
        shadow-mapSize={[1024, 1024]}
      />
      
      <Model url={url} rotationSpeed={0.3} />
      
      <OrbitControls 
        enablePan={false} 
        enableZoom={false} 
        minPolarAngle={Math.PI / 3} 
        maxPolarAngle={Math.PI / 1.5} 
      />
      
      <Environment preset="night" />
      <ContactShadows 
        position={[0, -0.8, 0]} 
        opacity={0.4} 
        scale={10} 
        blur={2} 
        far={2} 
      />
    </Canvas>
  );
}

export function Drone3DView({ drones }: { drones: { battery: number; id: string }[] }) {
  return (
    <div className="w-full h-full relative bg-black/40 rounded-xl overflow-hidden border border-white/10">
      <div className="absolute top-4 left-4 z-10 space-y-2 pointer-events-none">
        {drones.map((drone, idx) => (
          <div key={drone.id} className="flex items-center gap-3 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10">
            <div className="w-2 h-2 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)]" />
            <span className="text-[10px] font-mono text-white/60 tracking-wider">UNIT-${idx + 1}</span>
            <span className={`text-xs font-bold font-mono ${drone.battery < 20 ? 'text-red-500 animate-pulse' : 'text-white'}`}>
              {drone.battery.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>

      <div className="w-full h-full">
        <div className="grid grid-cols-3 h-full">
          {drones.slice(0, 3).map((drone) => (
            <div key={drone.id} className="h-full border-r border-white/5 last:border-0 relative">
              <div className="absolute inset-0 flex items-center justify-center -z-0">
                <div className="w-full h-full opacity-20 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.1)_0,transparent_70%)]" />
              </div>
              <div className="w-full h-full relative z-10">
                <SceneView url="/Drone.glb" />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="absolute bottom-4 right-4 z-10 pointer-events-none text-[8px] font-mono text-white/20 uppercase tracking-[0.3em]">
        Tactical 3D Preview Active
      </div>
    </div>
  );
}
