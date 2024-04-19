/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';
import { readFileSync, writeFileSync } from 'fs';

const NUM_ROUNDS = 100000;
const NUM_NODES = 100;
const TEST_NAME = `batched-giraffe-circle-${NUM_NODES}`;
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
    for (let i = 0; i < NUM_NODES; i++) {
      nodes[`n${i}`] = new Giraffe(`n${i}`);
      networkSimulator.addNode(`n${i}`, nodes[`n${i}`]);
    }
    for (let i = 0; i < NUM_NODES - 1; i++) {
      flushReport = await networkSimulator.flush();
      await nodes[`n${i}`].meet(`n${i+1}`);
    }
    await nodes[`n${NUM_NODES - 1}`].meet(`n0`);
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
      for (let i=0; i<NUM_NODES; i++) {
        actual[`n${i}`] = {
          debugLog: nodes[`n${i}`].getDebugLog(),
          loopsFound: nodes[`n${i}`].getLoops(),
        };
      }
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
