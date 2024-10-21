import { createInterface } from 'readline';
import { createReadStream } from 'fs';
import { BirdsEyeWorm } from './BirdsEyeWorm.js';

const DEBTCSV = process.argv[2] || './debt.csv';
const SOLUTIONCSV = process.argv[3] || './solution.csv';
console.log('Opening', DEBTCSV);

const lineReader = createInterface({
  input: createReadStream(DEBTCSV),
});
let totalTransAmount = 0;
let numTrans = 0;
const birdsEyeWorm = new BirdsEyeWorm(true, SOLUTIONCSV);
lineReader.on('line', function (line) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [ from, to, amountStr ] = line.split(' ');
  birdsEyeWorm.addTransfer(from, to, parseFloat(amountStr));
  numTrans++;
  totalTransAmount += parseFloat(amountStr);
});

lineReader.on('close', async function () {
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
