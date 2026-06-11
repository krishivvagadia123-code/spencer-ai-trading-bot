const fs = require('fs');
const code = fs.readFileSync('src/App.jsx', 'utf8');

function extract(name) {
  const start = code.indexOf(`function ${name}(`);
  if (start === -1) return `// ${name} not found`;
  
  let braceCount = 0;
  let inFunc = false;
  let end = -1;
  
  for (let i = start; i < code.length; i++) {
    if (code[i] === '{') {
      braceCount++;
      inFunc = true;
    }
    else if (code[i] === '}') {
      braceCount--;
      if (inFunc && braceCount === 0) {
        end = i + 1;
        break;
      }
    }
  }
  return code.substring(start, end);
}

const comps = ['TickerBar', 'Header', 'PortfolioOverview', 'Widget', 'StockButton', 'Dashboard'];
let out = '';
for (const c of comps) out += extract(c) + '\n\n';

fs.writeFileSync('dashboard_comps_original.jsx', out);
console.log('Extracted to dashboard_comps_original.jsx');
