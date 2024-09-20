import { readFileSync, writeFileSync } from 'fs';

const SARAFU_CSV = '../Sarafu2021_UKdb_submission/sarafu_xDAI/sarafu_txns_20200125-20210615.csv';
const TESTNET_CSV = './__tests__/fixtures/testnet-sarafu.csv';
const NUM_LINES_TO_USE = 1000;
const nodes = {};
let counter = 0;
const data = readFileSync(SARAFU_CSV, 'utf8');
const out = [];
const lines = data.split('\n').slice(1, NUM_LINES_TO_USE).map(line => {
  const [ id,timeset, transfer_subtype,source,target,weight,_token_name,_token_address ] = line.split(',');
  // console.log({ id, timeset, transfer_subtype, source, target, weight });
  return { id, timeset, transfer_subtype, source, target, weight };
}).filter(line => line.id !== 'id' && line.id !== '');
lines.forEach(async line => {
  if (typeof nodes[line.source] === 'undefined') {
    nodes[line.source] = counter++;
  }
  if (typeof nodes[line.target] === 'undefined') {
    nodes[line.target] = counter++;
  }
  out.push(`${nodes[line.source]} ${nodes[line.target]} ${line.weight}`);
});
writeFileSync(TESTNET_CSV, out.join('\n'));