import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { InvestigateView } from './components/InvestigateView';

export function App() {
  return (
    <div className="min-h-screen bg-[#f6f4ef] text-slate-900 flex flex-col font-sans">
      <header className="border-b border-[#ddd6c6] bg-[#fffefb] px-6 py-3 shadow-2xs">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-[#a94e2c]" />
            <span className="font-serif font-bold text-slate-900 text-lg tracking-tight">ANVESHAK</span>
            <span className="text-xs text-slate-500 font-medium">| Case 24/2026 Intelligence</span>
          </div>
          <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#e1ecdf] text-[#2d5c3f]">
            System Operational
          </span>
        </div>
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full p-4 sm:p-6">
        <Routes>
          <Route path="*" element={<InvestigateView />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;