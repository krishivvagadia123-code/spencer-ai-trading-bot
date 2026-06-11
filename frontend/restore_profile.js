const fs = require('fs');

let backupCode = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.backup.jsx', 'utf-8');
const startIdx = backupCode.indexOf('function ProfilePage(');
const endIdx = backupCode.indexOf('function getSpencerResponse(');
let profileCode = backupCode.substring(startIdx, endIdx);

// Restore the camera button
profileCode = profileCode.replace(/<button onClick=\{\(\) => fileRef\.current\?\.click\(\)\} className="absolute -bottom-1 -right-1 grid h-7 w-7 place-items-center rounded-full bg-white text-black shadow-lg hover:scale-110 transition-transform">/g, '<button onClick={() => fileRef.current?.click()} className="absolute -bottom-1 -right-1 grid h-7 w-7 place-items-center rounded-full border border-[#e5e7eb] bg-[#ffffff] text-[#020617] shadow-lg hover:scale-110 transition-transform">');

// Password inputs
profileCode = profileCode.replace(/className=\"[^\"]*\" type=\"password\" autoComplete=\"off\" placeholder=\"Current password\"/g, 'className="w-full rounded-[12px] border border-[#e5e7eb] bg-[#ffffff] px-4 py-3 text-[14px] text-[#020617] placeholder:text-[#94a3b8] focus:border-[#2563eb] focus:ring-2 focus:ring-[#bfdbfe] outline-none transition-all" type="password" autoComplete="off" placeholder="Current password"');
profileCode = profileCode.replace(/className=\"[^\"]*\" type=\"password\" autoComplete=\"off\" placeholder=\"New password \(min 8 chars, 1 number, 1 special\)\"/g, 'className="w-full rounded-[12px] border border-[#e5e7eb] bg-[#ffffff] px-4 py-3 text-[14px] text-[#020617] placeholder:text-[#94a3b8] focus:border-[#2563eb] focus:ring-2 focus:ring-[#bfdbfe] outline-none transition-all" type="password" autoComplete="off" placeholder="New password (min 8 chars, 1 number, 1 special)"');

// Update password button
profileCode = profileCode.replace(/<button onClick=\{handlePassUpdate\} disabled=\{!curPass \|\| !newPass\} className=\"lift-button mt-4 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-\[\#ffffff\] hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 transition-all\">Update Password<\/button>/, '<button onClick={handlePassUpdate} disabled={!curPass || !newPass} className={!curPass || !newPass ? "lift-button mt-4 w-full rounded-xl bg-[#f1f5f9] border border-[#e5e7eb] py-3 text-[14px] font-semibold text-[#94a3b8] cursor-not-allowed" : "lift-button mt-4 w-full rounded-xl bg-[#2563eb] py-3 text-[14px] font-semibold text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"}>Update Password</button>');

// Save Changes button
profileCode = profileCode.replace(/<button onClick=\{handleSave\} disabled=\{!hasChanges\} className=\"lift-button w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-\[\#ffffff\] hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 transition-all\">Save Changes<\/button>/, '<button onClick={handleSave} disabled={!hasChanges} className={!hasChanges ? "lift-button w-full rounded-xl bg-[#f1f5f9] border border-[#e5e7eb] py-3 text-[14px] font-semibold text-[#94a3b8] cursor-not-allowed" : "lift-button w-full rounded-xl bg-[#2563eb] py-3 text-[14px] font-semibold text-[#ffffff] hover:bg-[#1d4ed8] transition-colors"}>Save Changes</button>');

// Risk modes
profileCode = profileCode.replace(/border-emerald-500\/50 bg-emerald-500\/10 text-emerald-400/g, 'bg-[#ecfdf5] text-[#047857] border border-[#bbf7d0]');
profileCode = profileCode.replace(/border-gray-800 bg-gray-900\/50 text-gray-400 hover:border-gray-600 hover:text-gray-200/g, 'bg-[#ffffff] text-[#020617] border border-[#e5e7eb] hover:bg-[#f8fafc]');

// Toggles
profileCode = profileCode.replace(/rounded-full bg-blue-600/g, 'rounded-full bg-[#2563eb]');
profileCode = profileCode.replace(/rounded-full bg-gray-700/g, 'rounded-full bg-[#cbd5e1]');
profileCode = profileCode.replace(/h-5 w-5 rounded-full bg-white shadow/g, 'h-5 w-5 rounded-full bg-[#ffffff] shadow');
profileCode = profileCode.replace(/h-5 w-5 rounded-full bg-\[\#09090B\] shadow/g, 'h-5 w-5 rounded-full bg-[#ffffff] shadow');

// Sign out button
profileCode = profileCode.replace(/<button onClick=\{onLogout\} className=\"lift-button flex-1 rounded-full border border-red-200 py-3 text-sm font-medium text-red-600 hover:bg-red-50 transition-all\">Sign Out<\/button>/g, '<button onClick={onLogout} className="lift-button flex w-full items-center justify-center gap-2 rounded-xl border border-[#fecaca] bg-[#ffffff] py-3 text-[14px] font-semibold text-[#dc2626] hover:bg-[#fef2f2] transition-colors"><LogOut className="h-4 w-4 shrink-0" />Sign Out</button>');

// Ensure generic cleanup is applied on profileCode
profileCode = profileCode.replace(/bg-\[\#09090B\]/g, 'bg-[#ffffff]');
profileCode = profileCode.replace(/bg-\[\#050505\]/g, 'bg-[#f8fafc]');
profileCode = profileCode.replace(/bg-black/g, 'bg-[#ffffff]');
profileCode = profileCode.replace(/bg-gray-900/g, 'bg-[#ffffff]');
profileCode = profileCode.replace(/border-gray-800/g, 'border-[#e5e7eb]');
profileCode = profileCode.replace(/text-gray-400/g, 'text-[#64748b]');
profileCode = profileCode.replace(/text-gray-300/g, 'text-[#64748b]');
profileCode = profileCode.replace(/text-gray-500/g, 'text-[#64748b]');

let currentCode = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', 'utf-8');
const curStartIdx = currentCode.indexOf('function ProfilePage(');
const curEndIdx = currentCode.indexOf('function getSpencerResponse(');

currentCode = currentCode.substring(0, curStartIdx) + profileCode + currentCode.substring(curEndIdx);
fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', currentCode);
console.log('ProfilePage restored and patched.');
