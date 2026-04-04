import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import L from 'leaflet';
import { Drone, Incident } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Maximize2, Minimize2, X, Activity, Loader2, Scan, ShieldAlert, Search, Target, ArrowBigUp, ArrowBigDown, ArrowBigLeft, ArrowBigRight, Plus, Minus } from 'lucide-react';
import React, { Suspense } from 'react';
import { Drone3DView } from './Drone3DView';

const PUNE_CENTER: [number, number] = [18.5204, 73.8567];
const PUNE_BOUNDS: L.LatLngBoundsExpression = [[18.42, 73.72], [18.62, 73.98]];
const PUNE_MAX_BOUNDS: L.LatLngBoundsExpression = [[18.38, 73.66], [18.66, 74.04]];

interface Props {
  drones: Drone[];
  incidents: Incident[];
  onIncidentClick: (incident: Incident) => void;
  onManualDispatch: (lat: number, lng: number) => void;
  onAbort: (droneId: string) => void;
  activeLiveFeed: string | null;
  setActiveLiveFeed: (id: string | null) => void;
  videoMaximized: boolean;
  setVideoMaximized: (val: boolean) => void;
}

export function CityMap({ 
  drones, 
  incidents, 
  onIncidentClick, 
  onManualDispatch, 
  onAbort,
  activeLiveFeed,
  setActiveLiveFeed,
  videoMaximized,
  setVideoMaximized
}: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const droneMarkersRef = useRef<Map<string, L.Marker>>(new Map());
  const incidentMarkersRef = useRef<Map<string, L.CircleMarker>>(new Map());
  const routeLinesRef = useRef<Map<string, L.Polyline>>(new Map());
  const dispatchMarkersRef = useRef<L.LayerGroup | null>(null);
  const [maximized, setMaximized] = useState(false);
  const [selectedUnit, setSelectedUnit] = useState<number | null>(null);
  const layerControlRef = useRef<L.Control.Layers | null>(null);

  const [videoZoom, setVideoZoom] = useState(1.5);
  const [videoOffset, setVideoOffset] = useState({ x: 0, y: 0 });

  // Auto-detect drones on site for live feed alert
  const onSiteDrones = drones.filter(d => d.status === 'on_site');

  const fitMapToPune = useCallback(() => {
    mapRef.current?.fitBounds(PUNE_BOUNDS, {
      padding: [24, 24],
      maxZoom: 11,
      animate: false,
    });
  }, []);

  // Initialize or Re-initialize map
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!containerRef.current) return;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }

      const baseMaps = {
        "2D Standard": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          className: 'map-tile-dark',
          attribution: '&copy; OpenStreetMap'
        }),
        "Satellite": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          attribution: 'Tiles &copy; Esri'
        }),
        "Terrain": L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
          attribution: 'Tiles &copy; OpenTopoMap'
        })
      };

      const map = L.map(containerRef.current, {
        zoomControl: true,
        center: PUNE_CENTER,
        zoom: 11,
        minZoom: 10,
        maxZoom: 18,
        maxBounds: PUNE_MAX_BOUNDS,
        maxBoundsViscosity: 1,
        layers: [baseMaps["2D Standard"]]
      });

      layerControlRef.current = L.control.layers(baseMaps, null, { position: 'bottomleft' }).addTo(map);
      const dispatchGroup = L.layerGroup().addTo(map);
      dispatchMarkersRef.current = dispatchGroup;

      DISPATCH_ZONES.forEach((zone, idx) => {
        L.circle([zone.position.lat, zone.position.lng], {
          radius: 600 * zone.riskMultiplier,
          color: '#ffffff',
          fillColor: '#ffffff',
          fillOpacity: 0.05,
          weight: 1,
          dashArray: '6 4',
          opacity: 0.3,
        }).addTo(dispatchGroup);

        const baseIcon = L.divIcon({
          className: '',
          html: `<div style="display:flex;flex-direction:column;align-items:center;gap:4px;transform:translateY(-6px)">
            <div style="width:38px;height:38px;display:flex;align-items:center;justify-content:center;background:#000;border:2px solid #fff;border-radius:10px;font-size:10px;font-family:'Space Grotesk',sans-serif;font-weight:700;color:#fff;box-shadow:0 6px 18px rgba(0,0,0,0.8)">D${idx + 1}</div>
            <div style="padding:2px 6px;border-radius:999px;background:#000;border:1px solid #333;font-size:9px;line-height:1;font-family:'IBM Plex Mono',monospace;color:#fff;white-space:nowrap">${zone.name}</div>
          </div>`,
          iconSize: [110, 56],
          iconAnchor: [19, 19],
        });

        const marker = L.marker([zone.position.lat, zone.position.lng], { icon: baseIcon, zIndexOffset: 1000 }).addTo(dispatchGroup);

        marker.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          setSelectedUnit(idx + 1);
        });

        marker.bindTooltip(`Dispatch Unit ${idx + 1} Status: ONLINE`, {
          permanent: false,
          direction: 'top',
          className: 'custom-tooltip'
        });
      });

      mapRef.current = map;
      droneMarkersRef.current.clear();
      incidentMarkersRef.current.clear();
      routeLinesRef.current.clear();
      map.invalidateSize();
      fitMapToPune();
    }, 50);

    return () => {
      clearTimeout(timer);
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [maximized, fitMapToPune]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const existing = droneMarkersRef.current;
    const currentIds = new Set(drones.map((d) => d.id));
    existing.forEach((m, id) => { if (!currentIds.has(id)) { m.remove(); existing.delete(id); } });

    drones.forEach((drone) => {
      // Glow/Highlight is ONLY for mission-active drones
      const isOnMission = drone.status === 'en_route' || drone.status === 'on_site';
      const isMoving = drone.status === 'en_route' || drone.status === 'recalled';
      const isOnSite = drone.status === 'on_site';
      const isRecalled = drone.status === 'recalled';

      const incident = incidents.find(i => i.id === drone.targetIncidentId);
      
      // Calculate rotation toward target if moving (incident for en_route, base for recalled)
      let rotation = 0;
      if (isMoving) {
        const targetPos = isRecalled ? drone.basePosition : incident?.position;
        if (targetPos) {
          rotation = Math.atan2(
            targetPos.lat - drone.position.lat,
            targetPos.lng - drone.position.lng
          ) * (180 / Math.PI);
        }
      }

      const droneIcon = L.divIcon({
        className: '',
        html: `<div style="position:relative; width:36px; height:36px; transform: rotate(${rotation}deg); transition: transform 0.5s ease;">
          <img src="/drone_icon.png" style="width:100%; height:100%; filter: brightness(${isOnMission ? 1.2 : 0.4}) drop-shadow(0 0 8px ${isOnSite ? 'rgba(255,80,80,1)' : isOnMission ? 'rgba(255,255,255,1)' : 'rgba(0,0,0,0)'});" />
          ${isOnMission ? `<div style="position:absolute; top:0; left:0; width:100%; height:100%; border-radius:50%; border:2px solid ${isOnSite ? '#ff4444' : '#fff'}; box-shadow:0 0 15px ${isOnSite ? '#ff4444' : '#fff'}; animation: pulse 1.5s infinite; opacity: 0.2;"></div>` : ''}
          <div style="position:absolute;bottom:-24px;left:50%;transform:translateX(-50%) rotate(${-rotation}deg);white-space:nowrap;background:rgba(0,0,0,0.8);border:1px solid rgba(255,255,255,0.2);backdrop-filter:blur(4px);border-radius:4px;padding:2px 6px;font-size:10px;font-weight:900;font-family:'IBM Plex Mono',monospace;color:#fff">${drone.id}</div>
        </div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      });

      if (existing.has(drone.id)) {
        const marker = existing.get(drone.id)!;
        marker.setLatLng([drone.position.lat, drone.position.lng]);
        marker.setIcon(droneIcon);
      } else {
        const marker = L.marker([drone.position.lat, drone.position.lng], { icon: droneIcon, zIndexOffset: 900 }).addTo(map);
        marker.bindPopup(`<div style="font-size:12px;font-family:'IBM Plex Mono',monospace;padding:8px;background:#000;color:#fff"><b>${drone.id}</b><br/>Status: ${drone.status.toUpperCase()}<br/>Battery: ${drone.battery.toFixed(0)}%</div>`);
        existing.set(drone.id, marker);
      }
    });
  }, [drones, incidents]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const existing = incidentMarkersRef.current;
    const active = incidents.filter((i) => !['resolved', 'rejected', 'logged'].includes(i.status));
    const currentIds = new Set(active.map((i) => i.id));
    existing.forEach((m, id) => { if (!currentIds.has(id)) { m.remove(); existing.delete(id); } });

    active.forEach((incident) => {
      const isCritical = incident.severity >= 8;
      if (existing.has(incident.id)) {
        existing.get(incident.id)!.setLatLng([incident.position.lat, incident.position.lng]);
        return;
      }
      const marker = L.circleMarker([incident.position.lat, incident.position.lng], {
        radius: isCritical ? 11 : 8,
        color: '#fff',
        fillColor: '#fff',
        fillOpacity: isCritical ? 1 : 0.6,
        weight: isCritical ? 4 : 2,
      }).addTo(map);
      marker.on('click', () => onIncidentClick(incident));
      marker.bindPopup(`<div style="font-size:12px;font-family:'IBM Plex Mono',monospace;padding:4px;background:#000;color:#fff"><b>${incident.type.replace(/_/g, ' ').toUpperCase()}</b><br/>Confidence: ${(incident.detectionConfidence * 100).toFixed(0)}%<br/>Priority: ${incident.priorityScore.toFixed(1)}</div>`);
      existing.set(incident.id, marker);
    });
  }, [incidents, onIncidentClick]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const existing = routeLinesRef.current;
    existing.forEach((line) => line.remove());
    existing.clear();

    drones
      .filter((d) => d.status === 'en_route' && d.targetIncidentId)
      .forEach((drone) => {
        const incident = incidents.find((i) => i.id === drone.targetIncidentId);
        if (!incident) return;

        // Trace of the target path (faded static line)
        L.polyline(
          [[drone.position.lat, drone.position.lng], [incident.position.lat, incident.position.lng]],
          { color: '#ffffff', weight: 1, opacity: 0.1 }
        ).addTo(map);

        // Animated FLOWING line to the target
        const line = L.polyline(
          [[drone.position.lat, drone.position.lng], [incident.position.lat, incident.position.lng]],
          { 
            color: '#ffffff', 
            weight: 2, 
            dashArray: '12 12', 
            className: 'flowing-route', // Dynamic CSS animation
            opacity: 0.7 
          }
        ).addTo(map);
        existing.set(drone.id, line);
      });
  }, [drones, incidents]);

  const mapContent = (
    <div
      className={`border border-border bg-black ${maximized
        ? 'fixed inset-0 z-[10000] w-screen h-screen'
        : 'relative h-full w-full rounded-lg overflow-hidden'
        }`}
    >
      <button
        onClick={() => setMaximized(!maximized)}
        className={`absolute top-6 right-6 rounded-xl border border-white/20 bg-black/80 backdrop-blur-md p-4 text-white shadow-2xl transition-all hover:scale-110 active:scale-95 ${maximized ? 'z-[10001]' : 'z-[1001]'
          }`}
      >
        {maximized ? <Minimize2 size={32} /> : <Maximize2 size={24} />}
      </button>

      {maximized && (
        <div className="absolute top-8 left-1/2 -translate-x-1/2 z-[10001] pointer-events-none">
          <div className="bg-black/90 border border-white/20 px-10 py-3 rounded-full shadow-2xl backdrop-blur-xl">
            <span className="text-2xl font-black tracking-[0.3em] text-white uppercase font-mono">Map of Pune</span>
          </div>
        </div>
      )}

      <div ref={containerRef} className="h-full w-full absolute inset-0 z-0" />

      {/* Live Feed Deployment Alerts */}
      {onSiteDrones.length > 0 && !activeLiveFeed && (
        <div className="absolute top-8 left-1/2 -translate-x-1/2 z-[1001] animate-in slide-in-from-top-10 duration-700">
          <div className="bg-black/90 backdrop-blur-3xl border border-red-500/40 p-4 rounded-2xl flex items-center shadow-[0_0_50px_rgba(255,0,0,0.3)]">
            <div className="flex flex-col border-r border-white/10 pr-6 mr-6 transition-all">
              <span className="text-sm font-black tracking-widest text-white uppercase italic font-mono leading-none">Objective Reached</span>
              <span className="text-[10px] font-mono tracking-[0.3em] text-red-500 uppercase mt-1 font-bold">Unit {onSiteDrones[0].id.replace('drone_', 'D-')}</span>
            </div>
            <button 
              onClick={() => setActiveLiveFeed(onSiteDrones[0].id)}
              className="px-6 py-2 bg-red-600 hover:bg-white text-white hover:text-black transition-all duration-300 rounded-xl shadow-xl flex items-center gap-3 active:scale-95"
            >
              <Scan size={18} />
              <span className="text-[10px] font-black tracking-[0.3em] uppercase underline decoration-white/20 underline-offset-4">Bridge Link</span>
            </button>
          </div>
        </div>
      )}

      {/* Live Video Feed Drilldown Overlay */}
      {activeLiveFeed && (
        <div className={`${videoMaximized ? 'fixed inset-0 z-[40000] p-10 bg-black/90 backdrop-blur-xl animate-in zoom-in-95 duration-500' : 'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[2001] w-[800px] h-[500px] animate-in zoom-in-75 duration-500'}`}>
          <div className="relative w-full h-full bg-black border-4 border-white/10 rounded-3xl overflow-hidden shadow-[0_50px_150px_rgba(0,0,0,1)]">
            {/* Tactical Camera HUD Overlay */}
            <div className="absolute inset-0 z-20 pointer-events-none flex flex-col justify-between p-10">
              <div className="flex items-start justify-between">
                <div className="flex flex-col">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 bg-red-600 rounded-full animate-ping" />
                    <span className="text-2xl font-black tracking-[0.4em] text-white uppercase font-mono">FEED LINK: {activeLiveFeed.replace('drone_', 'D-')}</span>
                  </div>
                  <span className="text-sm font-mono text-white/40 tracking-[0.3em] uppercase mt-1">Resolution: 4K UHD // Aegis Neuralink Protocol</span>
                </div>
                <div className="flex items-center gap-6">
                  <div className="flex items-center gap-3 px-6 py-2 bg-white/5 border border-white/20 rounded-xl">
                    <span className="text-xl font-mono text-white font-black">REC</span>
                    <div className="w-3 h-3 bg-red-600 rounded-full animate-pulse" />
                  </div>
                </div>
              </div>

              <div className="flex items-end justify-between">
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-mono text-white/60 uppercase tracking-[0.4em]">Signal Integrity:</span>
                    <div className="flex gap-1">
                      {[0, 1, 2, 3, 4].map(i => <div key={i} className="w-2 h-6 bg-green-500 rounded-sm" />)}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.5em]">Aegis Ground Optic Link [SECURE_ENCRYPTED]</span>
                </div>
              </div>

              <div className="absolute inset-0 border-[40px] border-black/10 opacity-40 pointer-events-none" style={{ background: 'repeating-linear-gradient(transparent, transparent 2px, rgba(255,255,255,0.02) 2px, rgba(255,255,255,0.02) 4px)' }} />
            </div>

            {/* Close / Controls */}
            {/* Close / Controls */}
            <div className="absolute top-8 right-8 z-30 flex items-center gap-4">
              {/* Tactical Reset */}
              <button 
                onClick={() => {
                  setVideoZoom(1.5);
                  setVideoOffset({ x: 0, y: 0 });
                }}
                className="group flex items-center gap-3 bg-white/10 hover:bg-white px-6 py-3 rounded-2xl border border-white/20 backdrop-blur-xl transition-all shadow-2xl"
              >
                <Activity size={20} className="text-white group-hover:text-black" />
                <span className="text-xs font-black tracking-widest uppercase text-white group-hover:text-black">Reset Gimbal</span>
              </button>

              <button 
                onClick={() => {
                  if (activeLiveFeed) {
                    onAbort(activeLiveFeed);
                    setActiveLiveFeed(null);
                    setVideoMaximized(false);
                    setVideoZoom(1.5); // Reset stats on close
                    setVideoOffset({ x: 0, y: 0 });
                  }
                }}
                className="group flex items-center gap-3 bg-red-600/20 hover:bg-red-600 px-6 py-3 rounded-2xl border border-red-500/40 backdrop-blur-xl transition-all shadow-2xl"
              >
                <ShieldAlert size={20} className="text-red-500 group-hover:text-white" />
                <span className="text-xs font-black tracking-widest uppercase text-red-500 group-hover:text-white">Abort Mission</span>
              </button>

              <button 
                onClick={() => setVideoMaximized(!videoMaximized)}
                className="p-3 bg-white/10 hover:bg-white hover:text-black rounded-2xl border border-white/10 backdrop-blur-xl transition-all shadow-2xl"
              >
                {videoMaximized ? <Minimize2 size={24} /> : <Maximize2 size={24} />}
              </button>
              <button 
                onClick={() => {
                  setActiveLiveFeed(null);
                  setVideoMaximized(false);
                  setVideoZoom(1.5);
                  setVideoOffset({ x: 0, y: 0 });
                }}
                className="p-3 bg-white/10 hover:bg-red-600 rounded-2xl border border-white/10 backdrop-blur-xl transition-all shadow-2xl"
              >
                <X size={24} />
              </button>
            </div>

            {/* Gimbal Controls HUD cluster - Bottom Right */}
            <div className="absolute bottom-8 right-8 z-30 flex items-center gap-6 bg-black/60 backdrop-blur-2xl px-6 py-4 rounded-3xl border border-white/10 shadow-2xl animate-in fade-in slide-in-from-right-10 duration-700">
               {/* 4-way Pan */}
               <div className="grid grid-cols-3 gap-1">
                  <div />
                  <button onClick={() => setVideoOffset(p => ({ ...p, y: p.y + (15 / videoZoom) }))} className="p-2 bg-white/5 hover:bg-white hover:text-black rounded-lg transition-all"><ArrowBigUp size={16} /></button>
                  <div />
                  <button onClick={() => setVideoOffset(p => ({ ...p, x: p.x + (15 / videoZoom) }))} className="p-2 bg-white/5 hover:bg-white hover:text-black rounded-lg transition-all"><ArrowBigLeft size={16} /></button>
                  <div className="bg-white/10 rounded-sm" />
                  <button onClick={() => setVideoOffset(p => ({ ...p, x: p.x - (15 / videoZoom) }))} className="p-2 bg-white/5 hover:bg-white hover:text-black rounded-lg transition-all"><ArrowBigRight size={16} /></button>
                  <div />
                  <button onClick={() => setVideoOffset(p => ({ ...p, y: p.y - (15 / videoZoom) }))} className="p-2 bg-white/5 hover:bg-white hover:text-black rounded-lg transition-all"><ArrowBigDown size={16} /></button>
                  <div />
               </div>

               <div className="h-12 w-[1px] bg-white/10" />

               {/* Zoom Control */}
               <div className="flex flex-col gap-2">
                  <button onClick={() => setVideoZoom(p => Math.min(4, p + 0.2))} className="p-2 bg-white/5 hover:bg-white hover:text-black rounded-lg transition-all shadow-lg"><Plus size={16} /></button>
                  <div className="flex flex-col items-center">
                    <span className="text-[8px] font-black text-white/30 tracking-widest uppercase">Zoom</span>
                    <span className="text-sm font-black text-white font-mono">{videoZoom.toFixed(1)}x</span>
                  </div>
                  <button onClick={() => setVideoZoom(p => Math.max(1, p - 0.2))} className="p-2 bg-white/5 hover:bg-white hover:text-black rounded-lg transition-all shadow-lg"><Minus size={16} /></button>
               </div>
            </div>

            <div className="w-full h-full overflow-hidden">
               <video
                 autoPlay
                 loop
                 muted
                 playsInline
                 src="/video.mp4"
                 style={{ 
                   transformOrigin: 'center',
                   transform: `scale(${videoZoom}) translate(${videoOffset.x}px, ${videoOffset.y}px)`,
                   transition: 'transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1)'
                 }}
                 className="w-full h-full object-cover opacity-80"
               />
            </div>
          </div>
        </div>
      )}

      {/* Selected Unit 3D Tactical Overlay */}
      {selectedUnit !== null && (
        <div className={`absolute bottom-10 right-10 ${maximized ? 'w-[600px] h-[350px]' : 'w-[400px] h-[250px]'} z-[10002] transition-all animate-in fade-in slide-in-from-bottom-4 duration-500`}>
          <div className="relative w-full h-full glass-panel bg-black/90 border-2 border-white/20 rounded-2xl overflow-hidden shadow-[0_30px_100px_rgba(0,0,0,0.8)]">
            <div className="absolute top-0 left-0 right-0 h-12 bg-white/5 border-b border-white/10 flex items-center justify-between px-6 z-20">
              <div className="flex items-center gap-3">
                <Activity size={16} className="text-white/60 animate-pulse" />
                <span className="text-xs font-black tracking-[0.2em] text-white uppercase font-mono">Tactical Unit D${selectedUnit} View</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedUnit(null);
                }}
                className="p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors pointer-events-auto"
              >
                <X size={18} />
              </button>
            </div>

            <div className="pt-12 w-full h-full relative z-10">
              <Suspense fallback={
                <div className="w-full h-full flex flex-col items-center justify-center gap-4 bg-black/80">
                  <Loader2 className="w-10 h-10 text-white/40 animate-spin" />
                  <span className="text-[10px] font-mono tracking-[0.4em] text-white/40 uppercase animate-pulse">Syncing Drone Neuralink...</span>
                </div>
              }>
                <Drone3DView drones={drones.slice(0, 3)} />
              </Suspense>
            </div>
          </div>
        </div>
      )}

      <style dangerouslySetInnerHTML={{
        __html: `
        .leaflet-container { background: #000 !important; cursor: crosshair !important; height: 100% !important; width: 100% !important; }
        .map-tile-dark { filter: grayscale(1) invert(1) brightness(0.4) contrast(1.2) !important; }
        .leaflet-control-layers { 
          background: rgba(0,0,0,0.85) !important; 
          backdrop-filter: blur(12px) !important;
          color: #fff !important; 
          border: 1px solid rgba(255,255,255,0.2) !important;
          font-family: 'IBM Plex Mono', monospace !important;
          border-radius: 12px !important;
          padding: 12px !important;
          box-shadow: 0 10px 40px rgba(0,0,0,0.5) !important;
        }
        .leaflet-control-zoom { border: none !important; margin-left: 20px !important; margin-bottom: 20px !important; }
        .leaflet-control-zoom a { 
          background: rgba(0,0,0,0.85) !important; 
          color: #fff !important; 
          border: 1px solid rgba(255,255,255,0.2) !important;
          width: 44px !important;
          height: 44px !important;
          line-height: 44px !important;
          font-size: 20px !important;
          border-radius: 8px !important;
          margin-bottom: 4px !important;
        }
        .leaflet-popup-content-wrapper { 
          background: #000 !important; 
          color: #fff !important; 
          border: 1px solid #444 !important;
          border-radius: 12px !important;
        }
        .leaflet-popup-tip { background: #000 !important; }
        .custom-tooltip {
          background: rgba(0,0,0,0.9) !important;
          border: 1px solid rgba(255,255,255,0.2) !important;
          color: #fff !important;
          font-family: 'IBM Plex Mono', monospace !important;
          font-size: 10px !important;
          padding: 8px 12px !important;
          border-radius: 8px !important;
          box-shadow: 0 10px 30px rgba(0,0,0,0.5) !important;
        }
        .flowing-route {
          stroke-dasharray: 12, 12;
          animation: flow 1s linear infinite;
          filter: drop-shadow(0 0 6px rgba(255,255,255,0.4));
        }
        @keyframes flow {
          from { stroke-dashoffset: 24; }
          to { stroke-dashoffset: 0; }
        }
        @keyframes pulse {
          0% { transform: scale(1); opacity: 0.5; }
          50% { transform: scale(1.6); opacity: 0; }
          100% { transform: scale(1); opacity: 0.5; }
        }
      `}} />
    </div>
  );

  return maximized ? createPortal(mapContent, document.body) : mapContent;
}
