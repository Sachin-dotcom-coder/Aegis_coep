import { useState } from 'react';
import { Incident } from '@/lib/types';
import { DISPATCH_ZONES, calculatePriority, getIncidentLabel } from '@/lib/simulation';
import { BrainCircuit, Check, X } from 'lucide-react';

export interface DecisionPanelProps {
  incident: Incident | null;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
}

function ConfBar({ label, value, max = 1 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between font-mono text-[10px]">
        <span className="text-white/40 uppercase tracking-widest">{label}</span>
        <span className="text-white font-bold">{value <= 1 ? (value * 100).toFixed(0) + '%' : value.toFixed(2)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden border border-white/5">
        <div className="h-full rounded-full transition-all duration-1000 bg-white/80" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function DecisionPanel({ incident, onApprove, onReject }: DecisionPanelProps) {
  if (!incident) return null;

  const zone = DISPATCH_ZONES.find(z => z.id.toLowerCase() === incident.zoneId?.toLowerCase()) || DISPATCH_ZONES[0];
  const priority = calculatePriority(incident, zone, 2);
  const isDeployed = ['auto', 'dispatched', 'in_progress', 'en_route'].includes(incident.status);
  const actionLabel = isDeployed 
    ? 'MISSION DEPLOYED'
    : incident.decisionConfidence > 0.8 
      ? 'AUTO DISPATCH' 
      : incident.decisionConfidence >= 0.3 
        ? 'HUMAN CONFIRM' 
        : 'LOW CONFIDENCE';

  return (
    <div className="h-full flex flex-col p-8 font-sans">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div className="p-2.5 rounded-xl bg-white/5 border border-white/10">
          <BrainCircuit size={20} className="text-white/80" />
        </div>
        <div className="flex flex-col">
          <h3 className="text-sm font-black tracking-[0.3em] text-white uppercase italic">Aegis Decision Engine</h3>
          <span className="text-[10px] text-white/20 font-mono tracking-widest uppercase">Mission Intelligence Layer v4.0</span>
        </div>
      </div>

      {/* Main Breakdown */}
      <div className="grid grid-cols-12 gap-6 flex-1 min-h-0">
        <div className="col-span-12 xl:col-span-8 flex flex-col gap-6">
          <div className="p-8 rounded-2xl bg-white/5 border border-white/10 flex flex-col justify-center gap-2">
            <span className="text-[10px] font-bold text-white/40 tracking-[0.2em] uppercase">Target Classification</span>
            <h2 className="text-3xl font-black text-white italic tracking-tight">{getIncidentLabel(incident.type as any)}</h2>
            <div className="flex items-center gap-4 mt-2">
              <span className="text-[11px] font-mono text-white/60 bg-white/5 px-2 py-1 rounded border border-white/5 uppercase tracking-widest">
                SRC: {incident.cameraSource || 'CAM-MASTER'}
              </span>
              <span className="text-[11px] font-mono text-white/60 bg-white/5 px-2 py-1 rounded border border-white/5 uppercase tracking-widest">
                ZONE: {zone?.name || 'CENTRAL'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="p-5 rounded-2xl bg-white/5 border border-white/10 flex flex-col gap-4">
              <ConfBar label="CNN Detection" value={incident.detectionConfidence} />
              <ConfBar label="Zone Statistics" value={zone?.reliability || 0.8} />
              <ConfBar label="Neural Core" value={incident.decisionConfidence} />
            </div>

            <div className="col-span-2 p-6 rounded-2xl bg-white/5 border border-white/10">
              <div className="text-[10px] font-black text-white/30 tracking-[0.3em] uppercase mb-5">Priority Matrix Breakdown</div>
              <div className="grid grid-cols-2 gap-x-10 gap-y-4 font-mono text-[11px]">
                <div className="flex justify-between items-center border-b border-white/5 pb-2">
                  <span className="text-white/40">Severity</span><span className="text-white font-black">{priority.severity}</span>
                </div>
                <div className="flex justify-between items-center border-b border-white/5 pb-2">
                  <span className="text-white/40">Z-Factor</span><span className="text-white font-black">×{priority.zoneRisk}</span>
                </div>
                <div className="flex justify-between items-center border-b border-white/5 pb-2">
                  <span className="text-white/40">Temporal</span><span className="text-white font-black">×{priority.timeWeight}</span>
                </div>
                <div className="flex justify-between items-center border-b border-white/5 pb-2">
                  <span className="text-white/40">Recency</span><span className="text-white font-black">×{priority.recencyBoost}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Action Panel */}
        <div className="col-span-12 xl:col-span-4 flex flex-col gap-4">
          <div className="flex-1 rounded-3xl bg-white p-8 flex flex-col items-center justify-center text-center shadow-[0_20px_60px_rgba(255,255,255,0.05)]">
            <span className="text-[11px] font-black tracking-[0.2em] text-black/40 uppercase mb-4">Calculated Recommendation</span>
            <div className="text-4xl font-black text-black tracking-tighter italic mb-2 uppercase">{actionLabel}</div>
            <div className="px-3 py-1.5 bg-black text-white rounded-lg text-[13px] font-black tracking-widest font-mono">
              SCORE: {incident.priorityScore.toFixed(2)}
            </div>
            
            <div className="mt-10 w-full space-y-3">
              {['auto', 'dispatched', 'in_progress', 'en_route'].includes(incident.status) ? (
                <button
                  onClick={() => onReject?.(incident.id)}
                  className="w-full bg-red-600 hover:bg-red-700 text-white font-black py-6 rounded-2xl text-[12px] tracking-[0.3em] uppercase transition-all active:scale-[0.98] shadow-[0_10px_30px_rgba(220,38,38,0.3)] flex items-center justify-center gap-3 animate-in fade-in zoom-in-95 duration-500"
                >
                  <X size={20} className="animate-pulse" /> Recall Unit
                </button>
              ) : (
                <>
                  <button
                    onClick={() => onApprove?.(incident.id)}
                    className="w-full bg-black hover:bg-black/80 text-white font-black py-5 rounded-2xl text-[11px] tracking-[0.2em] uppercase transition-all active:scale-[0.98] shadow-xl flex items-center justify-center gap-3"
                  >
                    <Check size={18} /> Authorize Unit
                  </button>
                  <button
                    onClick={() => onReject?.(incident.id)}
                    className="w-full bg-transparent hover:bg-red-50 text-red-600 border border-red-100 font-bold py-5 rounded-2xl text-[11px] tracking-[0.2em] uppercase transition-all active:scale-[0.98] flex items-center justify-center gap-3"
                  >
                    <X size={18} /> Reject Detection
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
