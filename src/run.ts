/* eslint-disable @typescript-eslint/no-explicit-any */

import { readFileSync } from 'fs';
// import { BatchedNetworkSimulator, Giraffe as Node } from './main.js';
import { BatchedNetworkSimulator, Badger as Node } from './main.js';

const TESTNET_CSV = '__tests__/fixtures/testnet-sarafu.csv';
const NUM_ROUNDS = 1000;

async function run(): Promise<void> {
  console.log("This simulation will take about 60 seconds to complete.");
  const nodes = {};
  let flushReport;
  const networkSimulator = new BatchedNetworkSimulator();
  const data = readFileSync(TESTNET_CSV, 'utf8')
  const lines = data.split('\n').map(line => {
    const [ from, to ] = line.split(' ')
    return { from, to }
  }).filter(line => line.from !== 'from' && line.from !== '');
  let counter = 0;

  for (let lineNo = 0; lineNo < lines.length; lineNo++) {
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
      if (counter > NUM_ROUNDS) {
        process.exit();
      }
      console.log(`Round ${counter}:`);
      flushReport.forEach(msg => { console.log(`${counter}: ${msg}`); });
      console.log();
    } while ((flushReport.length > 0) && (counter++ < NUM_ROUNDS));
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
        console.log('loop route conflict!');
      }
      if (typeof loops[loopId][nodeId] === 'undefined') {
        // console.log('storing', loopId, nodeId, to);
        loops[loopId][nodeId] = to;
      } else if (loops[loopId][nodeId] !== to) {
        console.log('loop route conflict!');
      }
    });
  });
  // console.log('Debug logs:');
  // Object.keys(nodes).forEach((nodeId) => {
  //   console.log(nodeId, nodes[nodeId].getDebugLog());
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
  console.log(`Found ${Object.keys(paths).length} paths:`);
  Object.keys(paths).sort().forEach((path) => {
    // console.log(path, paths[path]);
    console.log(path);
  });
}


// ...
run();