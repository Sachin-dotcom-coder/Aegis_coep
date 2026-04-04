export type IncidentType =
  | 'road_accident'
  | 'crowd_gathering'
  | 'fallen_person'
  | 'intrusion'
  | 'fire'
  | 'earthquake'
  | 'unauthorized_entry'
  | 'suspicious_vehicle'
  | 'abandoned_object'
  | 'crowd_formation';

export type IncidentStatus =
  | 'pending'
  | 'queued'
  | 'dispatched'
  | 'in_progress'
  | 'resolved'
  | 'rejected'
  | 'logged';

export type DroneStatus =
  | 'idle'
  | 'en_route'
  | 'on_site'
  | 'returning'
  | 'recalled'
  | 'charging'
  | 'low_battery';

export type AuditAction = string;

export interface GeoPoint {
  lat: number;
  lng: number;
}

export interface Drone {
  id: string;
  position: GeoPoint;
  battery: number;
  status: DroneStatus;
  targetIncidentId?: string;
  basePosition: GeoPoint;
  zoneId: string; // Dynamic sector ID
}

export interface Incident {
  id: string;
  type: IncidentType | string;
  position: GeoPoint;
  zoneId: string;
  timestamp: number;
  detectionConfidence: number;
  decisionConfidence: number;
  priorityScore: number;
  status: IncidentStatus | string;
  assignedDroneId?: string;
  cameraSource: string;
  frameCount: number;
  peopleInFrame: number;
  severity: number;
  etaSeconds?: number;
  multiCamBonus?: number;
}

export interface AuditEntry {
  id: string;
  timestamp: number;
  action: AuditAction;
  incidentId?: string;
  droneId?: string;
  details: string;
  priorityScore?: number;
  decisionConfidence?: number;
  confidence?: number;
}

export interface DispatchZone {
  id: string;
  name: string;
  position: GeoPoint;
  riskMultiplier: number;
  reliability: number;
  color: string;
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
