import { createInterface } from 'readline';
import { createReadStream } from 'fs';
import { writeFile, appendFile } from 'node:fs/promises';
import { Graph } from './BirdsEyeGraph.js';

const DEBTCSV = process.argv[2] || './debt.csv';
const SOLUTIONCSV = process.argv[3] || './solution.csv';
console.log('Opening', DEBTCSV);

const stats: {
    [loopLength: number]: {
      numFound: number;
      totalAmount: number;
    }
  } = {};

const lineReader = createInterface({
  input: createReadStream(DEBTCSV),
});
let totalTransAmount = 0;
let numTrans = 0;
const graph = new Graph();
lineReader.on('line', function (line) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [ from, to, amountStr ] = line.split(' ');
  graph.addWeight(from, to, parseFloat(amountStr));
  numTrans++;
  totalTransAmount += parseFloat(amountStr);
});

const visited: { [name: string]: boolean } = {};
const cameFrom: { [from: string]: string } = {};
function traverse(from: string, to: string): void {
  cameFrom[to] = from;
  visit(to);
}
function visit(node: string): void {
  if (visited[node]) {
    // console.log(Object.keys(visited), cameFrom);
    const path = [];
    let cursor = node;
    do {
      // console.log('appending to path', cursor);
      path.push(cursor);
      cursor = cameFrom[cursor];
      // console.log('checking equality', cursor, node);
    } while (cursor !== node && path.length  < 20);
    const loop = path.reverse().join(' ');
    console.log(loop);
    appendFile(SOLUTIONCSV, loop + '\n').then(() => {      
      throw new Error('loop found!');
    });
  }
  visited[node] = true;
  graph.getOutgoingLinks(node).forEach(to => traverse(node, to));
}

lineReader.on('close', async function () {
  await writeFile(SOLUTIONCSV, '');
  visit(graph.getFirstNode());

  Object.keys(stats).filter(loopLength => loopLength !== '2').forEach((loopLength: string) => {
    console.log(`Length ${loopLength}: found ${stats[loopLength].numFound} loops, average amount: around ${Math.round(stats[loopLength].totalAmount / stats[loopLength].numFound)}`);
  });
  const links = graph.getLinks();
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
  Object.keys(stats).map(numStr => {
    if (numStr !== '2') {
      totalMultilateral += stats[numStr].totalAmount * parseInt(numStr);
      totalNum += stats[numStr].numFound;
    }
  });
  const amountLeft = totalTransAmount -  totalMultilateral;
  console.log(`${Math.round(totalMultilateral / 1000000)} million (${Math.round((totalMultilateral / totalTransAmount) * 100)}%) was netted in ${totalNum} loops`);
  console.log(`Leaving ${Math.round(amountLeft / 1000000)} million (${Math.round((amountLeft / totalTransAmount) * 100)}%) to be settled out of band`);
});
