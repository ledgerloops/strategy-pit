import { createInterface } from 'readline';
import { createReadStream } from 'fs';
import { BirdsEyeWorm } from './BirdsEyeWorm.js';

const DEBTCSV = process.argv[2] || './debt.csv';
const SOLUTIONCSV = process.argv[3] || './solution.csv';
console.log('Opening', DEBTCSV);
const check = '19897 23610 21257 20069 22568 27857 27867 27868 27869 27865 27872 21250 21549 9410 21925 22969 22100 22112 21523 24137 20484 22590 22103 21750 27561 21770 21811 29414 19882 20467 24126 20493 22591 22102 21768 27560 24105 22579 22105 21745 27562 21429 21822 29406 19855 22578 22110 21520 27564 21420 21833 19585 21851 22569 22107 21743 27563 21426 21823 23620 21253 21280 33361 31417 31376 31420 31382 20475 19939 29405 19897'.split(' '); // weight 45, length 71
const linksCheck = {};
const lineReader = createInterface({
  input: createReadStream(DEBTCSV),
});
let totalTransAmount = 0;
let numTrans = 0;
const birdsEyeWorm = new BirdsEyeWorm(true, SOLUTIONCSV);
lineReader.on('line', function (line) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [ from, to, amountStr ] = line.split(' ');
  if (typeof linksCheck[from] === 'undefined') { linksCheck[from] = {}; }
  if (typeof linksCheck[from][to] === 'undefined') { linksCheck[from][to] = 0; }
  linksCheck[from][to] += amountStr;
  birdsEyeWorm.addTransfer(from, to, parseFloat(amountStr));
  numTrans++;
  totalTransAmount += parseFloat(amountStr);
});

lineReader.on('close', async function () {
  const uniqueElements = new Set();
  for (let i = 0; i < check.length - 1; i++) {
    if (typeof linksCheck[check[i]] === 'undefined') { throw new Error(`no way out of ${check[i]}`); }
    if (typeof linksCheck[check[i]][check[i+1]] === 'undefined') { throw new Error(`no way from ${check[i]} to  ${check[i+1]}`); }
    if (linksCheck[check[i]][check[i+1]] < 114) {
      throw new Error(`link from ${check[i]} to ${check[i+1]} is only ${linksCheck[check[i]][check[i+1]]} wide`);
    }
    if (uniqueElements.has(check[i])) {
      throw new Error(`Node ${check[i]} visited twice!`);
    } else {
      uniqueElements.add(check[i]);
    }
  }

  // throw new Error('links check OK!');
  await birdsEyeWorm.runWorm();
  Object.keys(birdsEyeWorm.stats).filter(loopLength => loopLength !== '2').forEach((loopLength: string) => {
    console.log(`Length ${loopLength}: found ${birdsEyeWorm.stats[loopLength].numFound} loops, average amount: around ${Math.round(birdsEyeWorm.stats[loopLength].totalAmount / birdsEyeWorm.stats[loopLength].numFound)}`);
  });
  const links = birdsEyeWorm.graph.getLinks();
  let numLinks = 0;
  Object.keys(links).forEach(from => {
    numLinks += Object.keys(links[from]).length;
  });
  // console.log(birdsEyeWorm.stats);
  console.log(`Graph has ${Object.keys(links).length} nodes and ${numLinks} links left`);
  console.log(`After ${numTrans} transactions with a total amount of ${Math.round(totalTransAmount / 1000000)} million`);
  let totalNum = 0;
  let totalMultilateral = 0;
  // const totalBilateral = birdsEyeWorm.stats[2].totalAmount;
  Object.keys(birdsEyeWorm.stats).map(numStr => {
    if (numStr !== '2') {
      totalMultilateral += birdsEyeWorm.stats[numStr].totalAmount * parseInt(numStr);
      totalNum += birdsEyeWorm.stats[numStr].numFound;
    }
  });
  const amountLeft = totalTransAmount -  totalMultilateral;
  console.log(`${Math.round(totalMultilateral / 1000000)} million (${Math.round((totalMultilateral / totalTransAmount) * 100)}%) was netted in ${totalNum} loops`);
  console.log(`Leaving ${Math.round(amountLeft / 1000000)} million (${Math.round((amountLeft / totalTransAmount) * 100)}%) to be settled out of band`);
});
