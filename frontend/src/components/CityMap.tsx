import { useEffect, useRef, useState, useCallback, useMemo, Suspense } from 'react';
import { createPortal } from 'react-dom';
import L from 'leaflet';
import { Drone, Incident } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Maximize2, Minimize2, X, Activity, Loader2 } from 'lucide-react';

const PUNE_CENTER: [number, number] = [18.5204, 73.8567];
const PUNE_BOUNDS: L.LatLngBoundsExpression = [[18.42, 73.72], [18.62, 73.98]];
const PUNE_MAX_BOUNDS: L.LatLngBoundsExpression = [[18.38, 73.66], [18.66, 74.04]];

interface Props {
  drones: Drone[];
  incidents: Incident[];
  onIncidentClick: (incident: Incident) => void;
}

export function CityMap({ drones, incidents, onIncidentClick }: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const droneMarkersRef = useRef<Map<string, L.Marker>>(new Map());
  const incidentMarkersRef = useRef<Map<string, L.CircleMarker>>(new Map());
  const routeLinesRef = useRef<Map<string, L.Polyline>>(new Map());
  const dispatchMarkersRef = useRef<L.LayerGroup | null>(null);
  const [maximized, setMaximized] = useState(false);
  const [selectedUnit, setSelectedUnit] = useState<number | null>(null);
  const layerControlRef = useRef<L.Control.Layers | null>(null);

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
      const isActive = drone.status === 'en_route' || drone.status === 'on_site';
      const droneIcon = L.divIcon({
        className: '',
        html: `<div style="width:${isActive ? 16 : 12}px;height:${isActive ? 16 : 12}px;border-radius:999px;background:${isActive ? '#fff' : '#666'};border:2px solid ${isActive ? '#fff' : '#333'};box-shadow:${isActive ? '0 0 15px rgba(255,255,255,0.8)' : 'none'}"></div>`,
        iconSize: [isActive ? 16 : 12, isActive ? 16 : 12],
        iconAnchor: [isActive ? 8 : 6, isActive ? 8 : 6],
      });

      if (existing.has(drone.id)) {
        const marker = existing.get(drone.id)!;
        marker.setLatLng([drone.position.lat, drone.position.lng]);
        marker.setIcon(droneIcon);
      } else {
        const marker = L.marker([drone.position.lat, drone.position.lng], { icon: droneIcon, zIndexOffset: 900 }).addTo(map);
        marker.bindPopup(`<div style="font-size:12px;font-family:'IBM Plex Mono',monospace;padding:4px;background:#000;color:#fff"><b>${drone.id.replace('drone_', 'D-')}</b><br/>Status: ${drone.status}<br/>Battery: ${drone.battery.toFixed(0)}%</div>`);
        existing.set(drone.id, marker);
      }
    });
  }, [drones]);

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

    drones.filter((d) => d.status === 'en_route' && d.targetIncidentId).forEach((drone) => {
      const incident = incidents.find((i) => i.id === drone.targetIncidentId);
      if (!incident) return;
      const line = L.polyline([[drone.position.lat, drone.position.lng], [incident.position.lat, incident.position.lng]], {
        color: '#fff', weight: 2, dashArray: '8 6', opacity: 0.6,
      }).addTo(map);
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
                onClick={() => setSelectedUnit(null)}
                className="p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors"
              >
                <X size={18} />
              </button>
            </div>
            
            <div className="pt-12 w-full h-full">
              {/* <Suspense fallback={
                <div className="w-full h-full flex flex-col items-center justify-center gap-4 bg-black/50">
                  <Loader2 className="w-10 h-10 text-white/40 animate-spin" />
                  <span className="text-[10px] font-mono tracking-[0.4em] text-white/40 uppercase">Linking Neural Link...</span>
                </div>
              }>
                <Drone3DView drones={drones.slice(0, 3)} />
              </Suspense> */}
              <div className="w-full h-full flex items-center justify-center text-white/40 font-mono text-[10px] uppercase tracking-widest bg-black/50">
                3D Overlay Offline for Diagnostics
              </div>
            </div>
          </div>
        </div>
      )}

      <div ref={containerRef} className="h-full w-full" />

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
      `}} />
    </div>
  );

  return maximized ? createPortal(mapContent, document.body) : mapContent;
}
