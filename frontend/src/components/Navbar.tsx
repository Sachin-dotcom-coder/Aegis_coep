import { Shield, Radio, Clock } from 'lucide-react';
import { Drone, Incident } from '@/lib/types';

interface Props {
  drones: Drone[];
  incidents: Incident[];
}

export function Navbar({ drones, incidents }: Props) {
  const activeDrones = drones.filter(d => d.status !== 'idle').length;
  const activeIncidents = incidents.filter(i => !['resolved', 'rejected', 'logged'].includes(i.status)).length;
  const now = new Date();

  return (
    <header className="h-11 flex items-center justify-between px-5 border-b border-border/50 bg-card/60">
      <div className="flex items-center gap-3">
        <Shield size={16} className="text-foreground/80" />
        <span className="text-sm font-semibold tracking-[0.15em] text-foreground" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>AEGIS SHIELD</span>
      </div>

      <div className="flex items-center gap-6 text-[10px] font-mono text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Radio size={9} className="text-foreground/60" />
          <span className="text-foreground/60">ONLINE</span>
        </div>
        <span>{activeDrones} deployed</span>
        <span>{activeIncidents} alerts</span>
        <div className="flex items-center gap-1.5">
          <Clock size={9} />
          <span>{now.toLocaleTimeString('en-US', { hour12: false })}</span>
        </div>
      </div>
    </header>
  );
}
