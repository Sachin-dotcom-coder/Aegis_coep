import { useState } from 'react';
import { Incident } from '@/lib/types';
import { DISPATCH_ZONES, calculatePriority, getIncidentLabel } from '@/lib/simulation';
import { BrainCircuit, Maximize2, Minimize2 } from 'lucide-react';

interface Props {
  incident: Incident | null;
}

function ConfBar({ label, value, max = 1 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px] font-mono">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-foreground">{value <= 1 ? (value * 100).toFixed(0) + '%' : value.toFixed(2)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700 bg-foreground/60" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function DecisionPanel({ incident }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!incident) {
    return (
      <div className="glass-panel p-3 h-full flex flex-col items-center justify-center">
        <BrainCircuit size={20} className="text-muted-foreground mb-2" />
        <p className="text-xs text-muted-foreground font-sans">Select an alert to view decision breakdown</p>
      </div>
    );
  }

  const zone = DISPATCH_ZONES.find(z => z.id === incident.zoneId)!;
  const priority = calculatePriority(incident, zone, 2);
  const actionLabel = incident.decisionConfidence > 0.8 ? 'AUTO DISPATCH' : incident.decisionConfidence >= 0.5 ? 'HUMAN CONFIRM' : 'SILENT LOG';

  return (
    <div className={`glass-panel p-3 flex flex-col ${expanded ? 'fixed inset-4 z-40' : 'h-full'}`}>
      <div className="flex items-center gap-2 mb-3">
        <BrainCircuit size={13} className="text-foreground/60" />
        <h3 className="text-xs font-semibold tracking-wider text-foreground/80 uppercase font-sans">Decision Engine</h3>
        <button onClick={() => setExpanded(!expanded)} className="ml-auto p-1 rounded text-muted-foreground hover:text-foreground transition-colors">
          {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
        </button>
      </div>

      <div className="mb-3 p-2 rounded-md bg-secondary/40 border border-border/30">
        <div className="text-[11px] font-medium text-foreground mb-0.5">{getIncidentLabel(incident.type)}</div>
        <div className="text-[9px] text-muted-foreground font-mono">{incident.cameraSource} · {zone.name}</div>
      </div>

      <div className="space-y-2.5 flex-1 overflow-y-auto scrollbar-thin">
        <ConfBar label="Detection Confidence" value={incident.detectionConfidence} />
        <ConfBar label="Zone Reliability" value={zone.reliability} />
        <ConfBar label="Decision Confidence" value={incident.decisionConfidence} />

        <div className="border-t border-border/30 pt-2 mt-2">
          <div className="text-[10px] text-muted-foreground font-mono mb-2">PRIORITY FORMULA</div>
          <div className="grid grid-cols-2 gap-1.5 text-[9px] font-mono">
            <div className="flex justify-between"><span className="text-muted-foreground">Severity</span><span>{priority.severity}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Zone Risk</span><span>×{priority.zoneRisk}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Time Weight</span><span>×{priority.timeWeight}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Recency</span><span>×{priority.recencyBoost}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Multi-Cam</span><span>×{priority.multiCamBonus}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">ETA Penalty</span><span>-{priority.etaPenalty.toFixed(2)}</span></div>
          </div>
        </div>

        <div className="p-2.5 rounded-md bg-secondary/50 border border-border/30 text-center">
          <div className="text-[9px] text-muted-foreground font-mono mb-0.5">ACTION</div>
          <div className="text-sm font-semibold tracking-wider text-foreground">{actionLabel}</div>
          <div className="text-[10px] font-mono text-muted-foreground mt-0.5">Score: {incident.priorityScore.toFixed(2)}</div>
        </div>
      </div>
    </div>
  );
}
