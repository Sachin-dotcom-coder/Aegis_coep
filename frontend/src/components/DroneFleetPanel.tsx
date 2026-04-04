import { useState } from 'react';
import { Drone } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Battery, ChevronDown, ChevronRight, Navigation, Maximize2, Minimize2, X, Activity, Scan, ShieldAlert, Radio } from 'lucide-react';
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
      expanded ? 'fixed inset-0 z-[20000] bg-black p-8' : 'h-full p-3 bg-black/60 backdrop-blur-xl'
    }`}>
      <div className="flex items-center gap-6 mb-12 border-b border-white/5 pb-8">
        <div className="flex flex-col">
          <h3 className="text-3xl font-black tracking-[0.4em] text-white uppercase italic font-mono leading-none">Aegis Hub Grid</h3>
          <span className="text-[11px] font-mono text-white/20 uppercase tracking-[0.5em] mt-2">Select station for unit drilldown</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 p-2 pb-20">
        {grouped.map(({ zone, idx }) => (
          <div 
            key={zone.id} 
            onClick={() => setSelectedUnitView({ zoneId: zone.id, idx })}
            className="group relative bg-white/[0.03] hover:bg-white/[0.1] border border-white/10 hover:border-white/30 rounded-2xl p-8 transition-all duration-500 cursor-pointer flex flex-col items-center justify-center gap-6 active:scale-95"
          >
            <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center border border-white/10 group-hover:border-white group-hover:shadow-[0_0_30px_rgba(255,255,255,0.2)] transition-all">
               <Radio size={32} className="text-white/40 group-hover:text-white transition-colors" />
            </div>
            
            <div className="text-center">
              <span className="text-[9px] font-black text-white/20 tracking-[0.4em] uppercase">Sector Hub 0{idx}</span>
              <h4 className="text-sm font-black text-white tracking-widest uppercase mt-1">{zone.name}</h4>
              <span className="block text-[10px] font-mono text-white/30 mt-2">UNIT D-{idx.toString().padStart(2, '0')}</span>
            </div>
            
            <div className="mt-4 px-4 py-1.5 border border-white/10 rounded-full group-hover:bg-white group-hover:text-black transition-all">
               <span className="text-[9px] font-black uppercase tracking-[0.3em]">Drilldown</span>
            </div>
          </div>
        ))}
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
