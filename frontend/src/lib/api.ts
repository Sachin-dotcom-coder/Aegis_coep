// ─── Aegis API Client ────────────────────────────────────────────────────────
// All backend ↔ frontend field mappings live here.
// Backend runs on http://localhost:8000  (FastAPI / uvicorn)
// WebSocket: ws://localhost:8000/ws/drones

export const API_BASE = 'http://localhost:8000';
export const WS_URL   = 'ws://localhost:8000/ws/drones';

// ── Raw shapes returned by the backend ───────────────────────────────────────

export interface BackendDrone {
  drone_id: string;
  state: 'idle' | 'en_route' | 'on_scene' | 'recalled' | 'charging';
  lat: number;
  lng: number;
  battery: number;
  assigned_incident: string | null;
  eta_seconds?: number;
  path_progress?: number;
  charging_progress?: number;
}

export interface BackendIncident {
  _id?: string;
  id: string;
  zone_id: string;
  zone_accident_frequency: number;
  type: string;
  severity: number;
  camera_id: string;
  camera_coverage: number;
  people_in_frame: number;
  lat: number;
  lng: number;
  detect_confidence: number;
  timestamp: string;
  decision_confidence: number | null;
  priority_score: number | null;
  status: string;
  assigned_drone: string | null;
  eta_seconds: number | null;
  multi_cam_bonus?: number | null;
}

export interface BackendAudit {
  _id?: string;
  timestamp: string;
  action: string;
  incident_id?: string;
  drone_id?: string;
  reason?: string;
  priority_score?: number;
  decision_confidence?: number;
}

import { Drone, Incident, AuditEntry } from './types';

// ── Mapping helpers ───────────────────────────────────────────────────────────

/** Map backend drone state → frontend status */
function mapDroneState(state: BackendDrone['state']): Drone['status'] {
  switch (state) {
    case 'en_route':  return 'en_route';
    case 'on_scene':  return 'on_site';
    case 'recalled':  return 'recalled';
    case 'charging':  return 'charging';
    default:          return 'idle';
  }
}

/** Derive a stable zoneId from lat/lng by finding the closest known station */
const STATIONS: { id: string; lat: number; lng: number }[] = [
  { id: 'z1', lat: 18.5300, lng: 73.8500 },
  { id: 'z2', lat: 18.5500, lng: 73.9300 },
  { id: 'z3', lat: 18.5900, lng: 73.7300 },
  { id: 'z4', lat: 18.4500, lng: 73.8600 },
  { id: 'z5', lat: 18.5600, lng: 73.9100 },
];

function nearestStation(lat: number, lng: number): string {
  let best = STATIONS[0];
  let bestDist = Infinity;
  for (const s of STATIONS) {
    const d = (s.lat - lat) ** 2 + (s.lng - lng) ** 2;
    if (d < bestDist) { bestDist = d; best = s; }
  }
  return best.id;
}

export function mapDrone(b: BackendDrone): Drone {
  const zoneId = nearestStation(b.lat, b.lng);
  return {
    id:              b.drone_id,
    zoneId,
    position:        { lat: b.lat, lng: b.lng },
    basePosition:    { lat: b.lat, lng: b.lng },   // backend doesn't expose home, use current
    status:          mapDroneState(b.state),
    battery:         b.battery,
    targetIncidentId: b.assigned_incident ?? undefined,
    eta_seconds:       b.eta_seconds,
    path_progress:     b.path_progress,
    charging_progress: b.charging_progress,
  };
}

export function mapIncident(b: BackendIncident): Incident {
  return {
    id:                  b.id,
    type:                b.type,
    position:            { lat: b.lat, lng: b.lng },
    zoneId:              b.zone_id.toLowerCase(),
    timestamp:           new Date(b.timestamp).getTime(),
    detectionConfidence: b.detect_confidence,
    decisionConfidence:  b.decision_confidence ?? 0,
    priorityScore:       b.priority_score ?? 0,
    status:              b.status,
    assignedDroneId:     b.assigned_drone ?? undefined,
    cameraSource:        b.camera_id,
    frameCount:          b.people_in_frame,
    peopleInFrame:        b.people_in_frame, // Aligned with central types
    severity:            b.severity,
    etaSeconds:          b.eta_seconds ?? undefined,
    multiCamBonus:       b.multi_cam_bonus ?? undefined,
  };
}

export function mapAudit(b: BackendAudit, idx: number): AuditEntry {
  return {
    id:         b._id ?? `audit_${idx}_${Date.now()}`,
    timestamp:  new Date(b.timestamp).getTime(),
    action:     b.action,
    incidentId: b.incident_id,
    droneId:    b.drone_id,
    details:    b.reason ?? b.action,
    decisionConfidence: b.decision_confidence, // Corrected field name
  };
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

// ── Public API surface ────────────────────────────────────────────────────────

export const api = {
  /** Fetch entire fleet snapshot */
  getDrones: async (): Promise<Drone[]> => {
    const raw = await get<BackendDrone[]>('/drones/');
    return raw.map(mapDrone);
  },

  /** Fetch incidents, optionally filtered by status */
  getIncidents: async (status?: string): Promise<Incident[]> => {
    const qs = status ? `?status=${status}` : '';
    const raw = await get<BackendIncident[]>(`/incidents/${qs}`);
    return raw.map(mapIncident);
  },

  /** Fetch latest audit log entries */
  getAuditLog: async (limit = 100): Promise<AuditEntry[]> => {
    const raw = await get<BackendAudit[]>(`/audits/?limit=${limit}`);
    return raw.map(mapAudit);
  },

  /** Operator approves a pending incident → drone dispatched */
  approveIncident: (incidentId: string) =>
    post<{ status: string }>(`/incidents/${incidentId}/approve`),

  /** Operator rejects an incident */
  rejectIncident: (incidentId: string) =>
    post<{ status: string }>(`/incidents/${incidentId}/reject`),

  /** Admin resolves an incident */
  resolveIncident: (incidentId: string) =>
    post<{ status: string }>(`/incidents/${incidentId}/resolve`),

  /** Admin cancels active incident */
  cancelIncident: (incidentId: string) =>
    post<{ status: string }>(`/incidents/${incidentId}/cancel`),

  /** Manual deploy – dispatch a specific drone to lat/lng */
  deployDrone: (droneId: string, lat: number, lng: number) =>
    post<{ status: string }>(`/drones/${droneId}/deploy`, { lat, lng }),

  /** Recall a drone mid-flight */
  recallDrone: (droneId: string) =>
    post<{ status: string }>(`/drones/${droneId}/recall`),
};
