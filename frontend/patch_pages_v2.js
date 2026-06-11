const fs = require('fs');
let code = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', 'utf-8');

// Helper to patch within a specific function boundary
function patchComponent(name, patcher) {
  const startIdx = code.indexOf(`function ${name}(`);
  if (startIdx === -1) return;
  // find next function as boundary
  const endIdx = code.indexOf(`function `, startIdx + 10);
  const boundary = endIdx !== -1 ? endIdx : code.length;
  
  let section = code.substring(startIdx, boundary);
  section = patcher(section);
  code = code.substring(0, startIdx) + section + code.substring(boundary);
}

// 1. DrawerNav (Search)
patchComponent('DrawerNav', (s) => {
  return s.replace(/placeholder="Search stock, sector[^"]*"/, (m) => m + ' className="h-full w-full bg-[#f8fafc] pl-10 pr-4 text-[13px] font-medium text-[#020617] border border-[#e5e7eb] outline-none placeholder:text-[#94a3b8] rounded-md"');
});

// 2. PositionsPage
patchComponent('PositionsPage', (s) => {
  // Tabs
  s = s.replace(/bg-gray-800 text-gray-300 hover:bg-gray-700/g, 'bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]');
  s = s.replace(/bg-\[\#ffffff\] text-\[\#020617\] border border-\[\#e5e7eb\] hover:bg-\[\#f8fafc\]/g, 'bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]'); // reverse accidental
  s = s.replace(/bg-white text-gray-900/g, 'bg-[#2563eb] text-[#ffffff] border border-[#2563eb]');
  // Empty State
  s = s.replace(/text-gray-400/g, 'text-[#64748b]');
  s = s.replace(/text-gray-300/g, 'text-[#334155]');
  s = s.replace(/bg-\[\#f1f5f9\]/g, 'bg-[#f1f5f9] text-[#64748b] border border-[#e5e7eb]');
  return s;
});

// 3. BrainPage
patchComponent('BrainPage', (s) => {
  s = s.replace(/Analyze with AI/g, 'Analyze with AI'); // The button replacement handles this if done right, let's fix it explicitly
  s = s.replace(/<button[^>]*>([\s\S]*?)Analyze with AI([\s\S]*?)<\/button>/, '<button className="lift-button flex w-full items-center justify-center gap-2 rounded-lg bg-[#2563eb] py-3 text-[14px] font-semibold text-[#ffffff] hover:bg-[#1d4ed8] transition-colors">$1Analyze with AI$2</button>');
  
  // Metric boxes and Research cards (they had border-gray-800)
  s = s.replace(/border-gray-800/g, 'border-[#e5e7eb]');
  s = s.replace(/bg-\[\#ffffff\]/g, 'bg-[#f8fafc]'); // Make metric boxes f8fafc
  s = s.replace(/bg-\[\#f8fafc\]/g, 'bg-[#f8fafc] border border-[#e5e7eb] rounded-xl text-[#020617]'); 
  
  // Error alert
  s = s.replace(/bg-red-500\/10 text-red-400 border border-red-500\/20/g, 'bg-[#fef2f2] text-[#dc2626] border border-[#fecaca]');
  return s;
});

// 4. StrategyLabPage
patchComponent('StrategyLabPage', (s) => {
  s = s.replace(/bg-gray-800 text-gray-300 hover:bg-gray-700/g, 'bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]');
  s = s.replace(/bg-white text-gray-900/g, 'bg-[#2563eb] text-[#ffffff] border border-[#2563eb]');
  
  s = s.replace(/<button[^>]*>([\s\S]*?)\+ Add strategy([\s\S]*?)<\/button>/, '<button onClick={() => setShowAddModal(true)} className="flex items-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2 text-[13px] font-medium text-[#ffffff] hover:bg-[#1d4ed8] transition-colors">$1+ Add strategy$2</button>');
  
  // Badges
  s = s.replace(/bg-blue-500\/10 text-blue-400 border border-blue-500\/20/g, 'bg-[#eff6ff] text-[#2563eb] border border-[#bfdbfe]');
  s = s.replace(/bg-emerald-500\/10 text-emerald-400 border border-emerald-500\/20/g, 'bg-[#ecfdf5] text-[#059669] border border-[#bbf7d0]');
  s = s.replace(/bg-amber-500\/10 text-amber-400 border border-amber-500\/20/g, 'bg-[#fffbeb] text-[#d97706] border border-[#fde68a]');
  
  // Delete button
  s = s.replace(/text-rose-400 hover:bg-rose-500\/10/g, 'bg-[#fef2f2] text-[#dc2626] hover:bg-[#fee2e2]');
  return s;
});

// 5. CopyTradingPage
patchComponent('CopyTradingPage', (s) => {
  s = s.replace(/<button[^>]*>([\s\S]*?)\+ New copy setup([\s\S]*?)<\/button>/, '<button onClick={() => setShowAddModal(true)} className="flex items-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2 text-[13px] font-medium text-[#ffffff] hover:bg-[#1d4ed8] transition-colors">$1+ New copy setup$2</button>');
  
  s = s.replace(/bg-gray-800 text-gray-400 border border-gray-700/g, 'bg-[#f1f5f9] text-[#475569] border border-[#e2e8f0]');
  s = s.replace(/bg-emerald-500\/10 text-emerald-400 border border-emerald-500\/20/g, 'bg-[#ecfdf5] text-[#059669] border border-[#bbf7d0]');
  s = s.replace(/bg-amber-500\/10 text-amber-400 border border-amber-500\/20/g, 'bg-[#fffbeb] text-[#d97706] border border-[#fde68a]');
  return s;
});

// 6. LiveNewsPage
patchComponent('LiveNewsPage', (s) => {
  s = s.replace(/bg-gray-800 text-gray-300 hover:bg-gray-700/g, 'bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]');
  s = s.replace(/bg-white text-gray-900/g, 'bg-[#2563eb] text-[#ffffff] border border-[#2563eb]');
  return s;
});

// 7. TradeTrackerPage
patchComponent('TradeTrackerPage', (s) => {
  s = s.replace(/<button[^>]*>([\s\S]*?)\+ Log trade([\s\S]*?)<\/button>/, '<button onClick={() => setShowLogModal(true)} className="flex items-center gap-2 rounded-lg bg-[#2563eb] px-4 py-2 text-[13px] font-medium text-[#ffffff] hover:bg-[#1d4ed8] transition-colors">$1+ Log trade$2</button>');
  return s;
});

// 8. ProfilePage
patchComponent('ProfilePage', (s) => {
  // Password inputs
  s = s.replace(/className="[^"]*placeholder="Current password"[^"]*"/, 'className="w-full rounded-[12px] border border-[#e5e7eb] bg-[#ffffff] px-4 py-3 text-[14px] text-[#020617] placeholder:text-[#94a3b8] focus:border-[#2563eb] focus:ring-2 focus:ring-[#bfdbfe] outline-none transition-all" placeholder="Current password"');
  s = s.replace(/className="[^"]*placeholder="New password[^"]*"/, 'className="w-full rounded-[12px] border border-[#e5e7eb] bg-[#ffffff] px-4 py-3 text-[14px] text-[#020617] placeholder:text-[#94a3b8] focus:border-[#2563eb] focus:ring-2 focus:ring-[#bfdbfe] outline-none transition-all" placeholder="New password (min 8 chars, 1 number, 1 special)"');

  // Risk modes
  s = s.replace(/border-emerald-500\/50 bg-emerald-500\/10/g, 'bg-[#ecfdf5] text-[#047857] border border-[#bbf7d0]');
  s = s.replace(/border-gray-800 bg-gray-900\/50/g, 'bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]');
  
  // Toggles
  // bg-blue-600 -> bg-[#2563eb]
  s = s.replace(/bg-blue-600/g, 'bg-[#2563eb]');
  // bg-gray-700 -> bg-[#cbd5e1]
  s = s.replace(/bg-gray-700/g, 'bg-[#cbd5e1]');

  // Sign out button
  s = s.replace(/<button[^>]*>([\s\S]*?)Sign Out([\s\S]*?)<\/button>/, '<button onClick={onLogout} className="lift-button flex w-full items-center justify-center gap-2 rounded-xl border border-[#fecaca] bg-[#ffffff] py-3 text-[14px] font-semibold text-[#dc2626] hover:bg-[#fef2f2] transition-colors">$1Sign Out$2</button>');
  
  return s;
});

// General cleanup of class artifacts
code = code.replace(/text-\[\#020617\] font-semibold/g, 'text-[#020617] font-semibold');
code = code.replace(/text-\[\#64748b\] text-\[\#64748b\]/g, 'text-[#64748b]');

fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', code);
console.log('Targeted patch complete.');
