import React, { useState, useEffect } from 'react';
import { Search, Target, X, Scan } from 'lucide-react';

interface Props {
  onManualDispatch: (lat: number, lng: number) => void;
}

const PUNE_CENTER: [number, number] = [18.5204, 73.8567];

export const ManualCommandPanel = ({ onManualDispatch }: Props) => {
  const [showConsole, setShowConsole] = useState(false);
  const [manualAddress, setManualAddress] = useState('');
  const [suggestions, setSuggestions] = useState<{ display_name: string; lat: string; lon: string }[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lng: number } | null>(null);

  // Live Geocoding Search
  useEffect(() => {
    const delay = setTimeout(async () => {
      if (manualAddress.length > 3 && !selectedCoords) {
        setSearching(true);
        try {
          const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(manualAddress)}+Pune&limit=5`);
          const data = await res.json();
          setSuggestions(data);
        } catch (err) {
          console.error("Geocoding failed", err);
        } finally {
          setSearching(false);
        }
      } else {
        setSuggestions([]);
      }
    }, 500);
    return () => clearTimeout(delay);
  }, [manualAddress, selectedCoords]);

  return (
    <div className="mb-2 w-full">
      <button
        onClick={() => setShowConsole(!showConsole)}
        className="w-full flex items-center justify-between bg-black/60 hover:bg-white hover:text-black backdrop-blur-xl border border-white/10 px-6 py-4 rounded-2xl shadow-xl transition-all group active:scale-[0.98]"
      >
        <div className="flex items-center gap-4">
          <Target size={20} className={showConsole ? '' : 'group-hover:animate-spin'} />
          <span className="text-[11px] font-black tracking-[0.3em] uppercase italic">Manual Dispatch</span>
        </div>
        <div className={`w-2 h-2 rounded-full ${showConsole ? 'bg-red-500 animate-pulse shadow-[0_0_8px_#ef4444]' : 'bg-white/20'}`} />
      </button>

      {showConsole && (
        <div className="mt-2 flex flex-col gap-4 bg-black/95 backdrop-blur-3xl border border-white/10 p-5 rounded-2xl shadow-2xl animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="flex items-center justify-between">
            <span className="text-[9px] font-mono text-white/30 uppercase tracking-[0.3em]">Dispatch Location</span>
            <button onClick={() => setShowConsole(false)} className="text-white/20 hover:text-white"><X size={14} /></button>
          </div>

          <div className="relative">
            <Search className={`absolute left-4 top-1/2 -translate-y-1/2 ${searching ? 'text-white animate-spin' : 'text-white/40'}`} size={16} />
            <input
              type="text"
              placeholder="Location: Kothrud, Pune..."
              value={manualAddress}
              onChange={(e) => {
                setManualAddress(e.target.value);
                setSelectedCoords(null);
              }}
              className="w-full bg-white/5 border border-white/10 rounded-xl py-3 pl-12 pr-6 text-white font-mono text-xs focus:border-white/30 transition-all outline-none"
            />

            {suggestions.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-black/95 border border-white/20 rounded-xl overflow-hidden shadow-2xl z-[1002]">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setManualAddress(s.display_name);
                      setSelectedCoords({ lat: parseFloat(s.lat), lng: parseFloat(s.lon) });
                      setSuggestions([]);
                    }}
                    className="w-full text-left px-5 py-3 hover:bg-white hover:text-black transition-all border-b border-white/5 last:border-0"
                  >
                    <span className="text-[10px] font-bold tracking-widest uppercase truncate block">{s.display_name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => {
              const finalCoords = selectedCoords || { lat: PUNE_CENTER[0], lng: PUNE_CENTER[1] };
              onManualDispatch(finalCoords.lat, finalCoords.lng);
              setShowConsole(false);
              setManualAddress('');
              setSelectedCoords(null);
            }}
            disabled={!manualAddress}
            className="w-full bg-white text-black py-3.5 rounded-xl flex items-center justify-center gap-3 hover:bg-gray-200 active:scale-95 transition-all disabled:opacity-10"
          >
            <Scan size={18} />
            <span className="text-[10px] font-black tracking-[0.3em] uppercase">Send Drone</span>
          </button>
        </div>
      )}
    </div>
  );
};
