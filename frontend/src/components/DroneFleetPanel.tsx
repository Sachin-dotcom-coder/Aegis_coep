import { useState } from 'react';
import { Drone } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Battery, ChevronDown, ChevronRight, Navigation, Maximize2, Minimize2, X, Activity, Scan, ShieldAlert, Radio } from 'lucide-react';
import { Drone3DView } from './Drone3DView';

interface Props {
  drones: Drone[];
  expanded?: boolean;
  onClose?: () => void;
}

export function DroneFleetPanel({ drones, expanded: externalExpanded, onClose }: Props) {
  const [expandedZone, setExpandedZone] = useState<string | null>(null);
  const [selectedUnitView, setSelectedUnitView] = useState<{ zoneId: string; idx: number } | null>(null);

  const expanded = !!externalExpanded;

  const grouped = DISPATCH_ZONES.map((zone, idx) => ({
    zone,
    idx: idx + 1,
    drones: drones.filter(d => d.zoneId === zone.id),
  }));

  const activeDrones = drones.filter(d => d.status !== 'idle').length;

  return (
    <div className="fixed inset-0 z-[30000] flex items-center justify-center bg-black/90 backdrop-blur-3xl p-10 animate-in fade-in duration-500">
      <div className="relative w-full max-w-4xl h-full flex flex-col bg-black border border-white/10 rounded-[40px] shadow-[0_40px_120px_rgba(0,0,0,1)] overflow-hidden">
        {/* Terminal Header */}
        <div className="p-12 border-b border-white/5 flex items-center justify-between shrink-0">
          <div className="flex flex-col">
            <h3 className="text-4xl font-black tracking-[0.4em] text-white uppercase italic font-mono leading-none">Drone Logistics Center</h3>
            <div className="flex items-center gap-3 mt-4">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[12px] font-mono text-white/30 uppercase tracking-[0.6em]">Node Link Established</span>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-white/20 hover:text-white transition-all flex flex-col items-center gap-4 group"
            >
              <X size={32} className="group-hover:rotate-90 transition-transform duration-500" />
              <span className="text-[10px] font-black tracking-[0.4em] uppercase">Close View</span>
            </button>
          )}
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto scrollbar-none p-12">
          {!selectedUnitView ? (
            /* Hub Selection Mode: Vertical Grid of 5 Hubs */
            <div className="flex flex-col gap-4">
              {grouped.map(({ zone, idx }) => (
                <div
                  key={zone.id}
                  onClick={() => setSelectedUnitView({ zoneId: zone.id, idx })}
                  className="group flex items-center justify-between border-b border-white/5 py-8 px-8 transition-all duration-300 cursor-pointer hover:bg-white/[0.03] rounded-3xl"
                >
                  <div className="flex flex-col">
                    <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.6em] mb-2">Station 0{idx}</span>
                    <h4 className="text-2xl font-black text-white/40 group-hover:text-white transition-all tracking-[0.2em] uppercase italic">{zone.name}</h4>
                  </div>
                  <div className="text-right">
                    <span className="text-2xl font-black text-white/10 group-hover:text-white/60 transition-all font-mono italic tracking-widest uppercase">View Units</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            /* Selected Hub Ledger: List of 3 Drones (No individual boxes) */
            <div className="flex flex-col">
              <div className="flex items-center justify-between mb-12">
                <button
                  onClick={() => setSelectedUnitView(null)}
                  className="text-white/30 hover:text-white flex items-center gap-2 text-[10px] font-black tracking-widest uppercase"
                >
                  Back to Stations
                </button>
                <span className="text-2xl font-black text-white italic tracking-widest uppercase">{DISPATCH_ZONES.find(z => z.id === selectedUnitView.zoneId)?.name} Status List</span>
              </div>

              <div className="flex flex-col gap-2">
                {drones.filter(d => d.zoneId === selectedUnitView.zoneId).map((drone) => {
                  const droneNum = drone.id.replace('drone_', '');
                  return (
                    <div key={drone.id} className="group flex items-center gap-12 py-8 transition-all duration-300 border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                      {/* Holographic Unit Visualizer */}
                      <div className="w-48 h-32 relative overflow-hidden bg-transparent shrink-0">
                        <Drone3DView drones={[drone]} />
                      </div>

                      {/* Unit ID */}
                      <div className="w-32 shrink-0">
                        <span className="text-[9px] font-mono text-white/10 uppercase tracking-[0.3em] block mb-2">Identifier</span>
                        <span className="text-xl font-black text-white italic tracking-wider uppercase">Unit {droneNum}</span>
                      </div>

                      {/* Status Telemetry */}
                      <div className="flex-1">
                        <div className="flex flex-col">
                          <span className="text-[9px] font-mono text-white/10 uppercase tracking-[0.3em] mb-2">Current Task</span>
                          <div className="flex items-center gap-4">
                            <span className={`text-2xl font-black tracking-[0.2em] uppercase ${drone.status === 'idle' ? 'text-white/20' :
                                drone.status === 'on_site' ? 'text-red-500' :
                                  drone.status === 'charging' ? 'text-green-500' :
                                    'text-blue-500'
                              } italic`}>
                              {drone.status.replace('_', ' ')}
                            </span>
                            {(drone.status === 'en_route' || drone.status === 'recalled') && drone.eta_seconds !== undefined && (
                              <span className="text-[10px] font-mono text-blue-400 font-black tracking-widest px-3 py-1 bg-blue-400/10 rounded-lg">
                                ETA: {Math.floor(drone.eta_seconds / 60)}M {drone.eta_seconds % 60}S
                              </span>
                            )}
                          </div>

                          {/* Mission/Charging Progress Bar */}
                          {(drone.status !== 'idle' && drone.status !== 'on_site') && (
                            <div className="mt-4 w-full max-w-md">
                              <div className="flex justify-between text-[8px] font-mono text-white/20 uppercase tracking-widest mb-1.5">
                                <span>{drone.status === 'charging' ? 'Recharge Level' : 'Vector Progress'}</span>
                                <span>{Math.round(drone.status === 'charging' ? (drone.charging_progress || 0) : (drone.path_progress || 0))}%</span>
                              </div>
                              <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                                <div
                                  className={`h-full transition-all duration-1000 ${drone.status === 'charging' ? 'bg-green-500' : 'bg-blue-500'
                                    }`}
                                  style={{ width: `${drone.status === 'charging' ? (drone.charging_progress || 0) : (drone.path_progress || 0)}%` }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Power Capacity with Tricolor Iconography */}
                      <div className="text-right flex items-center justify-end gap-6 w-48 shrink-0">
                        <div className="flex flex-col text-right">
                          <span className="text-[9px] font-mono text-white/10 uppercase tracking-[0.3em] mb-1">Reserve</span>
                          <div className="flex items-center gap-3 justify-end">
                            <span className={`text-xl font-black font-mono tracking-tighter ${drone.battery < 20 ? 'text-red-500 animate-pulse' :
                                drone.battery < 75 ? 'text-orange-500' : 'text-green-500'
                              }`}>
                              {drone.battery.toFixed(0)}%
                            </span>
                            <Battery
                              size={20}
                              className={`${drone.battery < 20 ? 'text-red-500 animate-pulse' :
                                  drone.battery < 75 ? 'text-orange-500' : 'text-green-500'
                                }`}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
