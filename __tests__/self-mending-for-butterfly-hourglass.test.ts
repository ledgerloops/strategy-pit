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

describe('Basic Butterfly Hourglass - until the music stops', () => {
  // let Butterfly: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let dave: any;
  let edward: any;
  let messageForwarder: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { Butterfly, BatchedMessageForwarder } = await import('../src/main.js');
    messageForwarder = new BatchedMessageForwarder();
    alice = new Butterfly('Alice', messageForwarder);
    bob = new Butterfly('Bob', messageForwarder);
    charlie = new Butterfly('Charlie', messageForwarder);
    dave = new Butterfly('Dave', messageForwarder);
    edward = new Butterfly('Edward', messageForwarder);
    flushReport = await messageForwarder.flush();
    await alice.meet(bob);
    flushReport = await messageForwarder.flush();
    await bob.meet(charlie);
    flushReport = await messageForwarder.flush();
    await charlie.meet(alice);
    flushReport = await messageForwarder.flush();
    await alice.meet(dave);
    flushReport = await messageForwarder.flush();
    await dave.meet(edward);
    flushReport = await messageForwarder.flush();
    await edward.meet(alice);
    do {
      flushReport = await messageForwarder.flush();
    } while (flushReport.length > 0);
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
      let expected = {};
      try {
        const fileContents = readFileSync('__tests__/fixtures/batched-butterfly-hourglass.json', 'utf8');
        expected = JSON.parse(fileContents);
      } catch (err) {
        // file was not found or was unreadable
      }
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
        dave: {
          debugLog: dave.debugLog,
          loopsFound: dave.loopsFound,
        },
        edward: {
          debugLog: edward.debugLog,
          loopsFound: edward.loopsFound,
        },
      };
      writeFileSync('__tests__/fixtures/batched-butterfly-hourglass.json', JSON.stringify(actual, null, 2) + '\n');
      expect(actual).toEqual(expected);
    });
  });
});
