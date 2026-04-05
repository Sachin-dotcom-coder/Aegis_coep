import { useState } from 'react';
import { Incident, IncidentType } from '@/lib/types';
import { getIncidentLabel } from '@/lib/simulation';
import { AlertTriangle, Maximize2, Minimize2, X } from 'lucide-react';

interface Props {
  incidents: Incident[];
  onSelect: (incident: Incident) => void;
  onReject: (id: string) => void;
  selectedId?: string;
}

function severityTag(severity: number) {
  if (severity >= 8) return { text: 'CRITICAL', cls: 'bg-foreground text-background' };
  if (severity >= 6) return { text: 'MEDIUM', cls: 'bg-secondary text-foreground/80' };
  return { text: 'LOW', cls: 'bg-secondary text-muted-foreground' };
}

export function AlertsPanel({ incidents, onSelect, onReject, selectedId }: Props) {
  const [expanded, setExpanded] = useState(false);
  const active = incidents.filter(i => !['resolved', 'rejected', 'logged'].includes(i.status)).slice(0, 20);

  return (
    <div className={`glass-panel flex flex-col transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] ${
      expanded ? 'fixed inset-0 z-[20000] bg-black/95 backdrop-blur-3xl p-10' : 'h-full p-4 bg-black/40 backdrop-blur-xl'
      }`}>
      <div className="flex items-center gap-3 mb-6">
<<<<<<< Updated upstream
        <AlertTriangle size={expanded ? 24 : 16} className="text-white/60" />
        <h3 className={`${expanded ? 'text-2xl' : 'text-[15px]'} font-semibold tracking-widest text-white uppercase font-sans`}>
=======
        <AlertTriangle size={expanded ? 24 : 13} className="text-white/60" />
        <h3 className={`${expanded ? 'text-4xl' : 'text-sm'} font-black tracking-[0.25em] text-transparent bg-clip-text bg-gradient-to-r from-white via-white/80 to-white/40 uppercase font-display drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]`}>
>>>>>>> Stashed changes
          Active Alerts
        </h3>
        <span className={`${expanded ? 'text-lg px-4 py-1' : 'text-[13px] px-2 py-0.5'} ml-auto rounded-full bg-white/10 text-white font-mono`}>
          {active.length}
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-2 rounded-lg bg-white/5 text-white hover:bg-white/10 transition-all hover:scale-110"
        >
          {expanded ? <Minimize2 size={24} /> : <Maximize2 size={12} />}
        </button>
      </div>

      <div className={`flex-1 overflow-y-auto scrollbar-thin ${expanded ? 'grid grid-cols-2 gap-4' : 'space-y-1'}`}>
        {active.map((inc) => {
          const sev = severityTag(inc.severity);
          return (
            <div
              key={inc.id}
              className={`group relative rounded-xl cursor-pointer transition-all duration-300 border ${
                expanded ? 'p-6 border-white/10 hover:bg-white/5 hover:border-white/30 hover:scale-[1.01] shadow-2xl' : 'p-3 border-transparent hover:bg-white/[0.08] hover:scale-[1.02]'
                } ${selectedId === inc.id
                  ? 'bg-gradient-to-r from-white/10 to-transparent border-l-4 border-l-white border-y-white/10 border-r-white/10'
                  : inc.type === 'manual_deployment' ? 'bg-blue-500/10 border-blue-500/30' : 'bg-transparent'
                }`}
            >
              <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-all">
                <button
                  onClick={(e) => { e.stopPropagation(); onReject(inc.id); }}
                  className="p-1 hover:bg-red-500/20 text-red-500 rounded"
                  title="Dismiss Alert"
                >
                  <X size={14} />
                </button>
              </div>

              <div className="flex items-center justify-between mb-3 pr-6" onClick={() => onSelect(inc)}>
                <div className="flex items-center gap-2">
                  <span className={`${expanded ? 'text-2xl font-black tracking-tight' : 'text-xs font-bold tracking-wide'} text-white truncate drop-shadow-md`}>
                    {getIncidentLabel(inc.type as IncidentType)}
                  </span>
                  {inc.type === 'manual_deployment' && (
                    <span className="px-1.5 py-0.5 bg-blue-500 text-white text-[11px] font-black rounded uppercase tracking-tighter">Manual</span>
                  )}
                  {inc.status === 'silent' && (
                    <span className="px-1.5 py-0.5 bg-white/10 text-white/40 text-[9px] font-bold rounded uppercase tracking-widest border border-white/10">Silent Log</span>
                  )}
                </div>
                <span className={`${expanded ? 'text-xs px-3 py-1' : 'text-[11px] px-1.5 py-0.5'} font-bold rounded ${sev.cls}`}>
                  {sev.text}
                </span>
              </div>
              <div className={`flex items-center gap-6 text-white/50 font-mono tracking-widest uppercase ${expanded ? 'text-sm' : 'text-[10px]'}`} onClick={() => onSelect(inc)}>
                <span>PRIORITY: {inc.priorityScore.toFixed(1)}</span>
                {inc.type !== 'manual_deployment' && (
                  <span className={inc.status === 'silent' ? 'text-white/20' : ''}>
                    CONFIDENCE: {(inc.detectionConfidence * 100).toFixed(0)}%
                  </span>
                )}
                <span className={`ml-auto uppercase tracking-widest ${inc.status === 'silent' ? 'text-white/20' : ''}`}>
                  {inc.status.replace(/_/g, ' ')}
                </span>
              </div>
            </div>
          );
        })}
        {active.length === 0 && (
          <div className={`text-center text-white/40 font-sans ${expanded ? 'text-xl py-20' : 'text-sm py-8'}`}>
            No active alerts detected. Monitoring Pune sector...
          </div>
        )}
      </div>
    </div>
  );
}
