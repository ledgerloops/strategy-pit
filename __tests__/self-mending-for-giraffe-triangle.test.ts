/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';
import { readFileSync, writeFileSync } from 'fs';

const NUM_ROUNDS = 100;
const TEST_NAME = 'batched-giraffe-triangle';
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
  let alice: any;
  let bob: any;
  let charlie: any;
  let networkSimulator: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { BatchedNetworkSimulator, Giraffe } = await import('../src/main.js');
    networkSimulator = new BatchedNetworkSimulator();
    alice = new Giraffe('Alice');
    networkSimulator.addNode('Alice', alice);
    bob = new Giraffe('Bob');
    networkSimulator.addNode('Bob', bob);
    charlie = new Giraffe('Charlie');
    networkSimulator.addNode('Charlie', charlie);
    flushReport = await networkSimulator.flush();
    await alice.meet('Bob');
    // suppressing probe creation in meet of Bob with Charlie and Charlie with Alice:
    await bob.meet('Charlie', false);
    await charlie.meet('Alice', false);
    // flushReport = await networkSimulator.flush();
    // await bob.meet('Charlie');
    // flushReport = await networkSimulator.flush();
    // await charlie.meet('Alice');
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
        probes: networkSimulator.getProbeLogs(),
        alice: {
          debugLog: alice.getDebugLog(),
          loopsFound: alice.getLoops(),
        },
        bob: {
          debugLog: bob.getDebugLog(),
          loopsFound: bob.getLoops(),
        },
        charlie: {
          debugLog: charlie.getDebugLog(),
          loopsFound: charlie.getLoops(),
        },
      };
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
