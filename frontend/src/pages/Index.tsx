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
  const [showFleetModal, setShowFleetModal] = useState(false);
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

      <div className="flex-1 flex overflow-hidden min-h-0" style={{ height: 'calc(100vh - 16rem)' }}>
        <div className="flex-[40] min-w-0 min-h-0 p-2" style={{ height: '100%' }}>
          <div className="relative h-full w-full min-w-0 min-h-0">
            <CityMap
              drones={sim.drones}
              incidents={sim.incidents}
              onIncidentClick={sim.setSelectedIncident}
              onManualDispatch={sim.manualDispatch}
              onAbort={sim.abortDrone}
              activeLiveFeed={activeLiveFeed}
              setActiveLiveFeed={setActiveLiveFeed}
              videoMaximized={videoMaximized}
              setVideoMaximized={setVideoMaximized}
            />
          </div>
        </div>

        <div className="flex-[60] w-full max-w-2xl min-w-[30rem] min-h-0 flex flex-col p-2 pl-0 gap-1.5" style={{ height: '100%' }}>
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

          <div className="flex-[6] basis-0 min-h-0 overflow-hidden flex flex-col">
            <AlertsPanel incidents={sim.incidents} onSelect={sim.setSelectedIncident} selectedId={sim.selectedIncident?.id} />
          </div>

          <div className="flex-[4] basis-0 min-h-0 overflow-hidden flex flex-col">
             <ActiveMissionsPanel drones={sim.drones} onOpenFeed={setActiveLiveFeed} />
          </div>
        </div>
      </div>

      {/* Decision Modal Overlay */}
      {sim.selectedIncident && (
        <div className="fixed inset-0 z-[50000] flex items-center justify-center p-20 bg-black/80 backdrop-blur-3xl animate-in fade-in duration-500">
           <div className="relative w-full max-w-4xl h-[80vh] flex flex-col bg-black border-4 border-white/10 rounded-[40px] overflow-hidden shadow-[0_60px_150px_rgba(0,0,0,1)]">
              <div className="absolute top-8 right-8 z-50">
                <button onClick={() => sim.setSelectedIncident(null)} className="p-4 bg-white/10 hover:bg-red-600 rounded-2xl transition-all text-white"><X size={24} /></button>
              </div>
              <DecisionPanel incident={sim.selectedIncident} />
           </div>
        </div>
      )}

      {/* Fleet Telemetry Modal */}
      {showFleetModal && (
        <DroneFleetPanel 
          drones={sim.drones} 
          expanded={true} 
          onClose={() => setShowFleetModal(false)} 
        />
      )}

      {/* Audit log */}
      <div className="h-48 p-2 pt-0 shrink-0">
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
