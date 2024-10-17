import { readCsv } from "./readCsv.js";

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
  await readCsv(DEBTFILE, ' ', (cells: string[]) => {
    const [ from, to, amountStr ] = cells;
    const amount = parseFloat(amountStr);

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
  let totalSolution = 0;
  let numSolution = 0;
  await readCsv(SOLUTIONFILE, ' ', (cells: string[]) => {
    const amount = parseFloat(cells.pop());
    numSolution++;
    totalSolution += cells.length * amount;
    for (let i = 0; i < cells.length - 1; i++) {
      const edge = `${cells[i]} ${cells[i + 1]}`;
      if (graph[edge] < amount) {
        throw new Error(`Netting agreement ${cells.join(' ')} ${amount} cannot be applied to edge ${edge} with balance ${graph[edge]}`);
      }
      graph[edge] -= amount;      
    }
  });
  console.log(`Solution removed ${totalSolution} debt in ${numSolution} cycles`);
  console.log(`Done`);

}

// ...
run();