import { useState, useMemo } from 'react';
import { Incident } from '@/lib/types';
import { DISPATCH_ZONES, calculatePriority, getIncidentLabel } from '@/lib/simulation';
import { BrainCircuit, Check, X, Video } from 'lucide-react';

export interface DecisionPanelProps {
  incident: Incident | null;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
}

const ROAD_ACCIDENT_CLIPS = ['Clip1.mp4', 'Clip3.mp4', 'Clip4.mp4', 'Clip5.mp4'];

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

  const videoSrc = useMemo(() => {
    if (incident.type === 'road_accident') {
      const idNum = parseInt(incident.id.replace(/[^0-9]/g, '')) || 0;
      const clip = ROAD_ACCIDENT_CLIPS[idNum % ROAD_ACCIDENT_CLIPS.length];
      return `/videos/${clip}`;
    }
    if (incident.type === 'fire') {
      return '/videos/FIRE.mp4';
    }
    return null;
  }, [incident.type, incident.id]);

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
    <div className="h-full flex flex-col p-8 font-sans overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6 shrink-0">
        <div className="p-2.5 rounded-xl bg-white/5 border border-white/10">
          <BrainCircuit size={20} className="text-white/80" />
        </div>
        <div className="flex flex-col">
          <h3 className="text-sm font-black tracking-[0.3em] text-white uppercase italic">Aegis Decision Engine</h3>
          <span className="text-[10px] text-white/20 font-mono tracking-widest uppercase">Mission Intelligence Layer v4.0</span>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="grid grid-cols-12 gap-6 flex-1 min-h-0">
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6 min-h-0">
          {/* Top Row: Video + Basic Info */}
          <div className="flex gap-6 h-[45%] min-h-0 shrink-0">
            <div className="flex-1 rounded-[2rem] bg-white/5 border border-white/10 overflow-hidden relative group">
              {videoSrc ? (
                <video 
                  src={videoSrc}
                  autoPlay 
                  loop 
                  muted 
                  playsInline
                  className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity duration-700"
                />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center gap-4 text-white/10 italic">
                  <Video size={40} />
                  <span className="text-[10px] uppercase font-mono tracking-widest">No CCTV Feed Available</span>
                </div>
              )}
              <div className="absolute top-4 left-4 flex gap-2">
                <span className="px-2 py-1 bg-red-600 text-white text-[8px] font-black uppercase rounded animate-pulse shadow-xl">LIVE CCTV</span>
                <span className="px-2 py-1 bg-black/40 text-white/60 text-[8px] font-mono uppercase rounded backdrop-blur-md">#{incident.id.slice(0, 4)}</span>
              </div>
              <div className="absolute inset-0 pointer-events-none opacity-10 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%]" />
            </div>

            <div className="w-72 p-6 rounded-[2rem] bg-white/5 border border-white/10 flex flex-col justify-center gap-1.5 shrink-0">
              <span className="text-[9px] font-bold text-white/30 tracking-[0.2em] uppercase">Target Class</span>
              <h2 className="text-2xl font-black text-white italic tracking-tight leading-tight">{getIncidentLabel(incident.type as any)}</h2>
              <div className="space-y-4 mt-6 font-mono text-[9px] uppercase tracking-widest text-white/40">
                <div className="flex flex-col gap-1">
                  <span>Source Signal</span>
                  <span className="text-white font-bold">{incident.cameraSource || 'CAM-MASTER'}</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span>Sovereign Zone</span>
                  <span className="text-white font-bold">{zone?.name || 'CENTRAL'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Row: Metrics & Matrix */}
          <div className="grid grid-cols-2 gap-6 flex-1 min-h-0">
            <div className="p-8 rounded-[2.5rem] bg-white/5 border border-white/10 flex flex-col gap-6 justify-center">
              <ConfBar label="CNN Confidence" value={incident.detectionConfidence} />
              <ConfBar label="Sector Stability" value={zone?.reliability || 0.8} />
              <ConfBar label="Decision Weight" value={incident.decisionConfidence} />
            </div>

            <div className="p-8 rounded-[2.5rem] bg-white/5 border border-white/10 flex flex-col justify-center">
              <div className="text-[10px] font-black text-white/30 tracking-[0.3em] uppercase mb-6">Neural Matrix Breakdown</div>
              <div className="grid grid-cols-2 gap-x-10 gap-y-5 font-mono text-[10px]">
                <div className="flex justify-between items-center border-b border-white/5 pb-3">
                  <span className="text-white/40 italic">Severity</span><span className="text-white font-black">{priority.severity}</span>
                </div>
                <div className="flex justify-between items-center border-b border-white/5 pb-3">
                  <span className="text-white/40 italic">Z-Factor</span><span className="text-white font-black">×{priority.zoneRisk}</span>
                </div>
                <div className="flex justify-between items-center border-b border-white/5 pb-3">
                  <span className="text-white/40 italic">Temporal</span><span className="text-white font-black">×{priority.timeWeight}</span>
                </div>
                <div className="flex justify-between items-center border-b border-white/5 pb-3">
                  <span className="text-white/40 italic">Recency</span><span className="text-white font-black">×{priority.recencyBoost}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Action Panel */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-4">
          <div className="flex-1 rounded-[3rem] bg-white p-10 flex flex-col items-center justify-center text-center shadow-[0_40px_100px_rgba(255,255,255,0.05)]">
            <span className="text-[10px] font-black tracking-[0.3em] text-black/30 uppercase mb-6">Engine Recommendation</span>
            <div className="text-4xl font-black text-black tracking-tighter italic mb-4 uppercase leading-none">{actionLabel}</div>
            <div className="px-5 py-2.5 bg-black text-white rounded-xl text-[14px] font-black tracking-widest font-mono shadow-2xl">
              SCORE: {incident.priorityScore.toFixed(2)}
            </div>
            
            <div className="mt-12 w-full space-y-4">
              {['auto', 'dispatched', 'in_progress', 'en_route'].includes(incident.status) ? (
                <button
                  onClick={() => onReject?.(incident.id)}
                  className="w-full bg-red-600 hover:bg-red-700 text-white font-black py-7 rounded-[1.5rem] text-[12px] tracking-[0.3em] uppercase transition-all active:scale-[0.98] shadow-[0_20px_50px_rgba(220,38,38,0.3)] flex items-center justify-center gap-3"
                >
                  <X size={20} className="animate-pulse" /> Recall Unit
                </button>
              ) : (
                <>
                  <button
                    onClick={() => onApprove?.(incident.id)}
                    className="w-full bg-black hover:bg-black/90 text-white font-black py-6 rounded-[1.5rem] text-[11px] tracking-[0.2em] uppercase transition-all active:scale-[0.98] shadow-2xl flex items-center justify-center gap-3"
                  >
                    <Check size={20} /> Authorize Deployment
                  </button>
                  <button
                    onClick={() => onReject?.(incident.id)}
                    className="w-full bg-transparent hover:bg-red-50 text-red-600 border-2 border-red-100 font-black py-6 rounded-[1.5rem] text-[11px] tracking-[0.2em] uppercase transition-all active:scale-[0.98] flex items-center justify-center gap-3"
                  >
                    <X size={20} /> Reject Target
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

