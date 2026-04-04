import { useState } from 'react';
import { Drone } from '@/lib/types';
import { DISPATCH_ZONES } from '@/lib/simulation';
import { Battery, ChevronDown, ChevronRight, Navigation, Maximize2, Minimize2 } from 'lucide-react';

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

function batteryColor(level: number) {
  if (level > 60) return 'bg-foreground/70';
  if (level > 30) return 'bg-foreground/50';
  return 'bg-foreground/30';
}

export function DroneFleetPanel({ drones }: Props) {
  const [expandedZone, setExpandedZone] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

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
                onClick={() => !expanded && setExpandedZone(isOpen ? null : zone.id)}
                className={`w-full flex items-center gap-3 rounded-md transition-colors text-left ${
                  expanded ? 'mb-6 cursor-default' : 'py-2 px-2.5 hover:bg-white/10'
                }`}
              >
                {!expanded && (isOpen ? <ChevronDown size={14} className="text-white/60" /> : <ChevronRight size={14} className="text-white/60" />)}
                <span className={`${expanded ? 'text-xl' : 'text-[11px]'} font-bold text-white tracking-wider`}>
                  UNIT-{idx.toString().padStart(2, '0')}
                </span>
                <span className={`${expanded ? 'text-sm' : 'text-[9px]'} text-white/40 font-mono ml-2 uppercase tracking-wide truncate`}>
                  {zone.name}
                </span>
                <span className={`ml-auto font-mono text-white/60 ${expanded ? 'text-sm' : 'text-[9px]'}`}>
                  {activeCount > 0 ? `${activeCount} ACTIVE` : 'READY'}
                </span>
              </button>
              
              {isOpen && (
                <div className={`${expanded ? 'space-y-3' : 'ml-5 space-y-1 pb-1'}`}>
                  {zoneDrones.map(drone => {
                    const st = statusLabel(drone.status);
                    return (
                      <div key={drone.id} className={`flex items-center gap-4 rounded-md bg-white/5 ${expanded ? 'p-4' : 'py-1.5 px-2'}`}>
                        <span className={`${expanded ? 'text-sm' : 'text-[10px]'} font-mono text-white/60 w-20 truncate`}>
                          {drone.id.replace('drone_', 'D-')}
                        </span>
                        <span className={`${expanded ? 'text-[10px] px-3 py-1' : 'text-[8px] px-1.5 py-0.5'} font-bold rounded bg-white/10 text-white tracking-widest`}>
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
    </div>
  );
}
