import { useState, useCallback, useRef } from 'react';
import { BootSequence } from '@/components/BootSequence';
import { Navbar } from '@/components/Navbar';
import { CityMap } from '@/components/CityMap';
import { AlertsPanel } from '@/components/AlertsPanel';
import { DroneFleetPanel } from '@/components/DroneFleetPanel';
import { DecisionPanel } from '@/components/DecisionPanel';
import { AuditLog } from '@/components/AuditLog';
import { ConfirmationModal } from '@/components/ConfirmationModal';
import { useSimulation } from '@/hooks/useSimulation';

const Index = () => {
  const [booted, setBooted] = useState(false);
  const sim = useSimulation();
  const bootRef = useRef(sim.boot);
  bootRef.current = sim.boot;

  const handleBootComplete = useCallback(() => {
    setBooted(true);
    bootRef.current();
  }, []);

  if (!booted) {
    return <BootSequence onComplete={handleBootComplete} />;
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      <Navbar drones={sim.drones} incidents={sim.incidents} />

      <div className="flex-1 flex overflow-hidden min-h-0" style={{ height: 'calc(100vh - 11rem)' }}>
        <div className="flex-[65] min-w-0 min-h-0 p-2" style={{ height: '100%' }}>
          <div className="relative h-full w-full min-w-0 min-h-0">
            <CityMap
              drones={sim.drones}
              incidents={sim.incidents}
              onIncidentClick={sim.setSelectedIncident}
            />
          </div>
        </div>

        <div className="flex-[35] w-full max-w-sm min-w-[20rem] min-h-0 flex flex-col p-2 pl-0 gap-1.5" style={{ height: '100%' }}>
          <div className="flex-[4] min-h-0 overflow-hidden">
            <AlertsPanel incidents={sim.incidents} onSelect={sim.setSelectedIncident} selectedId={sim.selectedIncident?.id} />
          </div>
          <div className="flex-[3] min-h-0 overflow-hidden">
            <DroneFleetPanel drones={sim.drones} />
          </div>
          <div className="flex-[3] min-h-0 overflow-hidden">
            <DecisionPanel incident={sim.selectedIncident} />
          </div>
        </div>
      </div>

      {/* Audit log */}
      <div className="h-32 p-2 pt-0 shrink-0">
        <AuditLog entries={sim.auditLog} />
      </div>

      {sim.pendingConfirmation && (
        <ConfirmationModal
          incident={sim.pendingConfirmation}
          onConfirm={sim.confirmIncident}
          onReject={sim.rejectIncident}
        />
      )}
    </div>
  );
};

export default Index;
