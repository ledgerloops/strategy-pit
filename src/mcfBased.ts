import { createInterface } from 'readline';
import { createReadStream, promises } from 'fs';
import { Edge, minCostFlow } from 'min-cost-flow';
import { scale } from './util.js';

const LEDGER_SCALE = 1000;
const ROUNDING_MARGIN = 0.0000001;

const DEBTCSV = process.argv[2] || './/debt.csv';
const SOLUTIONCSV = process.argv[3] || './solution.csv';
console.log('Opening', DEBTCSV);

const lineReader = createInterface({
  input: createReadStream(DEBTCSV),
});
const graph: {
  [pair: string]: number;
} = {};
const edges: Edge<string>[] = [];
lineReader.on('line', function (line) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [ from, to, amountStr ] = line.split(' ');
  const amount = scale(amountStr, 'debt', LEDGER_SCALE, ROUNDING_MARGIN);
  edges.push({
    from,
    to,
    capacity: amount,
    cost: 1,
  } as Edge<string>);
  const edge = `${from} ${to}`;
    if (typeof graph[edge] === 'undefined') {
      graph[edge] = 0;
    }
    const scaledAmount = scale(amountStr, 'debt', LEDGER_SCALE, ROUNDING_MARGIN);
    graph[edge] += scaledAmount;
});

lineReader.on('close', async function () {
  const netPositions: {
    [nodeNum: string]: number;
  }= {};
  Object.keys(graph).forEach(pair => {
    const participants = pair.split(' ');
    participants.forEach(participant => {
      if (typeof netPositions[participant] === 'undefined') {
        netPositions[participant] = 0;
      }
    });
    netPositions[participants[0]] -= graph[pair]; // a negative net position means outgoing transfers predominantly happened
    netPositions[participants[1]] += graph[pair]; // a positive net position means incoming transfers predominantly happened
  });
  // console.log(netPositions);
  Object.keys(netPositions).forEach(node => {
    if (netPositions[node] < 0) { // a negative net position means outgoing transfers predominantly happened
      // console.log(`adding link from source to ${node} for net position ${netPositions[node]}`);
      edges.push({
        from: 'SOURCE',
        to: node,
        capacity: -netPositions[node],
        cost: 0
      } as Edge<string>);
    }
    if (netPositions[node] > 0) { // a positive net position means incoming transfers predominantly happened
      // console.log(`adding link from ${node} to drain for net position ${netPositions[node]}`);
      edges.push({
        from: node,
        to: 'DRAIN',
        capacity: netPositions[node],
        cost: 0
      } as Edge<string>);
    }
  });
  console.log(`Starting Min Cost Flow algorithm on ${edges.length} edges`);
  const result = minCostFlow(edges);
  console.log(`Finished Min Cost Flow algorithm; determined flow for ${result.length} edges`);
  await promises.writeFile(SOLUTIONCSV, '');
  await Promise.all(result.map(async (edge: Edge<string>) => {
    if (edge.capacity > edge.flow) {
      return promises.appendFile(SOLUTIONCSV, `${edge.from} ${edge.to} ${(edge.capacity - edge.flow) / LEDGER_SCALE}\n`);
    }
  }));
});
