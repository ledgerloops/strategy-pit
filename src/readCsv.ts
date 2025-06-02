import { createInterface } from 'readline';
import { createReadStream} from 'fs';

const filter = '19897 23610 21257 20069 22568 27857 27867 27868 27869 27865 27872 21250 21549 9410 21925 22969 22100 22112 21523 24137 20484 22590 22103 21750 27561 21770 21811 29414 19882 20467 24126 20493 22591 22102 21768 27560 24105 22579 22105 21745 27562 21429 21822 29406 19855 22578 22110 21520 27564 21420 21833 19585 21851 22569 22107 21743 27563 21426 21823 23620 21253 21280 33361 31417 31376 31420 31382 20475 19939 29405'.split(' ');

export async function readCsv(filename: string, delimiter: string, callback: (cells: string[]) => void): Promise<void> {
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
export async function readSarafuCsv(filename: string, callback: (from: string, to: string, amount: number) => void): Promise<void> {
  const nodes: {
    [origId: string]: string
  } = {};
  let counter = 0;
  return readCsv(filename, ',', (cells: string[]) => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const [ _id,_timeset, transfer_subtype,source,target,weight,_token_name,_token_address ] = cells;
    if (typeof nodes[source] === 'undefined') {
      nodes[source] = (counter++).toString();
    }
    if (typeof nodes[target] === 'undefined') {
      nodes[target] = (counter++).toString();
    }
    if (transfer_subtype === 'STANDARD') {
      const sourceIndex = filter.indexOf(nodes[source]);
      const targetIndex = filter.indexOf(nodes[target]);
      
      if ((sourceIndex !== -1) && ((sourceIndex === targetIndex - 1) || (targetIndex === 0 && sourceIndex === filter.length - 1))) {
        console.log(cells.join(','));
      }
      callback(nodes[source], nodes[target], parseFloat(weight));
    }
  });
}
