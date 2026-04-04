import { useState } from 'react';
import { Incident } from '@/lib/types';
import { DISPATCH_ZONES, calculatePriority, getIncidentLabel } from '@/lib/simulation';
import { BrainCircuit, Maximize2, Minimize2 } from 'lucide-react';

interface Props {
  incident: Incident | null;
}

function ConfBar({ label, value, max = 1, expanded = false }: { label: string; value: number; max?: number; expanded?: boolean }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="space-y-2">
      <div className={`flex justify-between font-mono ${expanded ? 'text-sm' : 'text-[10px]'}`}>
        <span className="text-white/40">{label}</span>
        <span className="text-white">{value <= 1 ? (value * 100).toFixed(0) + '%' : value.toFixed(2)}</span>
      </div>
      <div className={`${expanded ? 'h-3' : 'h-1.5'} rounded-full bg-white/10 overflow-hidden`}>
        <div className="h-full rounded-full transition-all duration-700 bg-white/60" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function DecisionPanel({ incident }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!incident) {
    return (
      <div className="glass-panel p-3 h-full flex flex-col items-center justify-center bg-black">
        <BrainCircuit size={20} className="text-white/20 mb-2" />
        <p className="text-xs text-white/40 font-sans">Select an alert to view decision breakdown</p>
      </div>
    );
  }

  const zone = DISPATCH_ZONES.find(z => z.id === incident.zoneId)!;
  const priority = calculatePriority(incident, zone, 2);
  const actionLabel = incident.decisionConfidence > 0.8 ? 'AUTO DISPATCH' : incident.decisionConfidence >= 0.5 ? 'HUMAN CONFIRM' : 'SILENT LOG';

  return (
    <div className={`glass-panel transition-all duration-300 flex flex-col ${
      expanded ? 'fixed inset-0 z-[20000] bg-black p-8' : 'h-full p-3 bg-black'
    }`}>
      <div className="flex items-center gap-3 mb-6">
        <BrainCircuit size={expanded ? 24 : 13} className="text-white/60" />
        <h3 className={`${expanded ? 'text-2xl' : 'text-xs'} font-semibold tracking-widest text-white uppercase font-sans`}>
          Aegis Decision Engine
        </h3>
        <button 
          onClick={() => setExpanded(!expanded)} 
          className="ml-auto p-2 rounded-lg bg-white/5 text-white hover:bg-white/10 transition-all hover:scale-110"
        >
          {expanded ? <Minimize2 size={24} /> : <Maximize2 size={12} />}
        </button>
      </div>

      <div className={`mb-6 p-4 rounded-xl bg-white/5 border border-white/10 ${expanded ? 'max-w-xl self-center w-full' : ''}`}>
        <div className={`${expanded ? 'text-2xl' : 'text-[11px]'} font-bold text-white mb-2 uppercase tracking-wider`}>
          {getIncidentLabel(incident.type)}
        </div>
        <div className={`${expanded ? 'text-sm' : 'text-[9px]'} text-white/40 font-mono tracking-widest uppercase`}>
          SOURCE: {incident.cameraSource} · SECTOR: {zone.name}
        </div>
      </div>

      <div className={`space-y-6 flex-1 overflow-y-auto scrollbar-thin ${expanded ? 'max-w-3xl self-center w-full' : ''}`}>
        <div className={expanded ? 'grid grid-cols-3 gap-8' : 'space-y-2.5'}>
          <ConfBar label="DETECTION" value={incident.detectionConfidence} expanded={expanded} />
          <ConfBar label="RELIABILITY" value={zone.reliability} expanded={expanded} />
          <ConfBar label="AI DECISION" value={incident.decisionConfidence} expanded={expanded} />
        </div>

        <div className={`border-t border-white/10 pt-6 mt-6 ${expanded ? 'grid grid-cols-2 gap-12' : ''}`}>
          <div>
            <div className={`text-white/40 font-mono mb-4 tracking-widest uppercase ${expanded ? 'text-xs' : 'text-[10px]'}`}>
              PRIORITY FORMULA BREAKDOWN
            </div>
            <div className={`grid grid-cols-2 gap-x-8 gap-y-3 font-mono ${expanded ? 'text-sm' : 'text-[9px]'}`}>
              <div className="flex justify-between border-b border-white/5 pb-1"><span className="text-white/40">Severity</span><span className="text-white">{priority.severity}</span></div>
              <div className="flex justify-between border-b border-white/5 pb-1"><span className="text-white/40">Zone Risk</span><span className="text-white">×{priority.zoneRisk}</span></div>
              <div className="flex justify-between border-b border-white/5 pb-1"><span className="text-white/40">Time Weight</span><span className="text-white">×{priority.timeWeight}</span></div>
              <div className="flex justify-between border-b border-white/5 pb-1"><span className="text-white/40">Recency</span><span className="text-white">×{priority.recencyBoost}</span></div>
              <div className="flex justify-between border-b border-white/5 pb-1"><span className="text-white/40">Multi-Cam</span><span className="text-white">×{priority.multiCamBonus}</span></div>
              <div className="flex justify-between border-b border-white/5 pb-1"><span className="text-white/40">ETA Penalty</span><span className="text-white">-{priority.etaPenalty.toFixed(2)}</span></div>
            </div>
          </div>

          <div className={`p-6 rounded-2xl bg-white text-black text-center self-center shadow-2xl ${expanded ? 'mt-0' : 'mt-4'}`}>
            <div className="text-[10px] font-bold tracking-widest uppercase mb-1 opacity-60">RECOMMENDED ACTION</div>
            <div className={`${expanded ? 'text-4xl' : 'text-sm'} font-black tracking-tighter`}>{actionLabel}</div>
            <div className={`${expanded ? 'text-sm' : 'text-[9px]'} font-mono mt-2 font-bold opacity-70`}>FINAL PRIORITY SCORE: {incident.priorityScore.toFixed(2)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
