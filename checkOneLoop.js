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

const exits = {};
await readCsv('./one-loop.csv', ',', (cells) => {
  const [ _id,_timeset, transfer_subtype,source,target,weight,_token_name,_token_address ] = cells;
  if (typeof exits[source] === 'undefined') {
    exits[source] = { id: _id, to: target, weight };
  }
});
let cursor = Object.keys(exits)[0];
const start = cursor;
do {
  if (typeof exits[cursor] === 'undefined') {
    throw new Error(`no way forward from ${cursor}`);
  }
  console.log(exits[cursor].id, cursor, exits[cursor].to, exits[cursor].weight);
  cursor = exits[cursor].to;
} while(cursor !== start);