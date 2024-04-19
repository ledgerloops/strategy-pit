/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';
import { readFileSync, writeFileSync } from 'fs';

const TESTNET_CSV = '__tests__/fixtures/testnet.csv';
const NUM_ROUNDS = 100000;
// const NUM_NODES = 100;
const TEST_NAME = `batched-giraffe-testnet-csv`;
const JSON_FILE = `__tests__/fixtures/${TEST_NAME}.json`;
const PUML_FILE = `__tests__/fixtures/${TEST_NAME}.puml`;

let counter: number = 0;
jest.unstable_mockModule('../src/genRanHex.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `genRanHex${counter++}`;
    })
  };
});

describe(`${TEST_NAME} - until the music stops`, () => {
  // let Giraffe: unknown;
  const nodes: { [key: string]: any } = {};
  let networkSimulator: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { BatchedNetworkSimulator, Giraffe } = await import('../src/main.js');
    networkSimulator = new BatchedNetworkSimulator();
    const data = readFileSync(TESTNET_CSV, 'utf8')
    const lines = data.split('\n').map(line => {
      const [ from, to ] = line.split(' ')
      return { from, to }
    }).filter(line => line.from !== 'from' && line.from !== '');
    lines.forEach(async line => {
      if (typeof nodes[line.from] === 'undefined') {
        // console.log("Adding node", line.from);
        nodes[line.from] = new Giraffe(line.from);
        networkSimulator.addNode(line.from, nodes[line.from]);
      }
      if (typeof nodes[line.to] === 'undefined') {
        // console.log("Adding node", line.to);
        nodes[line.to] = new Giraffe(line.to);
        networkSimulator.addNode(line.to, nodes[line.to]);
      }
      // console.log("Meeting", JSON.stringify(line.from), JSON.stringify(line.to));
      await nodes[line.from].meet(line.to);
      flushReport = await networkSimulator.flush();
    });
    let counter = 0;
    do {
      flushReport = await networkSimulator.flush();
    } while ((flushReport.length > 0) && (counter++ < NUM_ROUNDS));
  });
  it('Probes are not echoed back to the sender', () => {
    const probeLogs = networkSimulator.getProbeLogs();
    for (const probeId in probeLogs) {
      const seen = [ probeId ];
      for (const entry of probeLogs[probeId]) {
        const fromTo = entry.split('->');
        if (fromTo.length < 2) continue;
        const toFrom = [ fromTo[1], fromTo[0]];
        seen.push(fromTo.toString());
        expect(seen).not.toContain(toFrom.toString());
      }
      // console.log(probeId, seen);
    }
  });

  describe('Message Logs match exported fixture from last run', () => {
    it('Message Logs', () => {
      let expected = {};
      try {
        const fileContents = readFileSync(JSON_FILE, 'utf8');
        expected = JSON.parse(fileContents);
      } catch (err) {
        // file was not found or was unreadable
      }
      const actual = {
        full: networkSimulator.getFullLog(),
        probes: networkSimulator.getProbeLogs()
      };
      Object.keys(nodes).forEach((nodeId) => {
        actual[nodeId] = {
          debugLog: nodes[nodeId].getDebugLog(),
          loopsFound: nodes[nodeId].getLoops(),
        };
      });
      writeFileSync(JSON_FILE, JSON.stringify(actual, null, 2) + '\n');
      expect(actual).toEqual(expected);
    });
  });

  describe('Sequence Diagram matches exported fixture from last run', () => {
    it('Message Logs', () => {
      let expected = {};
      try {
        expected = readFileSync(PUML_FILE, 'utf8');
      } catch (err) {
        // file was not found or was unreadable
      }
      const actual = networkSimulator.getPlantUml();
      writeFileSync(PUML_FILE, actual);
      expect(actual).toEqual(expected);
    });
  });
});
