const fs = require('fs');
let code = fs.readFileSync('src/App.jsx', 'utf8');

// Use a regex to extract all button tags and their attributes
const buttonRegex = /<button([^>]*)>/g;
let match;
let noClickButtons = [];
let allButtonsCount = 0;

while ((match = buttonRegex.exec(code)) !== null) {
  allButtonsCount++;
  const attributes = match[1];
  
  if (!attributes.includes('onClick') && !attributes.includes('type="submit"') && !attributes.includes('type="reset"')) {
    // Attempt to extract text inside the button to identify it
    const startIdx = match.index + match[0].length;
    const endIdx = code.indexOf('</button>', startIdx);
    let innerContent = code.substring(startIdx, endIdx).trim();
    // clean up inner HTML if any
    innerContent = innerContent.replace(/<[^>]+>/g, '').trim();
    if (!innerContent) innerContent = "(Icon Button / Dynamic content)";
    
    noClickButtons.push({
      text: innerContent.substring(0, 50),
      attributes: attributes.trim()
    });
  }
}

console.log(`Found ${allButtonsCount} buttons.`);
console.log(`Found ${noClickButtons.length} buttons without onClick or type="submit":`);
noClickButtons.forEach((b, i) => {
  console.log(`${i+1}. [${b.text}] - Attributes: ${b.attributes.substring(0, 60)}...`);
});
