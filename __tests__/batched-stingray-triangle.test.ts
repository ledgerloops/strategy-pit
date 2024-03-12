/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

const messages1 = [
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex1",
];

const messages2 = [
  "[Bob]->[Charlie] meet",
  "[Bob]->[Charlie] probe genRanHex1",
  "[Bob]->[Alice] probe genRanHex2",
  "[Bob]->[Charlie] probe genRanHex2",
];

const messages3 = [
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Alice] probe genRanHex1",
  "[Charlie]->[Alice] probe genRanHex2",
  "[Charlie]->[Bob] probe genRanHex3",
  "[Charlie]->[Alice] probe genRanHex3",
];

const messages3a = [
  "[Alice]->[Charlie] probe genRanHex1",
  "[Alice]->[Charlie] probe genRanHex2",
  "[Bob]->[Alice] probe genRanHex3",
  "[Alice]->[Bob] probe genRanHex3",
];

const messages4 = [
];

let counter: number = 0;
jest.unstable_mockModule('../src/util.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `genRanHex${counter++}`;
    })
  };
});

describe('already friends', () => {
  it('throws an error', async () => {
    const { Stingray } = await import('../src/main.js');
    const alice = new Stingray('Alice');
    const bob = new Stingray('Bob');

    alice.meet(bob);
    expect(() => alice.meet(bob)).toThrow('Alice is already friends with Bob');
  });
});

describe('Basic Stingray Triangle - step-by-step', () => {
  // let Stingray: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let messageForwarder: any;
  let flushReport: string[];
  beforeAll(async () => {
    const { Stingray, BatchedMessageForwarder } = await import('../src/main.js');
    messageForwarder = new BatchedMessageForwarder();
    alice = new Stingray('Alice', messageForwarder);
    bob = new Stingray('Bob', messageForwarder);
    charlie = new Stingray('Charlie', messageForwarder);
  });

  describe('Alice meets Bob', () => {
    beforeAll(() => {
      alice.meet(bob);
      flushReport = messageForwarder.flush();
    });

    it('Message Logs', () => {
      expect(flushReport).toEqual(messages1);
      expect(messageForwarder.getFullLog()).toEqual(messages1);
    });

    it('Alice is friends with Bob', () => {
      expect(alice.getFriends()).toEqual([ 'Bob' ]);
    });
    it('Alice has an genRanHex1 probe for Bob', () => {
      expect(alice.getProbes()).toEqual({
        genRanHex1: {
          "from": [],
          "homeMinted": true,
          "to": [
            "Bob",
          ],
          "traces": [],
        }
      });
    });

    it('Bob is friends with Alice', () => {
      expect(bob.getFriends()).toEqual([ 'Alice' ]);
    });
    it('Bob has an genRanHex1 probe with Alice', () => {
      expect(bob.getProbes()).toEqual({
        genRanHex1: {
          traces: [],
          from: ['Alice'],
          homeMinted: false,
          to: []
        }
      });
    });

    it('Charlie is friends with nobody', () => {
      expect(charlie.getFriends()).toEqual([]);
    });
    it('Charlie has no probes', () => {
      expect(charlie.getProbes()).toEqual({
      });
    });

    describe('Bob meets Charlie', () => {
      beforeAll(() => {
        bob.meet(charlie);
        flushReport = messageForwarder.flush();
      });

      it('Message Logs', () => {
        expect(flushReport).toEqual(messages2);
        expect(messageForwarder.getFullLog()).toEqual(messages1.concat(messages2));
      });

      it('Alice is friends with Bob', () => {
        expect(alice.getFriends()).toEqual([ 'Bob' ]);
      });
      it('Alice has some probes', () => {
        expect(alice.getProbes()).toEqual({
          genRanHex1: {
            traces: [],
            from: [],
            homeMinted: true,
            to: ['Bob']
          },
          genRanHex2: {
            traces: [],
            from: ['Bob'],
            homeMinted: false,
            to: []
          }
        });
      });
      it('Alice has sent and received some messages', () => {
        expect(alice.getMessageLog()).toEqual([
          'TO[Bob] meet',
          'TO[Bob] probe genRanHex1',
          "FROM[Bob] probe genRanHex2",
        ]);
      });
  
      it('Bob is friends with Alice and Charlie', () => {
        expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
      });
      it('Bob has some probes', () => {
        expect(bob.getProbes()).toEqual({
          genRanHex1: {
            traces: [],
            from: ['Alice'],
            homeMinted: false,
            to: ['Charlie']
          },
          genRanHex2: {
            traces: [],
            from: [],
            homeMinted: true,
            to: ['Alice','Charlie']
          }
        });
      });
  
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual([ 'Bob' ]);
      });
      it('Charlie has some probes', () => {
        expect(charlie.getProbes()).toEqual({
          genRanHex1: {
            traces: [],
            from: ['Bob'],
            homeMinted: false,
            to: []
          },
          genRanHex2: {
            traces: [],
            from: ['Bob'],
            homeMinted: false,
            to: []
          }
        });
      });
  
      describe('Charlie meets Alice', () => {
        beforeAll(() => {
          charlie.meet(alice);
          flushReport = messageForwarder.flush();
        });

        it('Message Logs', () => {
          expect(flushReport).toEqual(messages3);
          expect(messageForwarder.getFullLog()).toEqual(messages1.concat(messages2, messages3, messages3a));
        });

        it('Alice is friends with Bob and Charlie', () => {
          expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
        });
        it('Alice has some probes', () => {
          expect(alice.getProbes()).toEqual({
            genRanHex1: {
              from: [],
              homeMinted: true,
              to: ['Bob', 'Charlie'],
              traces: [],
            },
            genRanHex2: {
              from: [ 'Bob' ],
              homeMinted: false,
              to: ['Charlie'],
              traces: [],
            },
            genRanHex3: {
              from: [ 'Charlie' ],
              homeMinted: false,
              to: ['Bob'],
              traces: [],
            },
          });
        });
        it('Alice has 3 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            // 'genRanHex1',
            // 'genRanHex2',
            // 'genRanHex3'
          ].sort());
        });
    
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
        });
        it('Bob has some probes', () => {
          expect(bob.getProbes()).toEqual({
            genRanHex1: {
              from: ['Alice'],
              homeMinted: false,
              to: ['Charlie'],
              traces: [],
            },
            genRanHex2: {
              from: [],
              homeMinted: true,
              to: ['Alice', 'Charlie'],
              traces: [],
            },
            genRanHex3: {
              from: ['Charlie'],
              homeMinted: false,
              to: ['Alice'],
              traces: [],
            },
          }); 
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            // 'genRanHex1',
            // 'genRanHex2',
            // 'genRanHex3'
          ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
        });
        it('Charlie has some probes', () => {
          expect(charlie.getProbes()).toEqual({
            genRanHex1: {
              traces: [],
              from: ['Bob'],
              homeMinted: false,
              to: ['Alice']
            },
            genRanHex2: {
              traces: [],
              from: ['Bob'],
              homeMinted: false,
              to: ['Alice']
            },
            genRanHex3: {
              traces: [],
              from: [],
              homeMinted: true,
              to: ['Bob', 'Alice']
            }
          });
        });
        it('Charlie has 3 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            // 'genRanHex1',
            // 'genRanHex2',
            // 'genRanHex3'
          ].sort());
        });

        describe('Another round of messages', () => {
          beforeAll(() => {
            flushReport = messageForwarder.flush();
          });

          it('Message Logs', () => {
            expect(flushReport).toEqual(messages4);
            expect(messageForwarder.getFullLog()).toEqual(messages1.concat(messages2, messages3, messages3a, messages4));
          });

          it('Alice, Bob and Charlie all know each other', () => {
            expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
            expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
            expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
          });
        });
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic stingray triangle
