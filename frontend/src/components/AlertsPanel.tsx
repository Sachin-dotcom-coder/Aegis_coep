import { useState } from 'react';
import { Incident } from '@/lib/types';
import { getIncidentLabel } from '@/lib/simulation';
import { AlertTriangle, Maximize2, Minimize2 } from 'lucide-react';

interface Props {
  incidents: Incident[];
  onSelect: (incident: Incident) => void;
  selectedId?: string;
}

function severityTag(severity: number) {
  if (severity >= 8) return { text: 'CRITICAL', cls: 'bg-foreground text-background' };
  if (severity >= 6) return { text: 'MEDIUM', cls: 'bg-secondary text-foreground/80' };
  return { text: 'LOW', cls: 'bg-secondary text-muted-foreground' };
}

export function AlertsPanel({ incidents, onSelect, selectedId }: Props) {
  const [expanded, setExpanded] = useState(false);
  const active = incidents.filter(i => !['resolved', 'rejected', 'logged'].includes(i.status)).slice(0, 20);

  return (
    <div className={`glass-panel p-3 flex flex-col ${expanded ? 'fixed inset-4 z-40' : 'h-full'}`}>
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={13} className="text-foreground/60" />
        <h3 className="text-xs font-semibold tracking-wider text-foreground/80 uppercase font-sans">Active Alerts</h3>
        <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-secondary text-muted-foreground font-mono">{active.length}</span>
        <button onClick={() => setExpanded(!expanded)} className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors">
          {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-1">
        {active.map((inc) => {
          const sev = severityTag(inc.severity);
          return (
            <div
              key={inc.id}
              onClick={() => onSelect(inc)}
              className={`p-2.5 rounded-md cursor-pointer transition-all border ${
                selectedId === inc.id
                  ? 'bg-secondary border-foreground/20'
                  : 'bg-transparent border-transparent hover:bg-secondary/40'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] font-medium text-foreground truncate">{getIncidentLabel(inc.type)}</span>
                <span className={`text-[8px] font-medium px-1.5 py-0.5 rounded ${sev.cls}`}>{sev.text}</span>
              </div>
              <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
                <span>PRI {inc.priorityScore.toFixed(1)}</span>
                <span>CONF {(inc.detectionConfidence * 100).toFixed(0)}%</span>
                <span className="ml-auto uppercase text-[9px]">{inc.status.replace(/_/g, ' ')}</span>
              </div>
            </div>
          );
        })}
        {active.length === 0 && (
          <div className="text-center text-muted-foreground text-xs py-8 font-sans">No active alerts</div>
        )}
      </div>
    </div>
  );
}
