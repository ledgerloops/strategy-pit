import { readCsv } from "./readCsv.js";
import { writeFile, appendFile } from "node:fs/promises";

const INFILE = process.argv[2] || '../Sarafu2021_UKdb_submission/sarafu_xDAI/sarafu_txns_20200125-20210615.csv';
const OUTFILE = process.argv[3] || './debt.csv';

const LEDGER_SCALE = 1000;

async function run(): Promise<void> {
  const graph: {
    [pair: string]: number;
  } = {};
  let numTrans = 0;
  let totalAmount = 0;
  console.log(`Reading from ${INFILE}...`);
  const nodesBefore: {
    [nodeNum: string]: boolean;
  }= {};
  await readCsv(INFILE, (from, to, amount) => {
    nodesBefore[from] = true;
    nodesBefore[to] = true;
    
    const edge = `${from} ${to}`;
    if (typeof graph[edge] === 'undefined') {
      graph[edge] = 0;
    }
    graph[edge] += Math.round(amount * LEDGER_SCALE);
    numTrans++;
    totalAmount += Math.round(amount * LEDGER_SCALE);
  });
  console.log(`Processed ${numTrans} transactions between ${Object.keys(nodesBefore).length} accounts into ${Object.keys(graph).length} unilateral aggregate balances, total amount around ${Math.round(totalAmount / LEDGER_SCALE / 1000000)} million Sarafu`);
  let totalBilateral = 0;
  let numBilateral = 0;
  Object.keys(graph).forEach(pair => {
    const counterPair = pair.split(' ').reverse().join(' ');
    if (typeof counterPair !== 'undefined') {
      if (graph[pair] >= graph[counterPair]) {
        totalBilateral += graph[counterPair];
        numBilateral++;
        graph[pair] -= graph[counterPair];
        delete graph[counterPair];
      }
    }
  });
  let check = 0;
  Object.keys(graph).forEach(pair => {
    check += graph[pair];
  });
  if (check !== (totalAmount - 2 * totalBilateral)) {
    throw new Error(`${check} + 2 * ${totalBilateral} doesn't add up to ${totalAmount}`);
  }
  console.log(`Applied bilateral netting ${numBilateral} times, for a total amount of 2 * around ${Math.round(totalBilateral / LEDGER_SCALE / 1000000)} million Sarafu, leaving ${Object.keys(graph).length} bilateral balances with a total of around ${Math.round(check / LEDGER_SCALE / 1000000)} million Sarafu`);
  let numRemoved = 0;
  const netPositions: {
    [nodeNum: string]: number;
  }= {};
  Object.keys(graph).forEach(pair => {
    if (graph[pair] === 0) {
      delete graph[pair];
      numRemoved++;
    } else if (graph[pair] < 0) { 
      throw new Error(`Unexpected negative edge weight`);
    } else {
      const participants = pair.split(' ');
      participants.forEach(participant => {
        if (typeof netPositions[participant] === 'undefined') {
          netPositions[participant] = 0;
        }
      });
      netPositions[participants[0]] += graph[pair];
      netPositions[participants[1]] -= graph[pair];
    }
  });
  console.log(`Removed ${numRemoved} zero balances, leaving ${Object.keys(graph).length} non-zero balances between ${Object.keys(netPositions).length} accounts`);
  let totalPos = 0;
  let totalNeg = 0;
  Object.keys(netPositions).forEach(account => {
    if (netPositions[account] > 0) {
      totalPos += netPositions[account];
    } else if (netPositions[account] < 0) {
      totalNeg -= netPositions[account];
    }
  });
  if (totalPos != totalNeg) {
    throw new Error(`Sum of positive net positions (${totalPos / LEDGER_SCALE / 1000000} million Sarafu) doesn't match`
                 + ` sum of negative net positions (${totalNeg / LEDGER_SCALE / 1000000} million Sarafu)`);
  }
  console.log(`Net Internal Debt (NID): around ${Math.round(totalPos / LEDGER_SCALE / 1000000)} million Sarafu. That is around ${Math.round(100 * totalPos / check)} percent of the total of around ${Math.round(check / LEDGER_SCALE / 1000000)} million Sarafu in bilateral balances`);

  console.log(`Writing to ${OUTFILE}...`);
  await writeFile(OUTFILE, '');
  const promises = Object.keys(graph).map(pair => appendFile(OUTFILE, `${pair} ${graph[pair] / LEDGER_SCALE}\n`));
  await Promise.all(promises);
  console.log(`Done`);

}

// ...
run();