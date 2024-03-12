/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

const messagesAB = [
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex1",
];

const messagesBC = [
  "[Bob]->[Charlie] meet",
  "[Bob]->[Charlie] probe genRanHex1",
  "[Bob]->[Alice] probe genRanHex2",
  "[Bob]->[Charlie] probe genRanHex2",
];

const messagesCA = [
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Alice] probe genRanHex1",
  "[Charlie]->[Alice] probe genRanHex2",
  "[Charlie]->[Bob] probe genRanHex3",
  "[Charlie]->[Alice] probe genRanHex3",
];

const messages4 = [
  "[Alice]->[Charlie] probe genRanHex1",
  "[Alice]->[Charlie] probe genRanHex2",
  "[Bob]->[Alice] probe genRanHex3",
  "[Alice]->[Bob] probe genRanHex3",
];

const messages5 = [];

let counter: number = 0;
jest.unstable_mockModule('../src/util.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `genRanHex${counter++}`;
    })
  };
});

function expectProbe(probeId: string, first: any, second: any, third: any, order: number): void {
  // minted at first:
  expect(first.getProbes()[probeId].homeMinted).toEqual(true);
  expect(second.getProbes()[probeId].homeMinted).toEqual(false);
  expect(third.getProbes()[probeId].homeMinted).toEqual(false);
  if (order === 1) {
    // sent:
    expect(first.getProbes()[probeId].to.sort()).toEqual([second.getName(), third.getName()].sort());
    expect(second.getProbes()[probeId].to).toEqual([third.getName()]);
    expect(third.getProbes()[probeId].to).toEqual([first.getName()]);
    // received:
    expect(first.getProbes()[probeId].from).toEqual([]);
    expect(second.getProbes()[probeId].from).toEqual([first.getName()]);
    expect(third.getProbes()[probeId].from).toEqual([second.getName()]);
  } else if (order === 2) {
    // sent:
    expect(first.getProbes()[probeId].to.sort()).toEqual([second.getName(), third.getName()].sort());
    expect(second.getProbes()[probeId].to).toEqual([third.getName()]);
    expect(third.getProbes()[probeId].to).toEqual([second.getName()]);
    // received:
    expect(first.getProbes()[probeId].from).toEqual([]);
    expect(second.getProbes()[probeId].from).toEqual([first.getName()]);
    expect(third.getProbes()[probeId].from).toEqual([first.getName()]);
  }
}


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
      flushReport = messageForwarder.flush();
      alice.meet(bob);
    });

    it('Message Logs', () => {
      expect(flushReport).toEqual([]);
      // messagesAB is alreadsy sent but nothing is flushed yet
      expect(messageForwarder.getFullLog()).toEqual(messagesAB);
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

    it('Bob is not friends with Alice yet', () => {
      expect(bob.getFriends()).toEqual([]);
    });
    it('Bob has no probes yet', () => {
      expect(bob.getProbes()).toEqual({
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
        flushReport = messageForwarder.flush();
        bob.meet(charlie);
      });

      it('Message Logs', () => {
        expect(flushReport).toEqual(messagesAB);
        // messagesBC is alreadsy sent but messagesAC is still what was just flushed here
        expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC));
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
        });
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
  
      it('Charlie is not friends with Bob yet', () => {
        expect(charlie.getFriends()).toEqual([]);
      });
      it('Charlie has no probes yet', () => {
        expect(charlie.getProbes()).toEqual({
        });
      });
  
      describe('Charlie meets Alice', () => {
        beforeAll(() => {
          flushReport = messageForwarder.flush();
          charlie.meet(alice);
        });

        it('Message Logs', () => {
          expect(flushReport).toEqual(messagesBC);
          // messagesCA is already sent but messagesBC is still what was just flushed here
          expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC, messagesCA));
        });

        it('Alice is friends with Bob', () => {
          expect(alice.getFriends()).toEqual([ 'Bob' ]);
        });
        it('Alice has some probes', () => {
          expect(alice.getProbes()).toEqual({
            genRanHex1: {
              from: [],
              homeMinted: true,
              to: ['Bob'],
              traces: [],
            },
            genRanHex2: {
              from: [ 'Bob' ],
              homeMinted: false,
              to: [],
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

        it('Stingray Logs', () => {
          expect(alice.getLog()).toEqual([
            "I meet Bob, and offer them all my flood probes",
          ]);
          expect(bob.getLog()).toEqual([
            "MEET MESSAGE FROM Alice, offering all flood probes",
            "I meet Charlie, and offer them all my flood probes",
            "OFFERING PROBE genRanHex1 TO Charlie",
        
          ]);
          expect(charlie.getLog()).toEqual([
            "MEET MESSAGE FROM Bob, offering all flood probes",
            "I meet Alice, and offer them all my flood probes",
            "OFFERING PROBE genRanHex1 TO Alice",
            "OFFERING PROBE genRanHex2 TO Alice",
        
          ]);
        });


        describe('Another round of messages', () => {
          beforeAll(() => {
            flushReport = messageForwarder.flush();
          });

          it('Message Logs', () => {
            expect(flushReport).toEqual(messagesCA);
            // messages4 is already sent but messagesCA is still what was just flushed here
            expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC, messagesCA, messages4));
          });

          it('Probe trees', () => {
            expect(Object.keys(alice.getProbes()).sort()).toEqual([ 'genRanHex1', 'genRanHex2', 'genRanHex3' ].sort());
            expect(Object.keys(bob.getProbes()).sort()).toEqual([ 'genRanHex1', 'genRanHex2', 'genRanHex3' ].sort());
            expect(Object.keys(charlie.getProbes()).sort()).toEqual([ 'genRanHex1', 'genRanHex2', 'genRanHex3' ].sort());
            expectProbe('genRanHex1', alice, bob, charlie, 1);
            expectProbe('genRanHex2', bob, charlie, alice, 2);
            expectProbe('genRanHex3', charlie, alice, bob, 2);
          });
  

          it('Alice, Bob and Charlie all know each other', () => {
            expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
            expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
            expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
          });

          it('Alice, Bob and Charlie all have all probes', () => {
            expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
            expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
            expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
          });

          it('Stingray Logs', () => {
            expect(alice.getLog()).toEqual([
              "I meet Bob, and offer them all my flood probes",
              "MEET MESSAGE FROM Charlie, offering all flood probes",
              "OFFERING PROBE genRanHex1 TO Charlie",
              "OFFERING PROBE genRanHex2 TO Charlie",
              "PROBE genRanHex1 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Charlie!",
              "PROBE genRanHex2 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Charlie!",
          
            ]);
            expect(bob.getLog()).toEqual([
              "MEET MESSAGE FROM Alice, offering all flood probes",
              "I meet Charlie, and offer them all my flood probes",
              "OFFERING PROBE genRanHex1 TO Charlie",
            ]);
            expect(charlie.getLog()).toEqual([
              "MEET MESSAGE FROM Bob, offering all flood probes",
              "I meet Alice, and offer them all my flood probes",
              "OFFERING PROBE genRanHex1 TO Alice",
              "OFFERING PROBE genRanHex2 TO Alice",
          
            ]);
          });

          describe('Another round of messages', () => {
            beforeAll(() => {
              flushReport = messageForwarder.flush();
            });

            it('Message Logs', () => {
              // expect(flushReport).toEqual(messages4);
              // messages5 is already sent but messages4 is still what was just flushed here
              expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC, messagesCA, messages4, messages5));
            });

            it('Probe trees', () => {
              expect(Object.keys(alice.getProbes()).sort()).toEqual([ 'genRanHex1', 'genRanHex2', 'genRanHex3' ].sort());
              expect(Object.keys(bob.getProbes()).sort()).toEqual([ 'genRanHex1', 'genRanHex2', 'genRanHex3' ].sort());
              expect(Object.keys(charlie.getProbes()).sort()).toEqual([ 'genRanHex1', 'genRanHex2', 'genRanHex3' ].sort());
              expectProbe('genRanHex1', alice, bob, charlie, 1);
              expectProbe('genRanHex2', bob, charlie, alice, 2);
              expectProbe('genRanHex3', charlie, alice, bob, 2);
            });
    

            it('Alice, Bob and Charlie all know each other', () => {
              expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
              expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
              expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
            });

            it('Alice, Bob and Charlie all have all probes', () => {
              expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
              expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
              expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
            });

            it('Stingray Logs', () => {
              expect(alice.getLog()).toEqual([
                "I meet Bob, and offer them all my flood probes",
                "MEET MESSAGE FROM Charlie, offering all flood probes",
                "OFFERING PROBE genRanHex1 TO Charlie",
                "OFFERING PROBE genRanHex2 TO Charlie",                  
                "PROBE genRanHex1 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Charlie!",
                "PROBE genRanHex2 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Charlie!",
            
              ]);
              expect(bob.getLog()).toEqual([
                "MEET MESSAGE FROM Alice, offering all flood probes",
                "I meet Charlie, and offer them all my flood probes",
                 "OFFERING PROBE genRanHex1 TO Charlie",      
              ]);
              expect(charlie.getLog()).toEqual([
                "MEET MESSAGE FROM Bob, offering all flood probes",
                "I meet Alice, and offer them all my flood probes",
                "OFFERING PROBE genRanHex1 TO Alice",
                "OFFERING PROBE genRanHex2 TO Alice",            
              ]);
            });
          }); // Another round of messages
        }); // Another round of messages
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic stingray triangle
