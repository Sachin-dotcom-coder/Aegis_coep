import { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import { Drone, Incident } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Maximize2, Minimize2 } from 'lucide-react';

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

  const fitMapToPune = useCallback(() => {
    mapRef.current?.fitBounds(PUNE_BOUNDS, {
      padding: [24, 24],
      maxZoom: 11,
      animate: false,
    });
  }, []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      zoomControl: true,
      center: PUNE_CENTER,
      zoom: 11,
      minZoom: 10,
      maxZoom: 17,
      maxBounds: PUNE_MAX_BOUNDS,
      maxBoundsViscosity: 1,
      inertia: false,
      zoomAnimation: false,
      fadeAnimation: false,
      markerZoomAnimation: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '',
    }).addTo(map);

    const dispatchGroup = L.layerGroup().addTo(map);
    dispatchMarkersRef.current = dispatchGroup;

    DISPATCH_ZONES.forEach((zone, idx) => {
      L.circle([zone.position.lat, zone.position.lng], {
        radius: 600 * zone.riskMultiplier,
        color: 'hsl(var(--foreground))',
        fillColor: 'hsl(var(--foreground))',
        fillOpacity: 0.05,
        weight: 1,
        dashArray: '6 4',
        opacity: 0.3,
      }).addTo(dispatchGroup);

      const baseIcon = L.divIcon({
        className: '',
        html: `<div style="display:flex;flex-direction:column;align-items:center;gap:4px;transform:translateY(-6px)">
          <div style="width:38px;height:38px;display:flex;align-items:center;justify-content:center;background:hsl(var(--background));border:2px solid hsl(var(--foreground));border-radius:10px;font-size:10px;font-family:'Space Grotesk',sans-serif;font-weight:700;color:hsl(var(--foreground));box-shadow:0 6px 18px rgba(0,0,0,0.45)">D${idx + 1}</div>
          <div style="padding:2px 6px;border-radius:999px;background:hsl(var(--background));border:1px solid hsl(var(--border));font-size:9px;line-height:1;font-family:'IBM Plex Mono',monospace;color:hsl(var(--foreground));white-space:nowrap">${zone.name}</div>
        </div>`,
        iconSize: [110, 56],
        iconAnchor: [19, 19],
      });

      L.marker([zone.position.lat, zone.position.lng], { icon: baseIcon, zIndexOffset: 1000 })
        .bindPopup(`<div style="font-size:11px;font-family:'IBM Plex Mono',monospace;padding:4px">
          <b>Dispatch Unit ${idx + 1}</b><br/>
          <span style="opacity:0.7">${zone.name}</span><br/>
          Risk: ×${zone.riskMultiplier} | Reliability: ${(zone.reliability * 100).toFixed(0)}%
        </div>`)
        .addTo(dispatchGroup);
    });

    mapRef.current = map;

    requestAnimationFrame(() => {
      map.invalidateSize({ pan: false });
      fitMapToPune();
    });

    const resizeObserver = new ResizeObserver(() => {
      if (mapRef.current) {
        mapRef.current.invalidateSize({ animate: false });
      }
    });
    
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    const handleWindowResize = () => {
      map.invalidateSize({ pan: false });
      fitMapToPune();
    };

    window.addEventListener('resize', handleWindowResize);

    return () => {
      window.removeEventListener('resize', handleWindowResize);
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      dispatchMarkersRef.current = null;
    };
  }, [fitMapToPune]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const timer = window.setTimeout(() => {
      map.invalidateSize({ pan: false });
      fitMapToPune();
    }, 400);

    return () => window.clearTimeout(timer);
  }, [fitMapToPune, maximized]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const existing = droneMarkersRef.current;
    const currentIds = new Set(drones.map((drone) => drone.id));

    existing.forEach((marker, id) => {
      if (!currentIds.has(id)) {
        marker.remove();
        existing.delete(id);
      }
    });

    drones.forEach((drone) => {
      const isActive = drone.status === 'en_route' || drone.status === 'on_site';
      const droneIcon = L.divIcon({
        className: '',
        html: `<div style="width:${isActive ? 14 : 10}px;height:${isActive ? 14 : 10}px;border-radius:999px;background:${isActive ? 'hsl(var(--foreground))' : 'hsl(var(--muted-foreground))'};border:2px solid ${isActive ? 'hsl(var(--foreground))' : 'hsl(var(--border))'};box-shadow:${isActive ? '0 0 10px rgba(255,255,255,0.5)' : 'none'}"></div>`,
        iconSize: [isActive ? 14 : 10, isActive ? 14 : 10],
        iconAnchor: [isActive ? 7 : 5, isActive ? 7 : 5],
      });

      if (existing.has(drone.id)) {
        const marker = existing.get(drone.id)!;
        marker.setLatLng([drone.position.lat, drone.position.lng]);
        marker.setIcon(droneIcon);
      } else {
        const marker = L.marker([drone.position.lat, drone.position.lng], { icon: droneIcon, zIndexOffset: 900 }).addTo(map);
        marker.bindPopup(`<div style="font-size:11px;font-family:'IBM Plex Mono',monospace;padding:2px">
          <b>${drone.id.replace('drone_', 'D-')}</b><br/>
          Status: ${drone.status}<br/>
          Battery: ${drone.battery.toFixed(0)}%
        </div>`);
        existing.set(drone.id, marker);
      }
    });
  }, [drones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const existing = incidentMarkersRef.current;
    const activeIncidents = incidents.filter((incident) => !['resolved', 'rejected', 'logged'].includes(incident.status));
    const currentIds = new Set(activeIncidents.map((incident) => incident.id));

    existing.forEach((marker, id) => {
      if (!currentIds.has(id)) {
        marker.remove();
        existing.delete(id);
      }
    });

    activeIncidents.forEach((incident) => {
      const isCritical = incident.severity >= 8;
      if (existing.has(incident.id)) {
        existing.get(incident.id)!.setLatLng([incident.position.lat, incident.position.lng]);
        return;
      }

      const marker = L.circleMarker([incident.position.lat, incident.position.lng], {
        radius: isCritical ? 9 : 7,
        color: 'hsl(var(--foreground))',
        fillColor: 'hsl(var(--foreground))',
        fillOpacity: isCritical ? 0.9 : 0.55,
        weight: isCritical ? 3 : 2,
      }).addTo(map);

      marker.on('click', () => onIncidentClick(incident));
      marker.bindPopup(`<div style="font-size:11px;font-family:'IBM Plex Mono',monospace;padding:2px">
        <b>${incident.type.replace(/_/g, ' ').toUpperCase()}</b><br/>
        Confidence: ${(incident.detectionConfidence * 100).toFixed(0)}%<br/>
        Priority: ${incident.priorityScore.toFixed(1)}
      </div>`);
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
      .filter((drone) => drone.status === 'en_route' && drone.targetIncidentId)
      .forEach((drone) => {
        const incident = incidents.find((item) => item.id === drone.targetIncidentId);
        if (!incident) return;

        const line = L.polyline(
          [
            [drone.position.lat, drone.position.lng],
            [incident.position.lat, incident.position.lng],
          ],
          {
            color: 'hsl(var(--foreground))',
            weight: 1.5,
            dashArray: '6 4',
            opacity: 0.4,
          }
        ).addTo(map);

        existing.set(drone.id, line);
      });
  }, [drones, incidents]);

  return (
    <div
      className={`relative h-full w-full overflow-hidden border border-border/60 bg-card ${
        maximized ? 'fixed inset-3 z-50 rounded-xl shadow-2xl' : 'rounded-lg'
      }`}
    >
      <button
        onClick={() => setMaximized(!maximized)}
        className="absolute top-3 right-3 z-[1000] rounded-md border border-border/60 bg-card/90 p-2 text-muted-foreground transition-colors hover:text-foreground"
        title={maximized ? 'Minimize map' : 'Maximize map'}
        aria-label={maximized ? 'Minimize map' : 'Maximize map'}
      >
        {maximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </button>
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
