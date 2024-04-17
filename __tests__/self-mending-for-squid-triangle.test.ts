/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';
import { readFileSync, writeFileSync } from 'fs';

let counter: number = 0;
jest.unstable_mockModule('../src/genRanHex.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `genRanHex${counter++}`;
    })
  };
});

describe('Basic Squid Triangle - until the music stops', () => {
  // let Squid: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let messageForwarder: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { Squid, BatchedMessageForwarder } = await import('../src/main.js');
    messageForwarder = new BatchedMessageForwarder();
    alice = new Squid('Alice', messageForwarder);
    bob = new Squid('Bob', messageForwarder);
    charlie = new Squid('Charlie', messageForwarder);
    flushReport = await messageForwarder.flush();
    alice.meet(bob);
    flushReport = await messageForwarder.flush();
    bob.meet(charlie);
    flushReport = await messageForwarder.flush();
    charlie.meet(alice);
    do {
      flushReport = await messageForwarder.flush();
    } while (flushReport.length > 0);
  });

  describe('Message Logs match exported fixture from last run', () => {
    it('Message Logs', () => {
      const expected = JSON.parse(readFileSync('__tests__/fixtures/batched-squid-triangle.json', 'utf8'));
      const actual = {
        full: messageForwarder.getFullLog(),
        probes: messageForwarder.getProbeLogs(),
      };
      writeFileSync('__tests__/fixtures/batched-squid-triangle.json', JSON.stringify(actual, null, 2) + '\n');
      expect(actual).toEqual(expected);
    });
  });
});
