import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Incident } from '@/lib/types';
import { getIncidentLabel } from '@/lib/simulation';
import { ShieldAlert, Check, X } from 'lucide-react';

interface Props {
  incident: Incident;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}

export function ConfirmationModal({ incident, onConfirm, onReject }: Props) {
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    if (countdown <= 0) {
      onConfirm(incident.id);
      return;
    }
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown, incident.id, onConfirm]);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[30001] flex items-center justify-center bg-black/95 backdrop-blur-md"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="glass-panel p-10 w-[480px] border-2 border-white/20 bg-black shadow-[0_0_100px_rgba(0,0,0,0.8)]"
          initial={{ scale: 0.9, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.9, opacity: 0, y: 20 }}
        >
          <div className="flex flex-col items-center gap-6 mb-8 text-center">
            <div className="p-4 rounded-full bg-white/10 ring-8 ring-white/5 animate-pulse">
              <ShieldAlert size={48} className="text-white" />
            </div>
            <div className="space-y-1">
              <h2 className="text-2xl font-black tracking-[0.2em] text-white uppercase font-sans">
                Human Confirmation Required
              </h2>
              <p className="text-[10px] text-white/40 font-mono tracking-widest uppercase">Action Pending: Strategic Deployment</p>
            </div>
          </div>

          <div className="p-6 rounded-xl bg-white/5 border border-white/10 mb-8 space-y-4">
            <div className="text-2xl font-bold text-white text-center tracking-tight truncate border-b border-white/10 pb-4">
              {getIncidentLabel(incident.type)}
            </div>
            <div className="grid grid-cols-2 gap-4 text-xs font-mono tracking-widest uppercase text-white/60">
              <div className="space-y-1"><span className="opacity-40">Source:</span> <div className="text-white">{incident.cameraSource}</div></div>
              <div className="space-y-1"><span className="opacity-40">Confidence:</span> <div className="text-white">{(incident.detectionConfidence * 100).toFixed(0)}%</div></div>
              <div className="space-y-1"><span className="opacity-40">Decision:</span> <div className="text-white">{(incident.decisionConfidence * 100).toFixed(0)}%</div></div>
              <div className="space-y-1"><span className="opacity-40">Incidend ID:</span> <div className="text-white">#{incident.id.slice(0, 8)}</div></div>
            </div>
            <div className="pt-2 text-center">
              <div className="text-[10px] font-bold text-white/40 mb-1 uppercase tracking-widest">Calculated Priority Score</div>
              <div className="text-3xl font-black text-white">{incident.priorityScore.toFixed(2)}</div>
            </div>
          </div>

          <div className="mb-8 p-4 bg-white/5 rounded-lg">
            <div className="flex justify-between text-xs font-mono text-white/60 mb-3 tracking-widest">
              <span>AUTO-DEPLOYMENT SEQUENCE ACTIVE</span>
              <span className="text-white font-bold">{countdown}S</span>
            </div>
            <div className="h-2 rounded-full bg-white/10 overflow-hidden">
              <motion.div
                className="h-full bg-white rounded-full"
                initial={{ width: '100%' }}
                animate={{ width: '0%' }}
                transition={{ duration: 5, ease: 'linear' }}
              />
            </div>
          </div>

          <div className="flex gap-4">
            <button
              onClick={() => onConfirm(incident.id)}
              className="flex-1 flex items-center justify-center gap-3 py-5 px-6 rounded-xl bg-white text-black text-sm font-black tracking-[0.2em] hover:bg-white/90 transition-all active:scale-95 shadow-[0_0_30px_rgba(255,255,255,0.2)]"
            >
              <Check size={20} /> DEPLOY
            </button>
            <button
              onClick={() => onReject(incident.id)}
              className="flex-1 flex items-center justify-center gap-3 py-5 px-6 rounded-xl bg-black text-white border-2 border-white/10 text-sm font-black tracking-[0.2em] hover:bg-white/5 transition-all active:scale-95"
            >
              <X size={20} /> ABORT
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
