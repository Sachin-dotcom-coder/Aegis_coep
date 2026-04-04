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
        className="fixed inset-0 z-50 flex items-center justify-center bg-background/85"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="glass-panel p-6 w-96 border border-border"
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <ShieldAlert size={18} className="text-foreground/70" />
            <h2 className="text-sm font-semibold tracking-wider text-foreground uppercase" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Confirmation Required
            </h2>
          </div>

          <div className="p-3 rounded-md bg-secondary/40 border border-border/30 mb-4">
            <div className="text-xs font-medium text-foreground mb-1">{getIncidentLabel(incident.type)}</div>
            <div className="text-[10px] text-muted-foreground font-mono space-y-0.5">
              <div>Camera: {incident.cameraSource}</div>
              <div>Detection: {(incident.detectionConfidence * 100).toFixed(0)}%</div>
              <div>Decision: {(incident.decisionConfidence * 100).toFixed(0)}%</div>
              <div>Priority: {incident.priorityScore.toFixed(2)}</div>
            </div>
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
              <span>Auto-deploy in</span>
              <span className="text-foreground">{countdown}s</span>
            </div>
            <div className="h-1 rounded-full bg-muted overflow-hidden">
              <motion.div
                className="h-full bg-foreground/50 rounded-full"
                initial={{ width: '100%' }}
                animate={{ width: '0%' }}
                transition={{ duration: 5, ease: 'linear' }}
              />
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => onConfirm(incident.id)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md bg-foreground text-background text-xs font-semibold tracking-wider hover:bg-foreground/90 transition-colors"
            >
              <Check size={14} /> CONFIRM
            </button>
            <button
              onClick={() => onReject(incident.id)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md bg-secondary text-foreground/70 border border-border text-xs font-semibold tracking-wider hover:bg-secondary/80 transition-colors"
            >
              <X size={14} /> REJECT
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
