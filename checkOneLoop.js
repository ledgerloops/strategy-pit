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

const graph = {};
await readCsv('./one-loop.csv', ',', (cells) => {
  const [ _id,_timeset, transfer_subtype,source,target,weight,_token_name,_token_address ] = cells;
  if (typeof graph[source] === 'undefined') { graph[source] = {}; }
  if (typeof graph[source][target] === 'undefined') { graph[source][target] = 0; }
  graph[source][target] += parseFloat(weight);
});
console.log(JSON.stringify(graph, null, 2));