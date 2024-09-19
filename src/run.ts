/* eslint-disable @typescript-eslint/no-explicit-any */

import { readFileSync, writeFileSync } from 'fs';
// import { BatchedNetworkSimulator, Giraffe as Node } from './main.js';
import { BatchedNetworkSimulator, Badger as Node } from './main.js';

const TESTNET_CSV = '__tests__/fixtures/testnet-sarafu.csv';
const NUM_ROUNDS_PER_LINE = 50;
function reversePath(path: string): string {
  const hops = path.split('.');
  const innerHops = hops.slice(1, hops.length - 1);
  const reverseInnerHops = innerHops.reverse();
  return [].concat(hops[0], reverseInnerHops, hops[0]).join('.');
}

async function run(): Promise<void> {
  console.log("This simulation will take about 60 seconds to complete.");
  const nodes = {};
  let flushReport;
  const networkSimulator = new BatchedNetworkSimulator();
  const data = readFileSync(TESTNET_CSV, 'utf8')
  const lines = data.split('\n').map(line => {
    const [ from, to, weight ] = line.split(' ')
    return { from, to, weight }
  }).filter(line => line.from !== 'from' && line.from !== '');
  for (let lineNo = 0; lineNo < lines.length; lineNo++) {
    let counter = 0;
    const line = lines[lineNo];
    if (typeof nodes[line.from] === 'undefined') {
      console.log("Adding node", line.from);
      nodes[line.from] = new Node(line.from);
      networkSimulator.addNode(line.from, nodes[line.from]);
    }
    if (typeof nodes[line.to] === 'undefined') {
      console.log("Adding node", line.to);
      nodes[line.to] = new Node(line.to);
      networkSimulator.addNode(line.to, nodes[line.to]);
    }
    console.log("Meeting", JSON.stringify(line.from), JSON.stringify(line.to));
    await nodes[line.from].meet(line.to);
    console.log("Done meeting, now flushing");
    do {
      flushReport = networkSimulator.flush();
      if (counter > NUM_ROUNDS_PER_LINE) {
        process.exit();
      }
      // console.log(`Line ${lineNo + 1} [${line.from} ${line.to} ${line.weight}] Round ${counter}:`);
      flushReport.forEach(msg => { console.log(`${lineNo}:${counter}: ${msg}`); });
      // console.log();
    } while ((flushReport.length > 0) && (counter++ < NUM_ROUNDS_PER_LINE));
  }
  // console.log('Loops found:');
  const loops = {};
  Object.keys(nodes).forEach((nodeId) => {
    // console.log(nodeId, nodes[nodeId].getLoops());
    nodes[nodeId].getLoops().forEach((loopStr: string) => {
      const [ from, to, probeId, traceId, legId ] = loopStr.split(' ');
      const loopId = `${probeId} ${traceId} ${legId}`;
      // console.log('storing', from, nodeId, to, loopId, loops[loopId]);
      if (typeof loops[loopId] === 'undefined') {
        loops[loopId] = {};
      }
      if (typeof loops[loopId][from] === 'undefined') {
        // console.log('storing', loopId, from, nodeId);
        loops[loopId][from] = nodeId;
      } else if (loops[loopId][from] !== nodeId) {
        console.log(`loop route conflict! ${loopId} goes from ${from} to both ${loops[loopId][from]} and ${nodeId}`);
      }
      if (typeof loops[loopId][nodeId] === 'undefined') {
        // console.log('storing', loopId, nodeId, to);
        loops[loopId][nodeId] = to;
      } else if (loops[loopId][nodeId] !== to) {
        console.log(`loop route conflict! ${loopId} goes from ${nodeId} to both ${loops[loopId][nodeId]} and ${to}`);
      }
    });
  });
  // console.log('Debug logs:');
  // Object.keys(nodes).forEach((nodeId) => {
  //   writeFileSync(`logs/${nodeId}.log`, nodes[nodeId].getDebugLog().join('\n') + '\n');
  // });
  const paths = {};
  Object.keys(loops).map((loopId) => {
    const start = Math.min(... Object.keys(loops[loopId]).map(numStr => parseInt(numStr))).toString();
    const hops = [];
    let cursor = start;
    do {
      if (typeof cursor === 'undefined') {
        throw new Error('path lost!');
      }
      // console.log(`${loopId} ${cursor} ${JSON.stringify(loops[loopId])}`);
      hops.push(cursor);
      cursor = loops[loopId][cursor];
    } while ((typeof cursor !== 'undefined') && (cursor != start));
    hops.push(cursor);
    const path = hops.join('.');
    if (typeof paths[path] === 'undefined') {
      paths[path] = [];
    }
    if (paths[path].indexOf(loopId) === -1) {
      paths[path].push(loopId);
    }
  });
  const reverses = [];
  const deduplicated = Object.keys(paths).sort().filter(path => {
    reverses.push(reversePath(path));
    return (reverses.indexOf(path) === -1);
  });
  console.log(`Found ${deduplicated.length} paths:`);
  deduplicated.forEach((path) => {
    // console.log(path, paths[path]);
    console.log(path);
  });
  // console.log(reverses);
  // console.log(networkSimulator.getPlantUml('possible'));
}


// ...
run();
