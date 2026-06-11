const fs = require('fs');

// --- 1. PATCH INDEX.CSS ---
let css = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/index.css', 'utf-8');
const rules = `
.dashboard-light {
  background: #f8fafc;
  color: #020617;
}

.dashboard-light .dashboard-card,
.dashboard-light .card,
.dashboard-light .widget-card,
.dashboard-light .glass-panel,
.dashboard-light .premium-card {
  background: #ffffff !important;
  color: #020617 !important;
  border: 1px solid #e5e7eb !important;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06) !important;
}

.dashboard-light input,
.dashboard-light textarea,
.dashboard-light select {
  background: transparent;
  color: #020617;
}

.dashboard-light input::placeholder,
.dashboard-light textarea::placeholder {
  color: #94a3b8;
}

.dashboard-light .light-row,
.dashboard-light .metric-box,
.dashboard-light .activity-row,
.dashboard-light .news-row,
.dashboard-light .market-row,
.dashboard-light .technical-box {
  background: #f8fafc !important;
  color: #020617 !important;
  border: 1px solid #e5e7eb !important;
}

.dashboard-light .muted-text {
  color: #64748b !important;
}
`;
if (!css.includes('.dashboard-light {')) {
  fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/index.css', css + rules);
  console.log('index.css updated.');
} else {
  console.log('index.css already contains rules.');
}

// --- 2. PATCH APP.JSX ---
let code = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', 'utf-8');

// 2.a Add dashboard-light to Dashboard wrapper
code = code.replace(
  /className="dashboard-shell relative h-screen w-screen overflow-hidden text-\[\#020617\] bg-\[\#f8fafc\]"/, 
  'className="dashboard-shell dashboard-light relative h-screen w-screen overflow-hidden text-[#020617] bg-[#f8fafc]"'
);

// We want to skip Auth and Landing sections from global replacements.
// Let's assume Landing and Auth are before line 1600.
const lines = code.split('\n');
const dashboardStart = lines.findIndex(l => l.includes('function CandlestickIcon'));

for (let i = dashboardStart; i < lines.length; i++) {
  let l = lines[i];

  // Search input
  if (l.includes('placeholder="Search NSE...')) {
    l = l.replace(/bg-black/, 'bg-[#ffffff]');
    l = l.replace(/bg-\[\#09090B\]/, 'bg-[#ffffff]');
    l = l.replace(/border-white\/10/, 'border-[#e5e7eb]');
    l = l.replace(/text-white/, 'text-[#020617]');
    l = l.replace(/placeholder:text-white\/30/, 'placeholder:text-[#94a3b8]');
  }

  // Cards
  l = l.replace(/bg-\[\#09090B\] border border-white\/10/g, 'bg-[#ffffff] border border-[#e5e7eb] shadow-sm text-[#020617]');
  l = l.replace(/bg-black border border-white\/10/g, 'bg-[#f8fafc] border border-[#e5e7eb] rounded-xl text-[#020617]');
  l = l.replace(/bg-\[\#050505\] border border-white\/10/g, 'bg-[#f8fafc] border border-[#e5e7eb] text-[#020617]');
  
  // Hardcoded dark backgrounds inside cards
  l = l.replace(/bg-black/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-\[\#09090B\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#050505\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-\[\#111111\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-\[\#18181b\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-\[\#1f1f1f\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-\[\#262626\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-\[\#333333\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-gray-900/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-neutral-950/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-zinc-950/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-white\/\[0\.02\]/g, 'bg-[#f8fafc]');
  l = l.replace(/bg-white\/5/g, 'bg-[#f1f5f9]');
  l = l.replace(/bg-white\/10/g, 'bg-[#e5e7eb]');

  // Borders
  l = l.replace(/border-black/g, 'border-[#e5e7eb]');
  l = l.replace(/border-\[\#000000\]/g, 'border-[#e5e7eb]');
  l = l.replace(/border-gray-900/g, 'border-[#e5e7eb]');
  l = l.replace(/border-neutral-950/g, 'border-[#e5e7eb]');
  l = l.replace(/border-zinc-950/g, 'border-[#e5e7eb]');
  l = l.replace(/border-white\/10/g, 'border-[#e5e7eb]');
  l = l.replace(/border-white\/20/g, 'border-[#d1d5db]');

  // Pills / Button overrides
  // Active blue pill
  l = l.replace(/text-blue-400 bg-blue-500\/10/g, 'bg-[#eff6ff] text-[#2563eb] border border-[#bfdbfe]');
  // Green pill
  l = l.replace(/text-emerald-400 bg-emerald-500\/10/g, 'bg-[#ecfdf5] text-[#059669] border border-[#bbf7d0]');
  // Red pill
  l = l.replace(/text-rose-400 bg-rose-500\/10/g, 'bg-[#fef2f2] text-[#dc2626] border border-[#fecaca]');
  l = l.replace(/text-red-400 bg-red-500\/10/g, 'bg-[#fef2f2] text-[#dc2626] border border-[#fecaca]');
  // Neutral pill
  l = l.replace(/text-gray-400 bg-gray-500\/10/g, 'bg-[#f1f5f9] text-[#475569] border border-[#e2e8f0]');

  // Text
  l = l.replace(/text-white\/40/g, 'text-[#64748b]');
  l = l.replace(/text-white\/60/g, 'text-[#64748b]');
  l = l.replace(/text-white\/80/g, 'text-[#374151]');
  l = l.replace(/text-white/g, 'text-[#020617]');
  l = l.replace(/text-gray-400/g, 'text-[#64748b]');
  l = l.replace(/text-gray-500/g, 'text-[#64748b]');
  l = l.replace(/text-zinc-400/g, 'text-[#64748b]');
  l = l.replace(/text-zinc-500/g, 'text-[#64748b]');
  l = l.replace(/text-emerald-400/g, 'text-[#059669]');
  l = l.replace(/text-green-400/g, 'text-[#059669]');
  l = l.replace(/text-green-500/g, 'text-[#059669]');
  l = l.replace(/text-red-400/g, 'text-[#dc2626]');
  l = l.replace(/text-red-500/g, 'text-[#dc2626]');
  l = l.replace(/text-rose-400/g, 'text-[#dc2626]');
  l = l.replace(/text-blue-400/g, 'text-[#2563eb]');

  // Top right toggle Backtested / Live
  if (l.includes('Backtested-only mode')) {
    l = l.replace(/bg-\[\#f8fafc\]/, 'bg-[#eff6ff]'); // Because we already replaced bg-[#09090B] with bg-[#ffffff] and bg-black with bg-[#f8fafc]
  }

  lines[i] = l;
}

// 2.b Ticker bar fix - it should remain dark but readable text.
// The ticker is before CandlestickIcon, so we process it separately.
for (let i = 0; i < dashboardStart; i++) {
  if (lines[i].includes('market-ticker') || lines[i].includes('text-gray-300') || lines[i].includes('q.price == null')) {
    lines[i] = lines[i].replace(/text-gray-300/g, 'text-[#ffffff]');
    lines[i] = lines[i].replace(/text-\[\#94a3b8\]/g, 'text-[#9ca3af]');
    lines[i] = lines[i].replace(/text-green-400/g, 'text-[#22c55e]');
    lines[i] = lines[i].replace(/text-red-400/g, 'text-[#ef4444]');
  }
}

fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', lines.join('\n'));
console.log('App.jsx updated.');
