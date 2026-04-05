import { useState } from 'react';
import { AuditEntry } from '@/lib/types';
import { ScrollText, Maximize2, Minimize2 } from 'lucide-react';

interface Props {
  entries: AuditEntry[];
}

function actionStyle(action: string) {
  switch (action) {
    case 'AUTO_DISPATCH':
    case 'INCIDENT_RESOLVED':
    case 'SYSTEM_BOOT':
      return 'text-foreground';
    case 'HUMAN_CONFIRM':
    case 'MANUAL_OVERRIDE':
      return 'text-foreground/80';
    default:
      return 'text-muted-foreground';
  }
}

export function AuditLog({ entries }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`glass-panel flex flex-col transition-all duration-300 ${
      expanded ? 'fixed inset-0 z-[20000] bg-black p-8' : 'h-full p-3 bg-black'
    }`}>
      <div className="flex items-center gap-3 mb-6">
        <ScrollText size={expanded ? 24 : 13} className="text-white/60" />
        <h3 className={`${expanded ? 'text-2xl' : 'text-sm'} font-semibold tracking-widest text-white uppercase font-sans`}>
          System Audit Log
        </h3>
        <span className={`${expanded ? 'text-lg px-4 py-1' : 'text-[13px]'} ml-auto font-mono text-white/40 uppercase tracking-widest`}>
          {entries.length} LOGGED EVENTS
        </span>
        <button 
          onClick={() => setExpanded(!expanded)} 
          className="p-2 rounded-lg bg-white/5 text-white hover:bg-white/10 transition-all hover:scale-110"
        >
          {expanded ? <Minimize2 size={24} /> : <Maximize2 size={12} />}
        </button>
      </div>

      <div className={`flex-1 overflow-y-auto scrollbar-thin ${expanded ? 'space-y-2' : 'space-y-0.5'}`}>
        {entries.slice(0, 100).map(entry => (
          <div 
            key={entry.id} 
            className={`flex items-center gap-6 font-mono border-b border-white/5 last:border-0 ${
              expanded ? 'py-4 text-sm' : 'py-2 text-[13px]'
            }`}
          >
            <span className="text-white/30 w-32 shrink-0 font-bold">
              {new Date(entry.timestamp).toLocaleTimeString('en-US', { hour12: false })}
            </span>
            <span className={`w-48 shrink-0 font-bold tracking-tighter ${actionStyle(entry.action)}`}>
              {entry.action}
            </span>
            <span className="text-white/60 flex-1 truncate uppercase tracking-wide">
              {entry.details}
            </span>
          </div>
        ))}
        {entries.length === 0 && (
          <div className="text-center text-white/20 py-10 font-mono uppercase tracking-[0.2em]">
            SYSTEM LOG EMPTY
          </div>
        )}
      </div>
    </div>
  );
}
