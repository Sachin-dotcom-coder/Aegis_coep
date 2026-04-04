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
    <div className={`glass-panel p-3 flex flex-col ${expanded ? 'fixed inset-4 z-40' : 'h-full'}`}>
      <div className="flex items-center gap-2 mb-2">
        <ScrollText size={13} className="text-foreground/60" />
        <h3 className="text-xs font-semibold tracking-wider text-foreground/80 uppercase font-sans">Audit Log</h3>
        <span className="ml-auto text-[10px] text-muted-foreground font-mono">{entries.length} events</span>
        <button onClick={() => setExpanded(!expanded)} className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors">
          {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-0.5">
        {entries.slice(0, 50).map(entry => (
          <div key={entry.id} className="flex items-start gap-2 py-1 text-[10px] font-mono border-b border-border/20 last:border-0">
            <span className="text-muted-foreground w-16 shrink-0">
              {new Date(entry.timestamp).toLocaleTimeString('en-US', { hour12: false })}
            </span>
            <span className={`w-28 shrink-0 font-medium ${actionStyle(entry.action)}`}>
              {entry.action}
            </span>
            <span className="text-foreground/50 truncate">{entry.details}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
