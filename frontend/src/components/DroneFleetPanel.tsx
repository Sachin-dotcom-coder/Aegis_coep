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
    <div className={`glass-panel p-3 flex flex-col ${expanded ? 'fixed inset-4 z-40' : 'h-full'}`}>
      <div className="flex items-center gap-2 mb-3">
        <Navigation size={13} className="text-foreground/60" />
        <h3 className="text-xs font-semibold tracking-wider text-foreground/80 uppercase font-sans">Drone Fleet</h3>
        <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-secondary text-muted-foreground font-mono">
          {activeDrones} active / {drones.length}
        </span>
        <button onClick={() => setExpanded(!expanded)} className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors">
          {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-1">
        {grouped.map(({ zone, idx, drones: zoneDrones }) => {
          const isOpen = expandedZone === zone.id;
          const activeCount = zoneDrones.filter(d => d.status !== 'idle').length;
          return (
            <div key={zone.id}>
              <button
                onClick={() => setExpandedZone(isOpen ? null : zone.id)}
                className="w-full flex items-center gap-2 py-2 px-2.5 rounded-md hover:bg-secondary/50 transition-colors text-left"
              >
                {isOpen ? <ChevronDown size={12} className="text-muted-foreground" /> : <ChevronRight size={12} className="text-muted-foreground" />}
                <span className="text-[11px] font-medium text-foreground/90">Dispatch Unit {idx}</span>
                <span className="text-[9px] text-muted-foreground font-mono ml-1">{zone.name}</span>
                <span className="ml-auto text-[9px] font-mono text-muted-foreground">
                  {activeCount > 0 ? `${activeCount} active` : 'all idle'}
                </span>
              </button>
              {isOpen && (
                <div className="ml-5 space-y-1 pb-1">
                  {zoneDrones.map(drone => {
                    const st = statusLabel(drone.status);
                    return (
                      <div key={drone.id} className="flex items-center gap-2 py-1.5 px-2 rounded-md bg-secondary/30">
                        <span className="text-[10px] font-mono text-foreground/60 w-16 truncate">{drone.id.replace('drone_', 'D-')}</span>
                        <span className={`text-[8px] font-medium px-1.5 py-0.5 rounded bg-secondary ${st.cls}`}>{st.text}</span>
                        <div className="ml-auto flex items-center gap-1.5 w-16">
                          <Battery size={10} className={drone.battery < 20 ? 'text-foreground/40' : 'text-muted-foreground'} />
                          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-1000 ${batteryColor(drone.battery)}`}
                              style={{ width: `${drone.battery}%` }}
                            />
                          </div>
                          <span className="text-[9px] font-mono text-muted-foreground w-7 text-right">{drone.battery.toFixed(0)}%</span>
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
