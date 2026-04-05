import { useState, useCallback, useRef } from 'react';
import { X, Activity } from 'lucide-react';
import { BootSequence } from '@/components/BootSequence';
import { Navbar } from '@/components/Navbar';
import { CityMap } from '@/components/CityMap';
import { AlertsPanel } from '@/components/AlertsPanel';
import { DroneFleetPanel } from '@/components/DroneFleetPanel';
import { DecisionPanel } from '@/components/DecisionPanel';
import { AuditLog } from '@/components/AuditLog';
import { ConfirmationModal } from '@/components/ConfirmationModal';
import { ManualCommandPanel } from '@/components/ManualCommandPanel';
import { ActiveMissionsPanel } from '@/components/ActiveMissionsPanel';
import { useSimulation } from '@/hooks/useSimulation';

const Index = () => {
  const [booted, setBooted] = useState(false);
  const [activeLiveFeed, setActiveLiveFeed] = useState<string | null>(null);
  const [videoMaximized, setVideoMaximized] = useState(false);
  const [showFleetModal, setShowFleetModal] = useState<{ zoneId: string; idx: number } | boolean>(false);
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

      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left Column: Map + Audit Log */}
        <div className="flex-[40] min-w-0 min-h-0 p-2 flex flex-col gap-2">
          <div className="relative flex-1 w-full min-w-0 min-h-0">
            <CityMap
              drones={sim.drones}
              incidents={sim.incidents}
              onIncidentClick={sim.setSelectedIncident}
              onManualDispatch={sim.manualDispatch}
              onDispatchClick={(zoneId, idx) => setShowFleetModal({ zoneId, idx })}
              onAbort={sim.abortDrone}
              activeLiveFeed={activeLiveFeed}
              setActiveLiveFeed={setActiveLiveFeed}
              videoMaximized={videoMaximized}
              setVideoMaximized={setVideoMaximized}
            />
          </div>
          
          <div className="h-64 shrink-0">
            <AuditLog entries={sim.auditLog} />
          </div>
        </div>

        {/* Right Column: Mission Control & Alerts */}
        <div className="flex-[60] w-full max-w-2xl min-w-[30rem] min-h-0 flex flex-col p-2 pl-0 gap-1.5">
          <ManualCommandPanel onManualDispatch={sim.manualDispatch} />

          <button
            onClick={() => setShowFleetModal(true)}
            className="w-full flex items-center justify-between bg-white/5 hover:bg-white hover:text-black border border-white/10 px-6 py-4 rounded-2xl shadow-xl transition-all group mb-1.5 active:scale-95 translate-y-0 hover:-translate-y-0.5"
          >
            <div className="flex items-center gap-4">
              <Activity size={20} className="group-hover:animate-ping text-white/60 group-hover:text-black" />
              <span className="text-[11px] font-black tracking-[0.3em] uppercase italic">Drone Status List</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-white/20 group-hover:text-black/40 uppercase tracking-widest">System-Connected</span>
            </div>
          </button>

          <div className="flex-[5] basis-0 min-h-0 overflow-hidden flex flex-col">
            <AlertsPanel
              incidents={sim.incidents}
              onSelect={sim.setSelectedIncident}
              onReject={sim.rejectIncident}
              selectedId={sim.selectedIncident?.id}
            />
          </div>

          <div className="flex-[7] basis-0 min-h-0 overflow-hidden flex flex-col">
            <ActiveMissionsPanel drones={sim.drones} onOpenFeed={setActiveLiveFeed} />
          </div>
        </div>
      </div>

      {/* Decision Modal Overlay - Now Centered & Contained as requested */}
      {sim.selectedIncident && (
        <div className="fixed inset-0 z-[50000] flex items-center justify-center bg-black/60 backdrop-blur-2xl animate-in fade-in duration-300">
          <div className="relative w-full max-w-6xl h-[70vh] flex flex-col bg-black/80 border-2 border-white/10 rounded-[2.5rem] overflow-hidden shadow-[0_40px_120px_rgba(0,0,0,0.8)] animate-in zoom-in-95 duration-300">
            <div className="absolute top-8 right-8 z-[50001]">
              <button 
                onClick={() => sim.setSelectedIncident(null)} 
                className="p-3 bg-white/5 hover:bg-red-600/20 text-white hover:text-red-500 rounded-2xl transition-all border border-white/5 group active:scale-95 shadow-xl"
              >
                <X size={24} className="group-hover:rotate-90 transition-all duration-500" />
              </button>
            </div>
            <div className="flex-1 w-full min-h-0">
              <DecisionPanel
                incident={sim.selectedIncident}
                onApprove={(id) => {
                  sim.confirmIncident(id);
                  sim.setSelectedIncident(null);
                }}
                onReject={(id) => {
                  sim.rejectIncident(id);
                  sim.setSelectedIncident(null);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Fleet Telemetry Modal */}
      {showFleetModal && (
        <DroneFleetPanel
          drones={sim.drones}
          expanded={true}
          initialView={typeof showFleetModal === 'object' ? showFleetModal : null}
          onClose={() => setShowFleetModal(false)}
        />
      )}

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
