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
          <span className="text-[13px] font-black tracking-[0.3em] uppercase italic">Active Unit Status</span>
        </div>
        <span className="text-[13px] font-mono text-white/20 uppercase tracking-[0.2em]">{activeDrones.length} Units Active</span>
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
                      <span className="flex items-center gap-1.5 px-2 py-0.5 bg-red-600/20 text-red-500 rounded-md text-[12px] font-black uppercase tracking-widest animate-pulse">
                        <MapPin size={10} /> ON STATION
                      </span>
                    ) : drone.status === 'charging' ? (
                      <span className="flex items-center gap-1.5 px-2 py-0.5 bg-green-600/20 text-green-500 rounded-md text-[12px] font-black uppercase tracking-widest">
                        <Activity size={10} className="animate-pulse" /> CHARGING
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded-md text-[12px] font-black uppercase tracking-widest">
                        <Navigation size={10} className={(drone.status === 'en_route' || drone.status === 'recalled') ? 'animate-bounce' : ''} /> {drone.status.replace('_', ' ')}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-end">
                  {(drone.status === 'en_route' || drone.status === 'recalled') && drone.eta_seconds !== undefined && (
                    <span className="text-[13px] font-mono text-blue-400 font-bold mb-1">
                      ETA: {Math.floor(drone.eta_seconds / 60)}m {drone.eta_seconds % 60}s
                    </span>
                  )}
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
              </div>

              {/* Progress visualizer */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono text-white/30 uppercase tracking-tighter">
                  <span>{drone.status === 'charging' ? 'Charge level' : 'Mission Progress'}</span>
                  <span>{Math.round(drone.status === 'charging' ? (drone.charging_progress || 0) : (drone.path_progress || 0))}%</span>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-1000 ${drone.status === 'on_site' ? 'w-full bg-red-600 shadow-[0_0_8px_rgba(239,68,68,0.5)]' :
                        drone.status === 'charging' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' :
                          'bg-blue-600 shadow-[0_0_8px_rgba(37,99,235,0.5)]'
                      }`}
                    style={{ width: `${drone.status === 'on_site' ? 100 : (drone.status === 'charging' ? (drone.charging_progress || 0) : (drone.path_progress || 0))}%` }}
                  />
                </div>              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
