const fs = require('fs');
const code = fs.readFileSync('src/App.jsx', 'utf8');

const dashStart = code.indexOf('function Dashboard(');
const nextFunc = code.indexOf('function App(', dashStart);

const dashCode = code.substring(dashStart, nextFunc);
fs.writeFileSync('dash_extracted.jsx', dashCode);
console.log('Extracted dashboard to dash_extracted.jsx');
