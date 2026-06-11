const fs = require('fs');

// Patch constants.js
let constCode = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/utils/constants.js', 'utf-8');
constCode = constCode.replace(/status:"Queued"/g, 'status:"Not Tested"');
fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/utils/constants.js', constCode);
console.log('constants.js patched');

// Patch App.jsx
let appCode = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', 'utf-8');

// 1. App initialization migration
appCode = appCode.replace(
  /const \[strategies, setStrategies\] = useState\(\(\) => UDB.strategies\(user.id\) \|\| defaultStrategies\);/,
  `const [strategies, setStrategies] = useState(() => {
    const saved = UDB.strategies(user.id);
    if (!saved) return defaultStrategies;
    // Migrate default strategies that might have old fake metrics
    return saved.map(s => {
      if (/^s\\d+$/.test(s.id)) {
        return { ...s, wins: 0, losses: 0, status: s.status === "Testing" ? "Testing" : "Not Tested" };
      }
      return s;
    });
  });`
);

// 2. StrategyLabPage UI fixes
// Add "Not Tested" to status styles
appCode = appCode.replace(
  /const statusStyle = \{ Testing:"bg-emerald-50 text-emerald-700 border-emerald-200", Queued:"bg-\[\#f8fafc\] text-\[\#374151\] border-gray-200", Paused:"bg-amber-50 text-amber-700 border-amber-200" \};/,
  `const statusStyle = { Testing:"bg-[#ecfdf5] text-[#059669] border-[#bbf7d0]", Queued:"bg-[#f1f5f9] text-[#475569] border-[#e2e8f0]", Paused:"bg-[#fffbeb] text-[#d97706] border-[#fde68a]", "Not Tested":"bg-[#ffffff] text-[#94a3b8] border-[#e5e7eb]" };`
);

// Fix win rate rendering
appCode = appCode.replace(
  /<div className="text-xs text-emerald-600 font-medium">\{s\.wins\}W \/ \{s\.losses\}L<\/div>\s*<div className="text-\[10px\] text-\[\#94a3b8\]">\{s\.wins \+ s\.losses > 0 \? \`\$\{Math\.round\(s\.wins\/\(s\.wins\+s\.losses\)\*100\)\}\%\` : "—"\} win<\/div>/g,
  `<div className={s.wins + s.losses > 0 ? "text-xs text-[#059669] font-medium" : "text-xs text-[#94a3b8] font-medium"}>{s.wins}W / {s.losses}L</div>
                  <div className="text-[10px] text-[#94a3b8]">{s.wins + s.losses > 0 ? \`\${Math.round(s.wins/(s.wins+s.losses)*100)}%\` : "—"} win</div>`
);

// Fix AddStratModal Initial status options
appCode = appCode.replace(
  /const \[status, setStatus\] = useState\("Queued"\);/,
  `const [status, setStatus] = useState("Not Tested");`
);
appCode = appCode.replace(
  /\{\["Queued","Testing"\]\.map\(s =>/g,
  `{["Not Tested","Queued","Testing"].map(s =>`
);


fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/App.jsx', appCode);
console.log('App.jsx patched');
