import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Incident } from '@/lib/types';
import { getIncidentLabel } from '@/lib/simulation';
import { ShieldAlert, Check, X, Video } from 'lucide-react';

interface Props {
  incident: Incident;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}

const ROAD_ACCIDENT_CLIPS = ['Clip1.mp4', 'Clip3.mp4', 'Clip4.mp4', 'Clip5.mp4'];

export function ConfirmationModal({ incident, onConfirm, onReject }: Props) {
  const [countdown, setCountdown] = useState(5);
  const isSilent = incident.status === 'silent';

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

  useEffect(() => {
    if (countdown <= 0) {
      if (isSilent) onReject(incident.id);
      else onConfirm(incident.id);
      return;
    }
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown, incident.id, onConfirm, onReject, isSilent]);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[30001] flex items-center justify-center bg-black/95 backdrop-blur-md px-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="glass-panel w-full max-w-[1000px] border-2 border-white/20 bg-black shadow-[0_0_100px_rgba(0,0,0,0.8)] overflow-hidden rounded-[2.5rem] flex flex-col md:flex-row"
          initial={{ scale: 0.9, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.9, opacity: 0, y: 20 }}
        >
          {/* Left Side: CCTV Miniplayer */}
          <div className="flex-1 min-h-[300px] md:min-h-0 bg-white/5 relative group">
            <div className="absolute top-6 left-6 z-10 flex items-center gap-3">
              <div className="px-3 py-1.5 bg-red-600/90 text-white text-[10px] font-black tracking-[0.2em] uppercase rounded-lg flex items-center gap-2 shadow-2xl backdrop-blur-md">
                <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                Live CCTV Feed
              </div>
              <div className="px-3 py-1.5 bg-black/60 text-white/80 text-[10px] font-mono tracking-widest uppercase rounded-lg backdrop-blur-md border border-white/10">
                Cam-{incident.id.slice(0, 4).toUpperCase()}
              </div>
            </div>
            
            {videoSrc ? (
              <video 
                src={videoSrc}
                autoPlay 
                loop 
                muted 
                playsInline
                className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-700"
              />
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center gap-4 text-white/20 bg-white/2">
                <Video size={48} />
                <span className="text-[10px] font-mono tracking-[0.3em] uppercase italic">Signal Lost / No Feed</span>
              </div>
            )}
            
            {/* Scanline Effect Overlay */}
            <div className="absolute inset-0 pointer-events-none opacity-20 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%]" />
          </div>

          {/* Right Side: Decision & Stats */}
          <div className="w-full md:w-[450px] p-10 flex flex-col border-l border-white/10 bg-black/40">
            <div className="flex flex-col items-center gap-6 mb-8 text-center">
              <div className={`p-4 rounded-full ring-8 animate-pulse ${isSilent ? 'bg-amber-500/10 ring-amber-500/10' : 'bg-white/10 ring-white/5'}`}>
                <ShieldAlert size={40} className={isSilent ? 'text-amber-400' : 'text-white'} />
              </div>
              <div className="space-y-1">
                <h2 className="text-xl font-black tracking-[0.2em] text-white uppercase font-sans">
                  {isSilent ? 'Low Confidence — Review' : 'Confirmation Required'}
                </h2>
                <p className="text-[9px] text-white/40 font-mono tracking-widest uppercase italic">
                  Operator Judgment Needed for Unit Authorization
                </p>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 mb-8 space-y-4">
              <div className="text-2xl font-black text-white text-center tracking-tight truncate border-b border-white/10 pb-4 italic">
                {getIncidentLabel(incident.type)}
              </div>
              <div className="grid grid-cols-2 gap-4 text-[10px] font-mono tracking-widest uppercase text-white/60">
                <div className="space-y-1"><span className="opacity-40">Source:</span> <div className="text-white truncate">{incident.cameraSource}</div></div>
                <div className="space-y-1"><span className="opacity-40">Confidence:</span> <div className={isSilent ? 'text-amber-400 font-black' : 'text-white'}>{(incident.detectionConfidence * 100).toFixed(0)}%</div></div>
                <div className="space-y-1"><span className="opacity-40">Decision:</span> <div className="text-white">{(incident.decisionConfidence * 100).toFixed(0)}%</div></div>
                <div className="space-y-1"><span className="opacity-40">Incident ID:</span> <div className="text-white">#{incident.id.slice(0, 8)}</div></div>
              </div>
              <div className="pt-2 text-center">
                <div className="text-[9px] font-bold text-white/30 mb-1 uppercase tracking-widest">Priority Score</div>
                <div className="text-3xl font-black text-white">{incident.priorityScore.toFixed(2)}</div>
              </div>
            </div>

            <div className="mb-8 p-4 bg-white/5 rounded-xl border border-white/5">
              <div className="flex justify-between text-[10px] font-mono text-white/60 mb-3 tracking-widest uppercase font-bold">
                <span>{isSilent ? 'AUTO-DISMISS IN' : 'DEPLOYMENT SEQUENCE'}</span>
                <span className={`font-black ${isSilent ? 'text-amber-400' : 'text-white'}`}>{countdown}S</span>
              </div>
              <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${isSilent ? 'bg-amber-400' : 'bg-white'}`}
                  initial={{ width: '100%' }}
                  animate={{ width: '0%' }}
                  transition={{ duration: 5, ease: 'linear' }}
                />
              </div>
            </div>

            <div className="flex gap-4 mt-auto">
              <button
                onClick={() => onConfirm(incident.id)}
                className="flex-1 flex items-center justify-center gap-3 py-5 px-6 rounded-2xl bg-white text-black text-[11px] font-black tracking-[0.2em] hover:bg-white/90 transition-all active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.15)] uppercase"
              >
                <Check size={18} /> DEPLOY
              </button>
              <button
                onClick={() => onReject(incident.id)}
                className="flex-1 flex items-center justify-center gap-3 py-5 px-6 rounded-2xl bg-black text-white border-2 border-white/10 text-[11px] font-black tracking-[0.2em] hover:bg-white/5 transition-all active:scale-95 uppercase"
              >
                <X size={18} /> ABORT
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

