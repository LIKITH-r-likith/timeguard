import React from 'react';
import { ShieldCheck, Info } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="bg-slate-900 border-t border-slate-800 text-slate-400 py-6 px-6 text-xs mt-auto">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span className="font-semibold text-slate-200">TimeGuard Console</span>
          <span className="text-slate-500">|</span>
          <span>Dayforce AI Innovation Challenge (Use Case 5: Time &amp; Attendance)</span>
        </div>

        <div className="flex items-center gap-2 text-slate-300 bg-slate-800/80 px-3 py-1.5 rounded border border-slate-700">
          <Info className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span>
            <strong>Disclaimer:</strong> All policy rules, pay rates, and cost estimates are mock data for demonstration. Not legal advice.
          </span>
        </div>
      </div>
    </footer>
  );
};
