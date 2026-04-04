export type IncidentType =
  | 'crowd_formation'
  | 'road_accident'
  | 'fallen_person'
  | 'unauthorized_entry'
  | 'suspicious_vehicle'
  | 'abandoned_object';

export type IncidentStatus = 'detected' | 'pending_confirmation' | 'queued' | 'dispatched' | 'resolved' | 'rejected' | 'logged';

export type DroneStatus = 'idle' | 'en_route' | 'on_site' | 'returning' | 'recalled' | 'low_battery';

export type AuditAction =
  | 'AI_DETECTED'
  | 'AUTO_DISPATCH'
  | 'HUMAN_CONFIRM'
  | 'HUMAN_REJECT'
  | 'MANUAL_OVERRIDE'
  | 'MANUAL_DISPATCH'
  | 'MANUAL_ABORT'
  | 'INCIDENT_RESOLVED'
  | 'LOW_BATTERY_FAILSAFE'
  | 'FLEET_REBALANCE'
  | 'SYSTEM_BOOT';

export interface GeoPoint {
  lat: number;
  lng: number;
}

export interface DispatchZone {
  id: string;
  name: string;
  position: GeoPoint;
  riskMultiplier: number;
  reliability: number;
  color: string;
}

export interface Drone {
  id: string;
  zoneId: string;
  position: GeoPoint;
  basePosition: GeoPoint;
  status: DroneStatus;
  battery: number;
  targetIncidentId?: string;
  targetPosition?: GeoPoint;
  eta?: number;
}

export interface Incident {
  id: string;
  type: IncidentType;
  position: GeoPoint;
  zoneId: string;
  timestamp: number;
  detectionConfidence: number;
  decisionConfidence: number;
  priorityScore: number;
  status: IncidentStatus;
  assignedDroneId?: string;
  cameraSource: string;
  frameCount: number;
  severity: number;
}

export interface AuditEntry {
  id: string;
  timestamp: number;
  action: AuditAction;
  incidentId?: string;
  droneId?: string;
  details: string;
  confidence?: number;
}

export interface PriorityBreakdown {
  severity: number;
  zoneRisk: number;
  timeWeight: number;
  recencyBoost: number;
  multiCamBonus: number;
  etaPenalty: number;
  finalScore: number;
}
