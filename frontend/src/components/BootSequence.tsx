import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const BOOT_STAGES = [
  'Initializing neural detection network...',
  'Loading YOLOv8 model weights...',
  'Calibrating dual-confidence engine...',
  'Connecting to 5 dispatch zones...',
  'Activating 15 drone units...',
  'Syncing camera feeds (32 nodes)...',
  'Running system diagnostics...',
  'Aegis Shield v2.0 — ONLINE',
];

export function BootSequence({ onComplete }: { onComplete: () => void }) {
  const [stage, setStage] = useState(0);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const stageInterval = setInterval(() => {
      setStage(prev => {
        if (prev >= BOOT_STAGES.length - 1) {
          clearInterval(stageInterval);
          setTimeout(onComplete, 1200);
          return prev;
        }
        return prev + 1;
      });
    }, 600);
    return () => clearInterval(stageInterval);
  }, [onComplete]);

  useEffect(() => {
    const progressInterval = setInterval(() => {
      setProgress(prev => Math.min(100, prev + 1.5));
    }, 50);
    return () => clearInterval(progressInterval);
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background">
      {/* Radar sweep */}
      <div className="relative mb-12 h-40 w-40">
        <div className="absolute inset-0 rounded-full border border-foreground/10" />
        <div className="absolute inset-4 rounded-full border border-foreground/15" />
        <div className="absolute inset-8 rounded-full border border-foreground/20" />
        <div className="absolute inset-12 rounded-full border border-foreground/25" />
        <div className="absolute inset-0 animate-radar">
          <div className="h-1/2 w-px mx-auto origin-bottom bg-gradient-to-t from-foreground/60 to-transparent" />
        </div>
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="absolute inset-0 rounded-full border border-foreground/15 animate-pulse-ring"
            style={{ animationDelay: `${i * 0.7}s` }}
          />
        ))}
        <div className="absolute inset-1/2 -translate-x-1 -translate-y-1 h-2 w-2 rounded-full bg-foreground" />
      </div>

      <motion.h1
        className="text-2xl font-semibold tracking-[0.3em] text-foreground mb-2"
        style={{ fontFamily: "'Space Grotesk', sans-serif" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
      >
        AEGIS SHIELD
      </motion.h1>
      <p className="text-[10px] text-muted-foreground tracking-[0.2em] mb-10 font-mono">
        AI-POWERED URBAN SAFETY SYSTEM
      </p>

      <div className="w-80 space-y-1 mb-8 font-mono text-xs">
        <AnimatePresence>
          {BOOT_STAGES.slice(0, stage + 1).map((text, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className={`flex items-center gap-2 ${i === stage ? 'text-foreground' : 'text-muted-foreground'}`}
            >
              <span className={i < stage ? 'text-foreground/60' : 'text-foreground'}>
                {i < stage ? '✓' : i === stage ? '›' : ' '}
              </span>
              {text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="w-80 h-px rounded-full bg-muted overflow-hidden">
        <motion.div
          className="h-full bg-foreground/50 rounded-full"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-[10px] text-muted-foreground mt-2 font-mono">{Math.round(progress)}%</p>
    </div>
  );
}
