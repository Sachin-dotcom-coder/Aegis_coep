import { DispatchZone, Drone, Incident, IncidentType, AuditEntry, AuditAction, GeoPoint, PriorityBreakdown } from './types';

// Pune dispatch zones
export const DISPATCH_ZONES: DispatchZone[] = [
  { id: 'z1', name: 'Shivajinagar', position: { lat: 18.5308, lng: 73.8475 }, riskMultiplier: 1.4, reliability: 0.88, color: '#ffffff' },
  { id: 'z2', name: 'Kothrud', position: { lat: 18.5074, lng: 73.8077 }, riskMultiplier: 1.1, reliability: 0.92, color: '#ffffff' },
  { id: 'z3', name: 'Hadapsar', position: { lat: 18.5089, lng: 73.9260 }, riskMultiplier: 1.3, reliability: 0.85, color: '#ffffff' },
  { id: 'z4', name: 'Viman Nagar', position: { lat: 18.5679, lng: 73.9143 }, riskMultiplier: 1.2, reliability: 0.90, color: '#ffffff' },
  { id: 'z5', name: 'Swargate', position: { lat: 18.5018, lng: 73.8636 }, riskMultiplier: 1.5, reliability: 0.82, color: '#ffffff' },
];

const INCIDENT_TYPES: { type: IncidentType; severity: number; label: string }[] = [
  { type: 'crowd_formation', severity: 7, label: 'Crowd Formation' },
  { type: 'road_accident', severity: 9, label: 'Road Accident' },
  { type: 'fallen_person', severity: 8, label: 'Fallen Person' },
  { type: 'unauthorized_entry', severity: 6, label: 'Unauthorized Entry' },
  { type: 'suspicious_vehicle', severity: 5, label: 'Suspicious Vehicle' },
  { type: 'abandoned_object', severity: 7, label: 'Abandoned Object' },
];

export function getIncidentLabel(type: string): string {
  return INCIDENT_TYPES.find(t => t.type === type)?.label ?? type;
}

export function getIncidentSeverity(type: IncidentType): number {
  return INCIDENT_TYPES.find(t => t.type === type)?.severity ?? 5;
}

let idCounter = 0;
export function genId(prefix = 'id'): string {
  return `${prefix}_${++idCounter}_${Date.now().toString(36)}`;
}

export function initDrones(): Drone[] {
  const drones: Drone[] = [];
  let globalIdx = 1;
  DISPATCH_ZONES.forEach((zone) => {
    for (let i = 0; i < 3; i++) {
      const offset = { lat: (Math.random() - 0.5) * 0.002, lng: (Math.random() - 0.5) * 0.002 };
      const pos = { lat: zone.position.lat + offset.lat, lng: zone.position.lng + offset.lng };
      drones.push({
        id: `drone_${globalIdx++}`,
        zoneId: zone.id,
        position: { ...pos },
        basePosition: { ...pos },
        status: 'idle',
        battery: 85 + Math.random() * 15,
      });
    }
  });
  return drones;
}

export function distance(a: GeoPoint, b: GeoPoint): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

export function calculatePriority(incident: Partial<Incident>, zone: DispatchZone, nearestEta: number): PriorityBreakdown {
  const severity = incident.severity ?? 5;
  const zoneRisk = zone.riskMultiplier;
  const hour = new Date().getHours();
  const timeWeight = hour >= 22 || hour <= 5 ? 1.3 : hour >= 17 ? 1.15 : 1.0;
  const recencyBoost = 1.2;
  const multiCamBonus = incident.multiCamBonus ?? (Math.random() > 0.6 ? 1.15 : 1.0);
  const etaPenalty = nearestEta * 0.05;

  const finalScore = (severity * zoneRisk * timeWeight * recencyBoost * multiCamBonus) / (1 + etaPenalty);

  return { severity, zoneRisk, timeWeight, recencyBoost, multiCamBonus, etaPenalty, finalScore: Math.round(finalScore * 100) / 100 };
}

export function spawnIncident(zones: DispatchZone[], drones: Drone[]): { incident: Incident; zone: DispatchZone } {
  const zone = zones[Math.floor(Math.random() * zones.length)];
  const typeInfo = INCIDENT_TYPES[Math.floor(Math.random() * INCIDENT_TYPES.length)];
  const offset = { lat: (Math.random() - 0.5) * 0.015, lng: (Math.random() - 0.5) * 0.015 };
  const position = { lat: zone.position.lat + offset.lat, lng: zone.position.lng + offset.lng };

  const detectionConfidence = 0.45 + Math.random() * 0.55;
  const decisionConfidence = detectionConfidence * zone.reliability;

  const nearestDrone = drones.filter(d => d.status === 'idle').sort((a, b) => distance(a.position, position) - distance(b.position, position))[0];
  const nearestEta = nearestDrone ? distance(nearestDrone.position, position) * 2 : 10;

  const priority = calculatePriority({ severity: typeInfo.severity }, zone, nearestEta);

  let status: Incident['status'];
  if (decisionConfidence > 0.8) status = 'queued';
  else if (decisionConfidence >= 0.5) status = 'pending_confirmation';
  else status = 'logged';

  const incident: Incident = {
    id: genId('inc'),
    type: typeInfo.type,
    position,
    zoneId: zone.id,
    timestamp: Date.now(),
    detectionConfidence: Math.round(detectionConfidence * 100) / 100,
    decisionConfidence: Math.round(decisionConfidence * 100) / 100,
    priorityScore: priority.finalScore,
    status,
    cameraSource: `CAM-${zone.name.substring(0, 3).toUpperCase()}-${Math.floor(Math.random() * 9) + 1}`,
    frameCount: 5 + Math.floor(Math.random() * 10),
    severity: typeInfo.severity,
    peopleInFrame: Math.floor(Math.random() * 20),
  };

  return { incident, zone };
}

export function selectDrone(drones: Drone[], incidentPos: GeoPoint): Drone | null {
  const available = drones.filter(d => d.status === 'idle' && d.battery > 20);
  if (!available.length) return null;

  return available.sort((a, b) => {
    const scoreA = distance(a.position, incidentPos) * 2 + (100 - a.battery) * 0.1;
    const scoreB = distance(b.position, incidentPos) * 2 + (100 - b.battery) * 0.1;
    return scoreA - scoreB;
  })[0];
}

export function createAuditEntry(action: AuditAction, details: string, incidentId?: string, droneId?: string, confidence?: number): AuditEntry {
  return { id: genId('audit'), timestamp: Date.now(), action, details, incidentId, droneId, confidence };
}

export function moveDroneToward(drone: Drone, target: GeoPoint, speed = 0.0008): GeoPoint {
  const dlat = target.lat - drone.position.lat;
  const dlng = target.lng - drone.position.lng;
  const dist = Math.sqrt(dlat ** 2 + dlng ** 2);
  if (dist < speed) return { ...target };
  const ratio = speed / dist;
  return { lat: drone.position.lat + dlat * ratio, lng: drone.position.lng + dlng * ratio };
}
