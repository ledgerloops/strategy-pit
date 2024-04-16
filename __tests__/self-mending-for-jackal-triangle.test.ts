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

describe('Basic Jackal Triangle - until the music stops', () => {
  // let Jackal: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let messageForwarder: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { Jackal, BatchedMessageForwarder } = await import('../src/main.js');
    messageForwarder = new BatchedMessageForwarder();
    alice = new Jackal('Alice', messageForwarder);
    bob = new Jackal('Bob', messageForwarder);
    charlie = new Jackal('Charlie', messageForwarder);
    flushReport = messageForwarder.flush();
    alice.meet(bob);
    flushReport = messageForwarder.flush();
    bob.meet(charlie);
    flushReport = messageForwarder.flush();
    charlie.meet(alice);
    do {
      flushReport = messageForwarder.flush();
    } while (flushReport.length > 0);
  });

  describe('Message Logs match exported fixture from last run', () => {
    it('Message Logs', () => {
      const expected = JSON.parse(readFileSync('__tests__/fixtures/batched-jackal-triangle.json', 'utf8'));
      const actual = {
        full: messageForwarder.getFullLog(),
        probes: messageForwarder.getProbeLogs(),
      };
      writeFileSync('__tests__/fixtures/batched-jackal-triangle.json', JSON.stringify(actual, null, 2) + '\n');
      expect(actual).toEqual(expected);
    });
  });
});
