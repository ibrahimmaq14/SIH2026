const fs = require('fs');
const path = require('path');

const nbPath = path.join(__dirname, 'Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data', 'Analysis of AIS Data.ipynb');
const nb = JSON.parse(fs.readFileSync(nbPath, 'utf8'));

const cells = nb.cells;
// Only output cells 0-77
cells.slice(0, 78).forEach((c, i) => {
  const src = c.source.join('');
  if (c.cell_type === 'code') {
    console.log(`\n=== CODE CELL ${i} ===`);
    console.log(src.substring(0, 2000));
  } else if (c.cell_type === 'markdown') {
    console.log(`\n--- MARKDOWN ${i} ---`);
    console.log(src.substring(0, 400));
  }
});
