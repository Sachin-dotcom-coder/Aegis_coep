/**
 * useSimulation – Live backend hook
 *
 * Data flow:
 *  • Incidents:  GET /incidents/ on boot + polled every 5 s
 *  • Drones:     WebSocket /ws/drones (1-s push from backend fleet loop)
 *                + GET /drones/ on boot (before WS connects)
 *  • Audit log:  GET /audits/ on boot + polled every 8 s
 *
 * Actions (approve/reject/manual deploy/recall) all go to the REST API; no
 * local state mutation – next poll cycle automatically reflects the result.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Drone, Incident, AuditEntry } from '@/lib/types';
import { api, WS_URL, mapDrone, mapIncident, mapAudit } from '@/lib/api';
import type { BackendDrone } from '@/lib/api';

export function useSimulation() {
  const [drones,    setDrones]    = useState<Drone[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [auditLog,  setAuditLog]  = useState<AuditEntry[]>([]);
  const [running,   setRunning]   = useState(false);

  // Incident the operator has clicked on → opens DecisionPanel
  const [selectedIncident,   setSelectedIncident]   = useState<Incident | null>(null);
  // Incident needing human confirmation (status === 'pending')
  const [pendingConfirmation, setPendingConfirmation] = useState<Incident | null>(null);

  // Track IDs already actioned this session — prevents re-popping the same modal
  const dismissedIds = useRef<Set<string>>(new Set());

  const wsRef = useRef<WebSocket | null>(null);

  // ── Helpers ──────────────────────────────────────────────────────────────

  const addAuditEntry = useCallback((entry: AuditEntry) => {
    setAuditLog(prev => [entry, ...prev].slice(0, 150));
  }, []);

  // ── Boot: load initial state from backend ─────────────────────────────────

  const boot = useCallback(async () => {
    try {
      // Parallel initial loads
      const [initDrones, initIncidents, initAudits] = await Promise.all([
        api.getDrones(),
        api.getIncidents(),
        api.getAuditLog(100),
      ]);

      setDrones(initDrones);
      setIncidents(initIncidents);
      setAuditLog(initAudits);

      // Set pending confirmation if any incident needs human review
      const pending = initIncidents.find(i => i.status === 'pending');
      if (pending) setPendingConfirmation(pending);

      setRunning(true);
    } catch (err) {
      console.error('❌ Aegis boot failed:', err);
      // Fallback: show system boot entry so UI doesn't look empty
      setAuditLog([{
        id: 'boot_fail',
        timestamp: Date.now(),
        action: 'SYSTEM_BOOT',
        details: 'Backend unreachable – running in offline mode',
      }]);
      setRunning(true);
    }
  }, []);

  // ── WebSocket: live drone telemetry ──────────────────────────────────────

  useEffect(() => {
    if (!running) return;

    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('🔌 WS connected to Aegis backend');
      };

      ws.onmessage = (event) => {
        try {
          const raw: BackendDrone[] = JSON.parse(event.data);
          setDrones(raw.map(mapDrone));
        } catch (e) {
          console.warn('WS parse error', e);
        }
      };

      ws.onclose = () => {
        console.warn('⚠️ WS disconnected – reconnecting in 3 s');
        reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onerror = (e) => {
        console.error('WS error', e);
        ws.close();
      };
    };

    connect();

    return () => {
      wsRef.current?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, [running]);

  // ── Poll incidents every 5 s ──────────────────────────────────────────────

  useEffect(() => {
    if (!running) return;

    const tick = async () => {
      try {
        const fresh = await api.getIncidents();
        setIncidents(fresh);

        // Surface incidents needing human confirmation via the modal.
        // Priority 1: backend-flagged 'pending' incidents (explicit human-review request)
        // Priority 2: highest-priority queued incident with decisionConfidence < 0.5
        //             (low-confidence detections that need operator approval before dispatch)
        const explicitPending = fresh.find(
          i => i.status === 'pending' && !dismissedIds.current.has(i.id)
        );

        // Catch low-confidence incidents in ANY waiting status:
        // 'pending' = decision_confidence 0.2–0.5 (human gate)
        // 'silent'  = decision_confidence < 0.2 (fully suppressed, but detect_confidence ~0.3–0.49)
        // 'queued' / 'auto' = edge cases
        const lowConfTop = !explicitPending
          ? fresh
              .filter(i =>
                (i.detectionConfidence < 0.5 && i.decisionConfidence < 0.5) &&
                ['queued', 'auto', 'silent', 'pending'].includes(i.status) &&
                !dismissedIds.current.has(i.id)
              )
              .sort((a, b) => b.priorityScore - a.priorityScore)[0] ?? null
          : null;

        const nextConfirmation = explicitPending ?? lowConfTop ?? null;

        setPendingConfirmation(prev => {
          // Show the modal for a new confirmation candidate
          if (nextConfirmation && (!prev || prev.id !== nextConfirmation.id)) return nextConfirmation;
          // Clear if the previously shown incident is no longer actionable
          if (prev && !fresh.find(i =>
            i.id === prev.id &&
            ['pending', 'queued', 'auto', 'silent'].includes(i.status)
          )) return null;
          return prev;
        });

        // Keep selectedIncident in sync (status may have changed)
        setSelectedIncident(prev => {
          if (!prev) return null;
          return fresh.find(i => i.id === prev.id) ?? null;
        });
      } catch (err) {
        console.warn('Incident poll failed:', err);
      }
    };

    tick(); // immediate first tick
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, [running]);

  // ── Poll audit log every 8 s ──────────────────────────────────────────────

  useEffect(() => {
    if (!running) return;

    const tick = async () => {
      try {
        const fresh = await api.getAuditLog(100);
        setAuditLog(fresh);
      } catch (err) {
        console.warn('Audit poll failed:', err);
      }
    };

    const id = setInterval(tick, 8000);
    return () => clearInterval(id);
  }, [running]);

  // ── Actions ───────────────────────────────────────────────────────────────

  /** Operator approves a pending incident → dispatch drone */
  const confirmIncident = useCallback(async (incidentId: string) => {
    dismissedIds.current.add(incidentId);   // never re-surface this incident
    setIncidents(prev => prev.filter(i => i.id !== incidentId)); // Immediate UI feedback
    try {
      await api.approveIncident(incidentId);
    } catch (err) {
      console.error('Approve failed:', err);
    }
    setPendingConfirmation(null);
  }, []);

  /** Operator rejects an incident */
  const rejectIncident = useCallback(async (incidentId: string) => {
    dismissedIds.current.add(incidentId);   // never re-surface this incident
    setIncidents(prev => prev.filter(i => i.id !== incidentId)); // Immediate UI feedback
    try {
      await api.rejectIncident(incidentId);
    } catch (err) {
      console.error('Reject failed:', err);
    }
    setPendingConfirmation(null);
  }, []);

  /**
   * Manual deploy — finds the nearest idle drone and sends it to lat/lng.
   */
  const manualDispatch = useCallback(async (targetLat: number, targetLng: number) => {
    const current = drones;
    const idle = current.filter(d => d.status === 'idle' || d.status === 'charging');
    if (idle.length === 0) {
      console.warn('No idle drones available for manual dispatch');
      return;
    }

    // Nearest idle by simple Euclidean distance
    const nearest = idle.reduce((a, b) =>
      (a.position.lat - targetLat) ** 2 + (a.position.lng - targetLng) ** 2 <
      (b.position.lat - targetLat) ** 2 + (b.position.lng - targetLng) ** 2
        ? a : b
    );

    try {
      await api.deployDrone(nearest.id, targetLat, targetLng);
    } catch (err) {
      console.error('Manual deploy failed:', err);
    }
  }, [drones]);

  /** Recall a specific drone */
  const abortDrone = useCallback(async (droneId: string) => {
    try {
      await api.recallDrone(droneId);
    } catch (err) {
      console.error('Recall failed:', err);
    }
  }, []);

  return {
    drones,
    incidents,
    auditLog,
    pendingConfirmation,
    selectedIncident,
    setSelectedIncident,
    boot,
    confirmIncident,
    rejectIncident,
    manualDispatch,
    abortDrone,
    running,
  };
}
