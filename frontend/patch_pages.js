const fs = require('fs');

// --- 1. PATCH INDEX.CSS ---
let css = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/index.css', 'utf-8');
const safetyRules = `
.dashboard-light {
  background: #f8fafc;
  color: #020617;
}

.dashboard-light input,
.dashboard-light textarea,
.dashboard-light select {
  color: #020617;
}

.dashboard-light input::placeholder,
.dashboard-light textarea::placeholder {
  color: #94a3b8;
}

.dashboard-light .dashboard-card,
.dashboard-light .widget-card,
.dashboard-light .card-shell {
  background: #ffffff;
  color: #020617;
  border: 1px solid #e5e7eb;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
`;
if (!css.includes('.dashboard-light input,')) {
  fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/index.css', css + safetyRules);
  console.log('index.css updated.');
}

// --- 2. PATCH APP.JSX ---
let code = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', 'utf-8');

// We'll replace specifically requested patterns inside the dashboard area (from CandlestickIcon onwards)
const lines = code.split('\n');
const dashboardStart = lines.findIndex(l => l.includes('function CandlestickIcon'));

for (let i = dashboardStart; i < lines.length; i++) {
  let l = lines[i];

  // ============================================
  // GLOBAL FIXES (Backgrounds & Borders)
  // ============================================
  l = l.replace(/bg-black/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#000000\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#050505\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#09090B\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#111111\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#18181b\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#1f1f1f\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#262626\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-\[\#333333\]/g, 'bg-[#ffffff]');
  l = l.replace(/bg-gray-900/g, 'bg-[#ffffff]');
  l = l.replace(/bg-neutral-950/g, 'bg-[#ffffff]');
  l = l.replace(/bg-zinc-950/g, 'bg-[#ffffff]');

  l = l.replace(/border-black/g, 'border-[#e5e7eb]');
  l = l.replace(/border-\[\#000000\]/g, 'border-[#e5e7eb]');
  l = l.replace(/border-gray-900/g, 'border-[#e5e7eb]');
  l = l.replace(/border-neutral-950/g, 'border-[#e5e7eb]');
  l = l.replace(/border-zinc-950/g, 'border-[#e5e7eb]');
  l = l.replace(/border-gray-800/g, 'border-[#e5e7eb]');
  l = l.replace(/border-gray-700/g, 'border-[#e5e7eb]');
  l = l.replace(/border-white\/10/g, 'border-[#e5e7eb]');
  l = l.replace(/border-white\/20/g, 'border-[#d1d5db]');

  // Progress tracks (inactive)
  l = l.replace(/bg-gray-800/g, 'bg-[#e5e7eb]');
  l = l.replace(/bg-gray-700/g, 'bg-[#e5e7eb]');
  // Toggles (on state)
  l = l.replace(/bg-blue-600/g, 'bg-[#2563eb]');
  // Toggles (off state)
  l = l.replace(/bg-gray-200/g, 'bg-[#cbd5e1]');
  l = l.replace(/bg-gray-300/g, 'bg-[#cbd5e1]');

  // ============================================
  // SPECIFIC BUTTONS
  // ============================================
  // Backtested-only
  if (l.includes('Backtested-only mode')) {
    l = l.replace(/className=".*?"/, 'className="flex items-center gap-2 rounded-full border border-[#bfdbfe] bg-[#eff6ff] px-4 py-2 text-[12px] font-medium text-[#2563eb] hover:bg-[#dbeafe] transition-colors"');
  }
  // Add Widget (+)
  if (l.includes('title="Add widget"')) {
    l = l.replace(/className=".*?"/, 'className="grid h-9 w-9 place-items-center rounded-full border border-[#e5e7eb] bg-[#ffffff] text-[#020617] hover:bg-[#f8fafc] transition-colors"');
  }
  // Analyze with AI
  if (l.includes('Analyze with AI')) {
    l = l.replace(/className=".*?"/, 'className="lift-button flex w-full items-center justify-center gap-2 rounded-lg bg-[#2563eb] py-3 text-[14px] font-semibold text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"');
  }
  // Add strategy
  if (l.includes('+ Add strategy')) {
    l = l.replace(/className=".*?"/, 'className="flex items-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2 text-[13px] font-medium text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"');
  }
  // New copy setup
  if (l.includes('+ New copy setup')) {
    l = l.replace(/className=".*?"/, 'className="flex items-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2 text-[13px] font-medium text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"');
  }
  // Log trade
  if (l.includes('+ Log trade')) {
    l = l.replace(/className=".*?"/, 'className="flex items-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2 text-[13px] font-medium text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"');
  }
  // Save Changes
  if (l.includes('>Save Changes<') || l.includes('>Save<')) {
    if (l.includes('disabled')) {
      l = l.replace(/className=".*?"/, 'className="lift-button w-full rounded-xl bg-[#f1f5f9] border border-[#e5e7eb] py-3 text-[14px] font-semibold text-[#94a3b8] cursor-not-allowed"');
    } else {
      l = l.replace(/className=".*?"/, 'className="lift-button w-full rounded-xl bg-[#2563eb] py-3 text-[14px] font-semibold text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"');
    }
  }
  // Update Password
  if (l.includes('>Update Password<')) {
    if (l.includes('disabled')) {
      l = l.replace(/className=".*?"/, 'className="lift-button w-full rounded-xl bg-[#f1f5f9] border border-[#e5e7eb] py-3 text-[14px] font-semibold text-[#94a3b8] cursor-not-allowed"');
    } else {
      l = l.replace(/className=".*?"/, 'className="lift-button w-full rounded-xl bg-[#2563eb] py-3 text-[14px] font-semibold text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"');
    }
  }
  // Sign Out
  if (l.includes('>Sign Out<')) {
    l = l.replace(/className=".*?"/, 'className="lift-button flex w-full items-center justify-center gap-2 rounded-xl border border-[#fecaca] bg-[#ffffff] py-3 text-[14px] font-semibold text-[#dc2626] hover:bg-[#fef2f2] transition-colors"');
  }

  // ============================================
  // SIDEBAR SEARCH INPUT & PASSWORD INPUTS
  // ============================================
  if (l.includes('placeholder="Search stock, sector')) {
    l = l.replace(/className=".*?"/, 'className="h-full w-full bg-[#f8fafc] pl-10 pr-4 text-[13px] font-medium text-[#020617] border border-[#e5e7eb] outline-none placeholder:text-[#94a3b8] rounded-md"');
  }
  if (l.includes('placeholder="Search NSE')) { // The onboarding search
    l = l.replace(/className=".*?"/, 'className="w-full rounded-lg bg-[#ffffff] border border-[#e5e7eb] pl-11 pr-4 py-3 text-[15px] text-[#020617] placeholder:text-[#94a3b8] focus:border-[#2563eb] outline-none"');
  }
  if (l.includes('type="password"')) {
    l = l.replace(/className=".*?"/, 'className="w-full rounded-[12px] border border-[#e5e7eb] bg-[#ffffff] px-4 py-3 text-[14px] text-[#020617] placeholder:text-[#94a3b8] focus:border-[#2563eb] outline-none transition-all"');
  }

  // ============================================
  // PILLS & BADGES
  // ============================================
  // Blue (Active/Phase 1/Intraday/Swing/Scalp)
  l = l.replace(/bg-blue-500\/10/g, 'bg-[#eff6ff]');
  l = l.replace(/bg-blue-50/g, 'bg-[#eff6ff]');
  l = l.replace(/text-blue-400/g, 'text-[#2563eb]');
  l = l.replace(/text-blue-500/g, 'text-[#2563eb]');
  l = l.replace(/text-blue-700/g, 'text-[#2563eb]');
  l = l.replace(/border-blue-500\/20/g, 'border-[#bfdbfe]');
  
  // Green (Live/Testing/Active/Profit)
  l = l.replace(/bg-emerald-500\/10/g, 'bg-[#ecfdf5]');
  l = l.replace(/text-emerald-400/g, 'text-[#059669]');
  l = l.replace(/border-emerald-500\/20/g, 'border-[#bbf7d0]');
  l = l.replace(/text-green-400/g, 'text-[#059669]');
  l = l.replace(/text-green-500/g, 'text-[#059669]');
  
  // Red (Loss)
  l = l.replace(/bg-rose-500\/10/g, 'bg-[#fef2f2]');
  l = l.replace(/bg-red-500\/10/g, 'bg-[#fef2f2]');
  l = l.replace(/text-rose-400/g, 'text-[#dc2626]');
  l = l.replace(/text-red-400/g, 'text-[#dc2626]');
  l = l.replace(/text-red-500/g, 'text-[#dc2626]');
  l = l.replace(/border-rose-500\/20/g, 'border-[#fecaca]');
  l = l.replace(/border-red-500\/20/g, 'border-[#fecaca]');
  
  // Amber (Warning/Paused)
  l = l.replace(/bg-amber-500\/10/g, 'bg-[#fffbeb]');
  l = l.replace(/text-amber-400/g, 'text-[#d97706]');
  l = l.replace(/text-amber-500/g, 'text-[#d97706]');
  l = l.replace(/text-yellow-400/g, 'text-[#d97706]');
  l = l.replace(/text-yellow-500/g, 'text-[#d97706]');
  l = l.replace(/border-amber-500\/20/g, 'border-[#fde68a]');
  
  // Neutral (Observe/Queued/Inactive)
  l = l.replace(/bg-gray-500\/10/g, 'bg-[#f1f5f9]');
  l = l.replace(/bg-gray-800 text-gray-400/g, 'bg-[#f1f5f9] text-[#475569] border border-[#e2e8f0]');
  l = l.replace(/border-gray-500\/20/g, 'border-[#e2e8f0]');

  // Positions page inactive tabs
  if (l.includes('activeTab ===') && l.includes('?')) {
     l = l.replace(/"bg-gray-800 text-gray-300 hover:bg-gray-700"/, '"bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]"');
     l = l.replace(/"bg-\[\#ffffff\] text-\[\#020617\] border border-\[\#e5e7eb\] hover:bg-\[\#f8fafc\]"/, '"bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]"');
     l = l.replace(/"bg-white text-gray-900"/, '"bg-[#2563eb] text-[#ffffff] border border-[#2563eb]"');
  }
  // Filter pills across pages
  if (l.includes('activeFilter ===') && l.includes('?')) {
     l = l.replace(/"bg-gray-800 text-gray-300 hover:bg-gray-700"/, '"bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]"');
     l = l.replace(/"bg-white text-gray-900"/, '"bg-[#2563eb] text-[#ffffff] border border-[#2563eb]"');
  }

  // ============================================
  // EMPTY STATES & DASHED BORDERS
  // ============================================
  l = l.replace(/bg-gray-800\/50/g, 'bg-[#f1f5f9]');
  l = l.replace(/bg-gray-900\/50/g, 'bg-[#f1f5f9]');
  l = l.replace(/bg-\[\#111827\]/g, 'bg-[#f1f5f9]');
  
  if (l.includes('border-dashed')) {
    l = l.replace(/border-gray-800/g, 'border-[#cbd5e1]');
    l = l.replace(/border-\[\#e5e7eb\]/g, 'border-[#cbd5e1]'); // Fix if previously replaced incorrectly
    l = l.replace(/bg-\[\#09090B\]\/50/g, 'bg-[#f8fafc]');
    l = l.replace(/bg-\[\#ffffff\]\/50/g, 'bg-[#f8fafc]');
    l = l.replace(/text-gray-500/g, 'text-[#64748b]');
  }

  // ============================================
  // TEXT COLORS
  // ============================================
  l = l.replace(/text-gray-300/g, 'text-[#64748b]');
  l = l.replace(/text-gray-400/g, 'text-[#64748b]');
  l = l.replace(/text-gray-500/g, 'text-[#64748b]');
  l = l.replace(/text-zinc-400/g, 'text-[#64748b]');
  l = l.replace(/text-zinc-500/g, 'text-[#64748b]');
  l = l.replace(/text-slate-400/g, 'text-[#64748b]');
  l = l.replace(/text-slate-500/g, 'text-[#64748b]');
  l = l.replace(/text-white\/40/g, 'text-[#94a3b8]');
  l = l.replace(/text-white\/60/g, 'text-[#64748b]');
  l = l.replace(/text-white\/80/g, 'text-[#374151]');
  
  // Convert main body text (skip explicitly white text that shouldn't change)
  // Be careful: if a button has text-white, we shouldn't change it to dark #020617.
  // Generally we assume text-white is used for headings. Let's swap text-white to text-[#020617] 
  // only if it's NOT inside a primary button wrapper.
  if (!l.includes('text-[#ffffff] hover:') && !l.includes('bg-[#2563eb]') && !l.includes('bg-blue-600') && !l.includes('bg-emerald-600') && !l.includes('text-[#ffffff]"')) {
    l = l.replace(/text-white/g, 'text-[#020617]');
    l = l.replace(/text-\[\#ffffff\]/g, 'text-[#020617]');
  } else {
    // Specifically fix text-white to text-[#ffffff] in buttons
    l = l.replace(/text-white/g, 'text-[#ffffff]');
  }

  // Fix explicit labels
  if (l.match(/PORTFOLIO VALUE|P&L BREAKDOWN|STOCKS HELD|TOP PERFORMER|WORST PERFORMER|BOT WATCHING|CAPITAL GUARD|ACTIVE STRATEGY|MARKET PULSE|BRAIN CHECK|BOT ACTIVITY|LATEST NEWS/)) {
    l = l.replace(/text-\[\#020617\]/g, 'text-[#64748b] tracking-[0.14em]');
    l = l.replace(/text-\[\#ffffff\]/g, 'text-[#64748b] tracking-[0.14em]');
    l = l.replace(/text-\[\#64748b\] tracking-\[0\.14em\] tracking-\[0\.14em\]/g, 'text-[#64748b] tracking-[0.14em]');
  }

  lines[i] = l;
}

fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', lines.join('\n'));
console.log('Patch complete.');
