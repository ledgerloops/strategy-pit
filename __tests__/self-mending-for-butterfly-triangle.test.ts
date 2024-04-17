/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';
import { readFileSync, writeFileSync } from 'fs';

let counter: number = 0;
jest.unstable_mockModule('../src/util.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `genRanHex${counter++}`;
    })
  };
});

describe('Basic Butterfly Triangle - until the music stops', () => {
  // let Butterfly: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let messageForwarder: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { Butterfly, BatchedMessageForwarder } = await import('../src/main.js');
    messageForwarder = new BatchedMessageForwarder();
    alice = new Butterfly('Alice', messageForwarder);
    bob = new Butterfly('Bob', messageForwarder);
    charlie = new Butterfly('Charlie', messageForwarder);
    flushReport = await messageForwarder.flush();
    await alice.meet(bob);
    flushReport = await messageForwarder.flush();
    await bob.meet(charlie);
    flushReport = await messageForwarder.flush();
    await charlie.meet(alice);
    let counter = 0;
    do {
      flushReport = await messageForwarder.flush();
    } while ((flushReport.length > 0) && (counter++ < 10));
  });
  it('Probes are not echoed back to the sender', () => {
    const probeLogs = messageForwarder.getProbeLogs();
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
      const expected = JSON.parse(readFileSync('__tests__/fixtures/batched-butterfly-triangle.json', 'utf8'));
      const actual = {
        full: messageForwarder.getFullLog(),
        probes: messageForwarder.getProbeLogs(),
        alice: {
          debugLog: alice.debugLog,
          loopsFound: alice.loopsFound,
        },
        bob: {
          debugLog: bob.debugLog,
          loopsFound: bob.loopsFound,
        },
        charlie: {
          debugLog: charlie.debugLog,
          loopsFound: charlie.loopsFound,
        },
      };
      writeFileSync('__tests__/fixtures/batched-butterfly-triangle.json', JSON.stringify(actual, null, 2) + '\n');
      expect(actual).toEqual(expected);
    });
  });
});
