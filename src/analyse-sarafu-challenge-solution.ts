import { readCsv } from "./readCsv.js";
import { scale } from "./util.js";

const DEBTFILE = process.argv[2] || './debt.csv';
const SOLUTIONFILE = process.argv[3] || './solution.csv';

const LEDGER_SCALE = 1000;
const ROUNDING_MARGIN = 0.0000001;

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

    nodesBefore[from] = true;
    nodesBefore[to] = true;
    
    const edge = `${from} ${to}`;
    if (typeof graph[edge] === 'undefined') {
      graph[edge] = 0;
    }
    const scaledAmount = scale(amountStr, 'debt', LEDGER_SCALE, ROUNDING_MARGIN);
    graph[edge] += scaledAmount;
    numTrans++;
    totalAmount += scaledAmount;
  });

  let check = 0;
  Object.keys(graph).forEach(edge => {
    check += graph[edge];
  });
  if (check !== totalAmount) {
    throw new Error(`${check} != ${totalAmount}`);
  }
  console.log(`Imported ${numTrans} transactions between ${Object.keys(nodesBefore).length} accounts into ${Object.keys(graph).length} balances, total amount around ${Math.round(totalAmount / LEDGER_SCALE / 1000000)} million Sarafu`);
  let totalSolution = 0;
  let numSolution = 0;
  await readCsv(SOLUTIONFILE, ' ', (cells: string[]) => {
    // cells would be e.g. ['8', '5', '21', '3', '5.3']
    const amountStr = cells.pop();
    const scaledAmount = scale(amountStr, 'solution', LEDGER_SCALE, ROUNDING_MARGIN);
    const nodes = cells.concat(cells[0]);
    // nodes would now be e.g. ['8', '5', '21', '3', 8']
    let possible = true;
    for (let i = 0; i < nodes.length - 1; i++) {
      const edge = `${nodes[i]} ${nodes[i + 1]}`;
      if (graph[edge] < scaledAmount) {
        // console.log(`Netting agreement ${nodes.join(' ')} ${scaledAmount / LEDGER_SCALE} cannot be applied to edge ${edge} with balance ${graph[edge] / LEDGER_SCALE}, ${graph[edge]} < ${scaledAmount}`);
        possible = false;
      }
      if (typeof graph[edge] === 'undefined') {
        console.log(`Unknown edge in loop ${nodes.join('->')}, '${edge}'`);
        // console.log(`Netting agreement ${nodes.join(' ')} ${scaledAmount / LEDGER_SCALE} cannot be applied to edge ${edge} with balance ${graph[edge] / LEDGER_SCALE}, ${graph[edge]} < ${scaledAmount}`);
        possible = false;
      }
    }
    if (possible) {
      numSolution++;
      totalSolution += (nodes.length - 1) * scaledAmount;
      for (let i = 0; i < nodes.length - 1; i++) {
        const edge = `${nodes[i]} ${nodes[i + 1]}`;
        if (isNaN(graph[edge])) {
          throw new Error(`have NaN balance for edge ${edge}`);
        }
        graph[edge] -= scaledAmount;
        if (isNaN(graph[edge])) {
          throw new Error(`got NaN after substracting ${scaledAmount}`);
        }
      }
    }
  });

  check = 0;
  Object.keys(graph).forEach(edge => {
    check += graph[edge];
  });
  if (check + totalSolution !== totalAmount) {
    throw new Error(`${check} + ${totalSolution} != ${totalAmount}`);
  }
  console.log(`Solution removed around ${Math.round(totalSolution / LEDGER_SCALE / 1000000)} million Sarafu debt in ${numSolution} cycles`);
  console.log(`That is around ${Math.round(100 * totalSolution / totalAmount)} percent, leaving around ${Math.round(check / LEDGER_SCALE / 1000000)} million Sarafu`);
  console.log(`Done`);
}

// ...
run();