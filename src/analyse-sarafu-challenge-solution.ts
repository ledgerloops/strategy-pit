import { readSarafuCsv } from "./readCsv.js";

const DEBTFILE = process.argv[2] || '../debt.csv';
const SOLUTIONFILE = process.argv[3] || './solution.csv';

const LEDGER_SCALE = 1000;

async function run(): Promise<void> {
  const graph: {
    [pair: string]: number;
  } = {};
  let numTrans = 0;
  let totalAmount = 0;
  console.log(`Reading debt graph from ${DEBTFILE}...`);
  const nodesBefore: {
    [nodeNum: string]: boolean;
  }= {};
  await readSarafuCsv(DEBTFILE, (from, to, amount) => {
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
  console.log(`Imported ${numTrans} transactions between ${Object.keys(nodesBefore).length} accounts into ${Object.keys(graph).length} balances, total amount around ${Math.round(totalAmount / LEDGER_SCALE / 1000000)} million Sarafu`);
//   let totalSolution = 0;
//   let numSolution = 0;
  await readSarafuCsv(SOLUTIONFILE, (from, to, amount) => {
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
  console.log(`Done`);

}

// ...
run();