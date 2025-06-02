import { createInterface } from 'readline';
import { createReadStream} from 'fs';

async function readCsv(filename, delimiter, callback) {
  return new Promise((resolve, reject) => {
    try {
      const lineReader = createInterface({
        input: createReadStream(filename),
      });
      lineReader.on('line', function (line) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        callback(line.split(delimiter));
      });
     
      lineReader.on('close', function () {
        resolve();
      });
    } catch (e) {
      reject(e);
    }
  });
}

const balances = {};
await readCsv('./one-loop.csv', ',', (cells) => {
  const [ id,_timeset,_transfer_subtype,source,target,_weight,_token_name,_token_address ] = cells;
  if (typeof balances[source] === 'undefined') { balances[source] = {}; }
  if (typeof balances[source][target] === 'undefined') { balances[source][target] = []; }
  balances[source][target].push(parseInt(id));
});
console.log(JSON.stringify(balances, null, 2));
// Object.keys(balances).map(key => {
//   const parts = key.split(' ');
//   console.log(`${parts[0]},${parts[0]},${balances[key]}`);
// })

let cursor = Object.keys(balances)[0];
const start = cursor;
do {
  if (typeof balances[cursor] === 'undefined') {
    throw new Error(`no way forward from ${cursor}`);
  }
  const exits = Object.keys(balances[cursor]);
  if (exits.length !== 1) {
    throw new Error(`Don't know how to exit from ${cursor}`);
  }
  const exit = exits[0];
  console.log(cursor, exit, JSON.stringify(balances[cursor][exit]));
  cursor = exit;
} while(cursor !== start);