import { useState, useEffect, useCallback, useRef } from 'react';
import { Drone, Incident, AuditEntry } from '@/lib/types';
import {
  DISPATCH_ZONES,
  initDrones,
  spawnIncident,
  selectDrone,
  createAuditEntry,
  moveDroneToward,
  distance,
} from '@/lib/simulation';

export function useSimulation() {
  const [drones, setDrones] = useState<Drone[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [pendingConfirmation, setPendingConfirmation] = useState<Incident | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [running, setRunning] = useState(false);
  const dronesRef = useRef(drones);
  const incidentsRef = useRef(incidents);

  useEffect(() => { dronesRef.current = drones; }, [drones]);
  useEffect(() => { incidentsRef.current = incidents; }, [incidents]);

  const addAudit = useCallback((entry: AuditEntry) => {
    setAuditLog(prev => [entry, ...prev].slice(0, 100));
  }, []);

  const boot = useCallback(() => {
    const d = initDrones();
    setDrones(d);
    setIncidents([]);
    setAuditLog([createAuditEntry('SYSTEM_BOOT', 'Aegis Shield v2.0 initialized — 15 drones online')]);
    setRunning(true);
  }, []);

  // Spawn incidents every 30-40s
  useEffect(() => {
    if (!running) return;
    const spawnDelay = 30000 + Math.random() * 10000;
    const interval = setInterval(() => {
      const { incident } = spawnIncident(DISPATCH_ZONES, dronesRef.current);
      setIncidents(prev => [incident, ...prev].slice(0, 50));
      addAudit(createAuditEntry('AI_DETECTED', `${incident.type.replace(/_/g, ' ')} detected at ${incident.cameraSource} (conf: ${incident.detectionConfidence})`, incident.id, undefined, incident.detectionConfidence));

      if (incident.status === 'queued') {
        // Auto dispatch
        const drone = selectDrone(dronesRef.current, incident.position);
        if (drone) {
          setDrones(prev => prev.map(d => d.id === drone.id ? { ...d, status: 'en_route', targetIncidentId: incident.id } : d));
          setIncidents(prev => prev.map(i => i.id === incident.id ? { ...i, status: 'dispatched', assignedDroneId: drone.id } : i));
          addAudit(createAuditEntry('AUTO_DISPATCH', `Drone ${drone.id} auto-dispatched (decision conf: ${incident.decisionConfidence})`, incident.id, drone.id, incident.decisionConfidence));
        }
      } else if (incident.status === 'pending_confirmation') {
        setPendingConfirmation(prev => prev ?? incident);
      }
    }, spawnDelay);
    return () => clearInterval(interval);
  }, [running, addAudit]);

  // Move drones & drain battery
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(() => {
      setDrones(prev => prev.map(drone => {
        if (drone.status === 'en_route' && drone.targetIncidentId) {
          const incident = incidentsRef.current.find(i => i.id === drone.targetIncidentId);
          if (!incident) return { ...drone, status: 'returning', targetIncidentId: undefined };
          const newPos = moveDroneToward(drone, incident.position);
          const newBattery = Math.max(0, drone.battery - 0.15);
          const arrived = distance(newPos, incident.position) < 0.05;

          if (newBattery < 10) {
            addAudit(createAuditEntry('LOW_BATTERY_FAILSAFE', `Drone ${drone.id} recalled — battery critical`, incident.id, drone.id));
            return { ...drone, position: newPos, battery: newBattery, status: 'recalled', targetIncidentId: undefined };
          }

          if (arrived) {
            // Resolve after arrival
            setTimeout(() => {
              setIncidents(p => p.map(i => i.id === incident.id ? { ...i, status: 'resolved' } : i));
              setDrones(p => p.map(d => d.id === drone.id ? { ...d, status: 'returning', targetIncidentId: undefined } : d));
              addAudit(createAuditEntry('INCIDENT_RESOLVED', `Incident resolved by ${drone.id}`, incident.id, drone.id));
            }, 5000);
            return { ...drone, position: newPos, battery: newBattery, status: 'on_site' };
          }
          return { ...drone, position: newPos, battery: newBattery };
        }

        if (drone.status === 'returning' || drone.status === 'recalled') {
          const newPos = moveDroneToward(drone, drone.basePosition);
          const newBattery = Math.max(0, drone.battery - 0.1);
          const home = distance(newPos, drone.basePosition) < 0.05;
          if (home) return { ...drone, position: drone.basePosition, battery: Math.min(100, newBattery + 0.5), status: 'idle' };
          return { ...drone, position: newPos, battery: newBattery };
        }

        // Idle drones recharge
        if (drone.status === 'idle' && drone.battery < 100) {
          return { ...drone, battery: Math.min(100, drone.battery + 0.3) };
        }

        return drone;
      }));
    }, 500);
    return () => clearInterval(interval);
  }, [running, addAudit]);

  const confirmIncident = useCallback((incidentId: string) => {
    const drone = selectDrone(dronesRef.current, incidentsRef.current.find(i => i.id === incidentId)?.position ?? { lat: 0, lng: 0 });
    if (drone) {
      setDrones(prev => prev.map(d => d.id === drone.id ? { ...d, status: 'en_route', targetIncidentId: incidentId } : d));
      setIncidents(prev => prev.map(i => i.id === incidentId ? { ...i, status: 'dispatched', assignedDroneId: drone.id } : i));
      addAudit(createAuditEntry('HUMAN_CONFIRM', `Operator confirmed dispatch of ${drone.id}`, incidentId, drone.id));
    }
    setPendingConfirmation(null);
  }, [addAudit]);

  const rejectIncident = useCallback((incidentId: string) => {
    setIncidents(prev => prev.map(i => i.id === incidentId ? { ...i, status: 'rejected' } : i));
    addAudit(createAuditEntry('HUMAN_REJECT', `Operator rejected incident`, incidentId));
    setPendingConfirmation(null);
  }, [addAudit]);

  const manualDispatch = useCallback((droneId: string, target: { lat: number; lng: number }) => {
    setDrones(prev => prev.map(d => d.id === droneId ? { ...d, status: 'en_route', targetIncidentId: 'manual' } : d));
    addAudit(createAuditEntry('MANUAL_OVERRIDE', `Manual dispatch of ${droneId}`, undefined, droneId));
    // Return after 10s
    setTimeout(() => {
      setDrones(prev => prev.map(d => d.id === droneId ? { ...d, status: 'returning', targetIncidentId: undefined } : d));
    }, 10000);
  }, [addAudit]);

  return {
    drones, incidents, auditLog, pendingConfirmation, selectedIncident,
    setSelectedIncident, boot, confirmIncident, rejectIncident, manualDispatch, running,
  };
}
