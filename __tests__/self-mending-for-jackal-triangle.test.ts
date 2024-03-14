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

// function expectProbe(probeId: string, first: any, second: any, third: any, order: number): void {
//   // minted at first:
//   expect(first.getProbes()[probeId].homeMinted).toEqual(true);
//   expect(second.getProbes()[probeId].homeMinted).toEqual(false);
//   expect(third.getProbes()[probeId].homeMinted).toEqual(false);
//   if (order === 1) {
//     // sent:
//     expect(first.getProbes()[probeId].to.sort()).toEqual([second.getName(), third.getName()].sort());
//     expect(second.getProbes()[probeId].to).toEqual([third.getName()]);
//     expect(third.getProbes()[probeId].to).toEqual([first.getName()]);
//     // received:
//     expect(first.getProbes()[probeId].from).toEqual([]);
//     expect(second.getProbes()[probeId].from).toEqual([first.getName()]);
//     expect(third.getProbes()[probeId].from).toEqual([second.getName()]);
//   } else if (order === 2) {
//     // sent:
//     expect(first.getProbes()[probeId].to.sort()).toEqual([second.getName(), third.getName()].sort());
//     expect(second.getProbes()[probeId].to).toEqual([third.getName()]);
//     expect(third.getProbes()[probeId].to).toEqual([second.getName()]);
//     // received:
//     expect(first.getProbes()[probeId].from).toEqual([]);
//     expect(second.getProbes()[probeId].from).toEqual([first.getName()]);
//     expect(third.getProbes()[probeId].from).toEqual([first.getName()]);
//   }
// }

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
      const expected = JSON.parse(readFileSync('__tests__/fixtures/batched-jackal-triangle.log', 'utf8'));
      writeFileSync('__tests__/fixtures/batched-jackal-triangle.log', JSON.stringify(messageForwarder.getFullLog(), null, 2));
      expect(messageForwarder.getFullLog()).toEqual(expected);
    });
  });
});
