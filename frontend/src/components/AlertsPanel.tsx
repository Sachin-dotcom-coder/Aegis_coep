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
    <div className={`glass-panel flex flex-col transition-all duration-300 ${
      expanded ? 'fixed inset-0 z-[20000] bg-black p-8' : 'h-full p-3 bg-black'
    }`}>
      <div className="flex items-center gap-3 mb-6">
        <AlertTriangle size={expanded ? 24 : 13} className="text-white/60" />
        <h3 className={`${expanded ? 'text-2xl' : 'text-xs'} font-semibold tracking-widest text-white uppercase font-sans`}>
          Active Strategic Alerts
        </h3>
        <span className={`${expanded ? 'text-lg px-4 py-1' : 'text-[10px] px-2 py-0.5'} ml-auto rounded-full bg-white/10 text-white font-mono`}>
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
              className={`group relative rounded-md cursor-pointer transition-all border ${
                expanded ? 'p-6 border-white/20 hover:bg-white/5' : 'p-2.5 border-transparent hover:bg-white/10'
              } ${
                selectedId === inc.id
                  ? 'bg-white/10 border-white/40'
                  : inc.type === 'manual_deployment' ? 'bg-blue-500/5 border-blue-500/20' : 'bg-transparent'
              }`}
            >
              {inc.type === 'manual_deployment' ? (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    // For manual deployments, we use the same onReject but we should ensure it recalls
                    onReject(inc.id);
                  }}
                  className="absolute top-2 right-2 px-2 py-1 bg-red-600 hover:bg-red-500 text-white text-[9px] font-black tracking-widest rounded transition-all opacity-0 group-hover:opacity-100 uppercase"
                >
                  Abort
                </button>
              ) : (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onReject(inc.id);
                  }}
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 text-red-500 transition-all rounded"
                  title="Dismiss Alert"
                >
                  <X size={14} />
                </button>
              )}

              <div className="flex items-center justify-between mb-3 pr-6" onClick={() => onSelect(inc)}>
                <div className="flex items-center gap-2">
                  <span className={`${expanded ? 'text-xl' : 'text-[11px]'} font-medium text-white truncate`}>
                    {getIncidentLabel(inc.type as IncidentType)}
                  </span>
                  {inc.type === 'manual_deployment' && (
                    <span className="px-1.5 py-0.5 bg-blue-500 text-white text-[8px] font-black rounded uppercase tracking-tighter">Manual</span>
                  )}
                </div>
                <span className={`${expanded ? 'text-xs px-3 py-1' : 'text-[8px] px-1.5 py-0.5'} font-bold rounded ${sev.cls}`}>
                  {sev.text}
                </span>
              </div>
              <div className={`flex items-center gap-6 text-white/60 font-mono ${expanded ? 'text-sm' : 'text-[10px]'}`} onClick={() => onSelect(inc)}>
                <span>PRIORITY: {inc.priorityScore.toFixed(1)}</span>
                {inc.type !== 'manual_deployment' && (
                  <span>CONFIDENCE: {(inc.detectionConfidence * 100).toFixed(0)}%</span>
                )}
                <span className="ml-auto uppercase tracking-widest">{inc.status.replace(/_/g, ' ')}</span>
              </div>
            </div>
          );
        })}
        {active.length === 0 && (
          <div className={`text-center text-white/40 font-sans ${expanded ? 'text-xl py-20' : 'text-xs py-8'}`}>
            No active alerts detected. Monitoring Pune sector...
          </div>
        )}
      </div>
    </div>
  );
}
