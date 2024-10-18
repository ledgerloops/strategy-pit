import { writeFile, appendFile } from 'node:fs/promises';
import { readCsv } from "./readCsv.js";
import { scale } from "./util.js";

const DEBTFILE = process.argv[2] || './debt.csv';
const FLOWFILE = process.argv[3] || './flow.csv';
const OUTFILE = process.argv[4] || './mcf-out.csv';

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
  await readCsv(FLOWFILE, ' ', (cells: string[]) => {    // cells would be e.g. ['8', '5', '21', '3', '5.3']
    const amountStr = cells.pop();
    const scaledAmount = scale(amountStr, 'flow', LEDGER_SCALE, ROUNDING_MARGIN);
    const [from, to] = cells;
    const edge = `${from} ${to}`;
    if (graph[edge] < scaledAmount) {
      throw new Error(`cannot substract ${scaledAmount} from ${graph[edge]}`);
    }
    graph[edge] -= scaledAmount;
  });
  await writeFile(OUTFILE, '');
  await Promise.all(Object.keys(graph).map((edge: string) => appendFile(OUTFILE, `${edge} ${graph[edge]}\n`)));
}

// ...
run();