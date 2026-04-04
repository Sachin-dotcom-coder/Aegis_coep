import { useState } from 'react';
import { Drone } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Battery, ChevronDown, ChevronRight, Navigation, Maximize2, Minimize2, X, Activity, Scan, ShieldAlert } from 'lucide-react';
import { Drone3DView } from './Drone3DView';

interface Props {
  drones: Drone[];
}

function statusLabel(status: string) {
  switch (status) {
    case 'idle': return { text: 'IDLE', cls: 'text-muted-foreground' };
    case 'en_route': return { text: 'EN ROUTE', cls: 'text-foreground' };
    case 'on_site': return { text: 'ON SITE', cls: 'text-foreground font-bold' };
    case 'returning': return { text: 'RETURNING', cls: 'text-muted-foreground' };
    case 'recalled': return { text: 'RECALLED', cls: 'text-muted-foreground' };
    default: return { text: status, cls: 'text-muted-foreground' };
  }
}

export function DroneFleetPanel({ drones }: Props) {
  const [expandedZone, setExpandedZone] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [selectedUnitView, setSelectedUnitView] = useState<{ zoneId: string; idx: number } | null>(null);

  const grouped = DISPATCH_ZONES.map((zone, idx) => ({
    zone,
    idx: idx + 1,
    drones: drones.filter(d => d.zoneId === zone.id),
  }));

  const activeDrones = drones.filter(d => d.status !== 'idle').length;

  return (
    <div className={`glass-panel transition-all duration-300 flex flex-col ${
      expanded ? 'fixed inset-0 z-[20000] bg-black p-8' : 'h-full p-3 bg-black'
    }`}>
      <div className="flex items-center gap-3 mb-6">
        <Navigation size={expanded ? 24 : 13} className="text-white/60" />
        <h3 className={`${expanded ? 'text-2xl' : 'text-xs'} font-semibold tracking-widest text-white uppercase font-sans`}>
          Drone Fleet Operations
        </h3>
        <span className={`${expanded ? 'text-lg px-4 py-1' : 'text-[10px] px-2 py-0.5'} ml-auto rounded-full bg-white/10 text-white font-mono`}>
          {activeDrones} ACTIVE / {drones.length} TOTAL
        </span>
        <button 
          onClick={() => setExpanded(!expanded)} 
          className="p-2 rounded-lg bg-white/5 text-white hover:bg-white/10 transition-all hover:scale-110"
        >
          {expanded ? <Minimize2 size={24} /> : <Maximize2 size={12} />}
        </button>
      </div>

      <div className={`flex-1 overflow-y-auto scrollbar-thin ${expanded ? 'grid grid-cols-2 gap-8' : 'space-y-1'}`}>
        {grouped.map(({ zone, idx, drones: zoneDrones }) => {
          const isOpen = expandedZone === zone.id || expanded;
          const activeCount = zoneDrones.filter(d => d.status !== 'idle').length;
          return (
            <div key={zone.id} className={expanded ? 'border border-white/10 p-6 rounded-xl bg-white/5' : ''}>
              <button
                onClick={() => {
                  if (expanded) {
                    setSelectedUnitView({ zoneId: zone.id, idx });
                  } else {
                    setExpandedZone(isOpen ? null : zone.id);
                  }
                }}
                className={`w-full flex items-center gap-3 rounded-md transition-colors text-left group ${
                  expanded ? 'mb-6 py-4 px-6 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/30' : 'py-2 px-2.5 hover:bg-white/10'
                }`}
              >
                {!expanded && (isOpen ? <ChevronDown size={14} className="text-white/60" /> : <ChevronRight size={14} className="text-white/60" />)}
                <span className={`${expanded ? 'text-2xl' : 'text-[11px]'} font-bold text-white tracking-wider`}>
                  UNIT-{idx.toString().padStart(2, '0')}
                </span>
                <span className={`${expanded ? 'text-base' : 'text-[9px]'} text-white/40 font-mono ml-2 uppercase tracking-widest truncate`}>
                  {zone.name}
                </span>
                
                {expanded && (
                  <div className="ml-auto flex items-center gap-4">
                    <span className="font-mono text-white/40 text-xs uppercase tracking-[0.2em]">
                      {activeCount} Active Units
                    </span>
                    <div className="p-3 rounded-full bg-white/10 group-hover:bg-white/20 transition-colors">
                      <Scan size={20} className="text-white/80" />
                    </div>
                  </div>
                )}
                
                {!expanded && (
                  <span className={`ml-auto font-mono text-white/60 text-[9px]`}>
                    {activeCount > 0 ? `${activeCount} ACTIVE` : 'READY'}
                  </span>
                )}
              </button>
              
              {isOpen && (
                <div className={`${expanded ? 'space-y-3 px-6' : 'ml-5 space-y-1 pb-1'}`}>
                  {zoneDrones.map(drone => {
                    const st = statusLabel(drone.status);
                    return (
                      <div key={drone.id} className={`flex items-center gap-4 rounded-md bg-white/5 ${expanded ? 'p-4' : 'py-1.5 px-2'}`}>
                        <span className={`${expanded ? 'text-sm' : 'text-[10px]'} font-mono text-white/60 w-20 truncate`}>
                          {drone.id.replace('drone_', 'D-')}
                        </span>
                        <span className={`${expanded ? 'text-[10px] px-3 py-1' : 'text-[8px] px-1.5 py-0.5'} font-bold rounded bg-white/10 text-white tracking-widest uppercase`}>
                          {st.text}
                        </span>
                        <div className="ml-auto flex items-center gap-3 flex-1 max-w-[200px]">
                          <Battery size={expanded ? 18 : 10} className={drone.battery < 20 ? 'text-red-500 animate-pulse' : 'text-white/40'} />
                          <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-1000 ${
                                drone.battery < 20 ? 'bg-red-500' : 'bg-white/60'
                              }`}
                              style={{ width: `${drone.battery}%` }}
                            />
                          </div>
                          <span className={`${expanded ? 'text-sm' : 'text-[9px]'} font-mono text-white/80 w-10 text-right`}>
                            {drone.battery.toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Selected Unit 3D Drilldown Modal */}
      {selectedUnitView && (
        <div className="fixed inset-0 z-[30000] flex items-center justify-center p-8 bg-black/95 backdrop-blur-3xl animate-in fade-in duration-500">
          <div className="relative w-full h-full max-w-7xl flex flex-col bg-black/80 border-2 border-white/20 rounded-3xl overflow-hidden shadow-[0_0_100px_rgba(255,255,255,0.1)]">
            <div className="absolute top-0 left-0 right-0 h-24 bg-white/5 border-b border-white/10 flex items-center justify-between px-12 z-20">
              <div className="flex items-center gap-6">
                <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center shadow-[0_0_20px_rgba(255,255,255,0.1)]">
                  <ShieldAlert className="text-white" size={24} />
                </div>
                <div>
                  <h2 className="text-3xl font-black tracking-[0.3em] text-white uppercase font-mono">
                    Tactical Unit Drilldown: <span className="text-white/40">D-{selectedUnitView.idx.toString().padStart(2,'0')}</span>
                  </h2>
                  <div className="flex items-center gap-3 mt-1">
                    <Activity size={14} className="text-green-500 animate-pulse" />
                    <span className="text-[10px] font-mono tracking-[0.4em] text-white/40 uppercase">Aegis Neuralink: 100% Signal Integrity</span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setSelectedUnitView(null)}
                className="group flex items-center gap-3 bg-white/10 hover:bg-white hover:text-black transition-all px-6 py-3 rounded-2xl border border-white/10"
              >
                <X size={20} />
                <span className="text-xs font-black tracking-widest uppercase">Terminate Link</span>
              </button>
            </div>
            
            <div className="flex-1 w-full pt-24 pb-8 overflow-hidden">
              <div className="h-full px-8">
                <Drone3DView drones={drones.filter(d => d.zoneId === selectedUnitView.zoneId).slice(0, 3)} />
              </div>
            </div>

            <div className="h-20 bg-white/5 border-t border-white/10 flex items-center px-12 justify-between">
              <div className="flex gap-10">
                <div className="flex flex-col">
                  <span className="text-[10px] font-mono text-white/30 uppercase tracking-widest">Sector Authority</span>
                  <span className="text-sm font-bold text-white tracking-widest uppercase">{DISPATCH_ZONES.find(z => z.id === selectedUnitView.zoneId)?.name}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-mono text-white/30 uppercase tracking-widest">Fleet Status</span>
                  <span className="text-sm font-bold text-green-500 tracking-widest uppercase">All Units Operational</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-mono text-white/20 uppercase tracking-[0.5em]">Classified Aegis Data Loop — Node {selectedUnitView.idx}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
