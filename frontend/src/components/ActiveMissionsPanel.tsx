import React from 'react';
import { Drone } from '@/lib/types';
import { Activity, Radio, MapPin, Navigation, Video } from 'lucide-react';

interface Props {
  drones: Drone[];
  onOpenFeed: (droneId: string) => void;
}

export const ActiveMissionsPanel = ({ drones, onOpenFeed }: Props) => {
  const activeDrones = drones.filter(d => d.status !== 'idle');
  
  return (
    <div className="flex-1 flex flex-col bg-black/40 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
      <div className="p-4 border-b border-white/5 bg-white/5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity size={16} className="text-white/60 animate-pulse" />
          <span className="text-[11px] font-black tracking-[0.3em] uppercase italic">Active Operations Ledger</span>
        </div>
        <span className="text-[10px] font-mono text-white/20 uppercase tracking-[0.2em]">{activeDrones.length} Units Active</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
        {activeDrones.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center opacity-20 py-8">
            <Radio size={24} className="mb-2" />
            <span className="text-[10px] font-mono uppercase tracking-[0.2em]">All Units Stationed</span>
          </div>
        ) : (
          activeDrones.map(drone => (
            <div key={drone.id} className="group bg-white/5 hover:bg-white/10 border border-white/5 rounded-xl p-3 transition-all duration-300">
              <div className="flex items-center justify-between mb-3">
                <div className="flex flex-col">
                  <span className="text-[11px] font-bold text-white tracking-widest uppercase">Unit {drone.id.replace('drone_', 'D-')}</span>
                  <div className="flex items-center gap-2 mt-1">
                     {drone.status === 'on_site' ? (
                       <span className="flex items-center gap-1.5 px-2 py-0.5 bg-red-600/20 text-red-500 rounded-md text-[9px] font-black uppercase tracking-widest animate-pulse">
                         <MapPin size={10} /> ON STATION
                       </span>
                     ) : (
                       <span className="flex items-center gap-1.5 px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded-md text-[9px] font-black uppercase tracking-widest">
                         <Navigation size={10} className={drone.status === 'en_route' ? 'animate-bounce' : ''} /> {drone.status.replace('_', ' ')}
                       </span>
                     )}
                  </div>
                </div>

                {drone.status === 'on_site' && (
                  <button 
                    onClick={() => onOpenFeed(drone.id)}
                    className="flex items-center gap-2 bg-red-600 hover:bg-white text-white hover:text-black px-4 py-2 rounded-lg transition-all shadow-lg shadow-red-900/20 active:scale-95 group"
                  >
                    <Video size={14} className="group-hover:animate-spin" />
                    <span className="text-[10px] font-black uppercase tracking-widest">STREAM</span>
                  </button>
                )}
              </div>

              {/* Progress visualizer */}
              <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                <div 
                  className={`h-full transition-all duration-1000 ${drone.status === 'on_site' ? 'w-full bg-red-600' : 'w-2/3 bg-blue-600 animate-pulse'}`} 
                />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
