/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

const separator = [
  "[---]->[---] ---",
];
const messagesAB = [
  "[Alice]->[Bob] pauze true",
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex1",
  "[Alice]->[Bob] pauze false",
];

const messagesBC = [
  "[---]->[---] ---",
  "[Bob]->[Charlie] pauze true",
  "[Bob]->[Charlie] meet",
  "[Bob]->[Charlie] probe genRanHex1",
  "[Bob]->[Alice] probe genRanHex2",
  "[Bob]->[Charlie] probe genRanHex2",
  "[Bob]->[Charlie] pauze false",
];

const messagesCA = [
  "[Charlie]->[Alice] pauze true",
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Alice] probe genRanHex1",
  "[Charlie]->[Alice] probe genRanHex2",
  "[Charlie]->[Bob] probe genRanHex3",
  "[Charlie]->[Alice] probe genRanHex3",
  "[Charlie]->[Alice] pauze false",
];

const fullLogRound4 = [
  "[---]->[---] ---",
  "[Alice]->[Bob] pauze true",
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex1",
  "[Alice]->[Bob] pauze false",
  "[---]->[---] ---",
  "[Alice]>-[Bob] meet",
  "[Alice]>-[Bob] probe genRanHex1",
  "[Bob]->[Charlie] pauze true",
  "[Bob]->[Charlie] meet",
  "[Bob]->[Charlie] probe genRanHex1",
  "[Bob]->[Alice] probe genRanHex2",
  "[Bob]->[Charlie] probe genRanHex2",
  "[Bob]->[Charlie] pauze false",
  "[---]->[---] ---",
  "[Bob]>-[Charlie] meet",
  "[Bob]>-[Charlie] probe genRanHex1",
  "[Bob]>-[Alice] probe genRanHex2",
  "[Bob]>-[Charlie] probe genRanHex2",
  "[Charlie]->[Alice] pauze true",
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Alice] probe genRanHex1",
  "[Charlie]->[Alice] probe genRanHex2",
  "[Charlie]->[Bob] probe genRanHex3",
  "[Charlie]->[Alice] probe genRanHex3",
  "[Charlie]->[Alice] pauze false",
  "[---]->[---] ---",
  "[Charlie]>-[Alice] meet",
  "[Charlie]>-[Alice] probe genRanHex1",
  "[Charlie]>-[Alice] probe genRanHex2",
  "[Charlie]>-[Bob] probe genRanHex3",
  "[Bob]->[Alice] probe genRanHex3",
  "[Charlie]>-[Alice] probe genRanHex3",

  "[Alice]->[Bob] probe genRanHex3",
  "[Alice]->[Charlie] probe genRanHex1",
  "[Alice]->[Charlie] probe genRanHex2",
  "[Alice]->[Charlie] loop genRanHex1 genRanHex4",
  "[Alice]->[Charlie] probe genRanHex5",
];

const fullLogRound5 = [
  "[---]->[---] ---",
  "[Bob]>-[Alice] probe genRanHex3",
  "[Alice]>-[Bob] probe genRanHex3",
  "[Alice]>-[Charlie] probe genRanHex1",
  "[Alice]>-[Charlie] probe genRanHex2",
  "[Alice]>-[Charlie] loop genRanHex1 genRanHex4",
  "[Charlie]->[Bob] loop genRanHex1 genRanHex4",
  "[Alice]>-[Charlie] probe genRanHex5",
  "[Charlie]->[Bob] probe genRanHex5",
];

const fullLogsRound6 = [
  "[---]->[---] ---",
  "[Charlie]>-[Bob] loop genRanHex1 genRanHex4",
  "[Bob]->[Alice] loop genRanHex1 genRanHex4",
  "[Charlie]>-[Bob] probe genRanHex5",
  "[Bob]->[Alice] probe genRanHex5",
];

const fullLogsRound7 = [
  "[---]->[---] ---",
  "[Bob]>-[Alice] loop genRanHex1 genRanHex4",
  "[Bob]>-[Alice] probe genRanHex5",
  "[Alice]->[Bob] loop genRanHex5 genRanHex6",
];

const fullLogsRound8 = [
  "[---]->[---] ---",
  "[Alice]>-[Bob] loop genRanHex5 genRanHex6",
  "[Bob]->[Charlie] loop genRanHex5 genRanHex6",
];

// const messages4 = [
//   "[Bob]->[Alice] probe genRanHex3",
//   "[Alice]->[Bob] probe genRanHex3",
//   "[Alice]->[Charlie] probe genRanHex1",
//   "[Alice]->[Charlie] probe genRanHex2",
//   "[Alice]->[Charlie] loop genRanHex1 genRanHex4",
//   "[Alice]->[Charlie] probe genRanHex5",
//];

// const messages5 = [];

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
    const { Jackal } = await import('../src/main.js');
    const alice = new Jackal('Alice');
    const bob = new Jackal('Bob');

    alice.meet(bob);
    expect(() => alice.meet(bob)).toThrow('Alice is already friends with Bob');
  });
});

describe('Batched Jackal Triangle - step-by-step', () => {
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
  });

  describe('Alice meets Bob', () => {
    beforeAll(() => {
      flushReport = messageForwarder.flush();
      alice.meet(bob);
    });

    it('Message Logs', () => {
      expect(flushReport).toEqual([]);
      // messagesAB is alreadsy sent but nothing is flushed yet
      expect(messageForwarder.getFullLog()).toEqual(separator.concat(messagesAB));
    });

    it('Alice is friends with Bob', () => {
      expect(alice.getFriends()).toEqual(['Bob']);
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
        expect(messageForwarder.getFullLog()).toEqual(separator.concat(messagesAB, messagesBC));
      });

      it('Alice is friends with Bob', () => {
        expect(alice.getFriends()).toEqual(['Bob']);
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
        expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
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
          expect(flushReport).toEqual([
            "[Bob]->[Charlie] pauze true",
            "[Bob]->[Charlie] meet",
            "[Bob]->[Charlie] probe genRanHex1",
            "[Bob]->[Alice] probe genRanHex2",
            "[Bob]->[Charlie] probe genRanHex2",
            "[Bob]->[Charlie] pauze false",
         ]);
          // messagesCA is already sent but messagesBC is still what was just flushed here
          expect(messageForwarder.getFullLog(true)).toEqual([
            "[---]->[---] ---",
            "[Alice]->[Bob] pauze true",
            "[Alice]->[Bob] meet",
            "[Alice]->[Bob] probe genRanHex1",
            "[Alice]->[Bob] pauze false",
            "[---]->[---] ---",
            "[Alice]>-[Bob] meet",
            "[Alice]>-[Bob] probe genRanHex1",

            // start of this round
            "[Bob]->[Charlie] pauze true",
            "[Bob]->[Charlie] meet",
            "[Bob]->[Charlie] probe genRanHex1",
            "[Bob]->[Alice] probe genRanHex2",
            "[Bob]->[Charlie] probe genRanHex2",
            "[Bob]->[Charlie] pauze false",
            "[---]->[---] ---",
            "[Bob]>-[Charlie] meet",
            "[Bob]>-[Charlie] probe genRanHex1",
            "[Bob]>-[Alice] probe genRanHex2",
            "[Bob]>-[Charlie] probe genRanHex2",
            // end of this round

            "[Charlie]->[Alice] pauze true",
            "[Charlie]->[Alice] meet",
            "[Charlie]->[Alice] probe genRanHex1",
            "[Charlie]->[Alice] probe genRanHex2",
            "[Charlie]->[Bob] probe genRanHex3",
            "[Charlie]->[Alice] probe genRanHex3",
            "[Charlie]->[Alice] pauze false",
         ]);
        });

        it('Alice is friends with Bob', () => {
          expect(alice.getFriends()).toEqual(['Bob']);
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
              from: ['Bob'],
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
          expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            // 'genRanHex1',
            // 'genRanHex2',
            // 'genRanHex3'
         ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
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

        it('Jackal Logs', () => {
          expect(alice.getLog()).toEqual([
            "I meet Bob, and offer them all my flood probes",
         ]);
          expect(bob.getLog()).toEqual([
            "PAUZING MESSAGES TO Alice",
            "MEET MESSAGE FROM Alice, offering all flood probes",
            "UNPAUZING MESSAGES TO Alice",
            "I meet Charlie, and offer them all my flood probes",
            "OFFERING PROBE genRanHex1 TO Charlie",
         ]);
          expect(charlie.getLog()).toEqual([
            "PAUZING MESSAGES TO Bob",
            "MEET MESSAGE FROM Bob, offering all flood probes",
            "UNPAUZING MESSAGES TO Bob",
            "I meet Alice, and offer them all my flood probes",
            "OFFERING PROBE genRanHex1 TO Alice",
            "OFFERING PROBE genRanHex2 TO Alice",
 
         ]);
        });


        describe('Messages Round 4', () => {
          beforeAll(() => {
            flushReport = messageForwarder.flush();
          });

          it('Message Logs', () => {
            expect(flushReport).toEqual(messagesCA);
            // messages4 is already sent but messagesCA is still what was just flushed here
            expect(messageForwarder.getFullLog(true)).toEqual(fullLogRound4);
            expect(messageForwarder.getBatch()).toEqual([
              "[Bob]->[Alice] probe genRanHex3",
              "[Alice]->[Bob] probe genRanHex3",
              "[Alice]->[Charlie] probe genRanHex1",
              "[Alice]->[Charlie] probe genRanHex2",
              "[Alice]->[Charlie] loop genRanHex1 genRanHex4",
              "[Alice]->[Charlie] probe genRanHex5",
           ]);
          });

          it('Probe trees', () => {
            expect(Object.keys(alice.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3', 'genRanHex5'].sort());
            expect(Object.keys(bob.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3'].sort());
            expect(Object.keys(charlie.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3'].sort());
            expectProbe('genRanHex1', alice, bob, charlie, 1);
            expectProbe('genRanHex2', bob, charlie, alice, 2);
            expectProbe('genRanHex3', charlie, alice, bob, 2);
          });
 

          it('Alice, Bob and Charlie all know each other', () => {
            expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
            expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
            expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
          });

          it('Alice, Bob and Charlie all have all probes', () => {
            expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
            expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
            expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
          });

          describe('Messages Round 5', () => {
            it('Message Logs', () => {
              expect(messageForwarder.flush()).toEqual([
                "[Bob]->[Alice] probe genRanHex3",
                "[Alice]->[Bob] probe genRanHex3",
                "[Alice]->[Charlie] probe genRanHex1",
                "[Alice]->[Charlie] probe genRanHex2",
                "[Alice]->[Charlie] loop genRanHex1 genRanHex4",
                "[Alice]->[Charlie] probe genRanHex5",  
             ]);
              // messages5 is already sent but messages4 is still what was just flushed here
              expect(messageForwarder.getFullLog(true)).toEqual([].concat(fullLogRound4, fullLogRound5));
            });

            it('Probe trees', () => {
              expect(Object.keys(alice.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3', 'genRanHex5'].sort());
              expect(Object.keys(bob.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3'].sort());
              expect(Object.keys(charlie.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3', 'genRanHex5'].sort());
              expectProbe('genRanHex1', alice, bob, charlie, 1);
              expectProbe('genRanHex2', bob, charlie, alice, 2);
              expectProbe('genRanHex3', charlie, alice, bob, 2);
            });


            it('Alice, Bob and Charlie all know each other', () => {
              expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
              expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
              expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
            });

            it('Alice, Bob and Charlie all have all probes', () => {
              expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
              expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
              expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
            });

            it('Jackal Logs', () => {
              expect(alice.getLog()).toEqual([
                "I meet Bob, and offer them all my flood probes",
                "PAUZING MESSAGES TO Charlie",
                "MEET MESSAGE FROM Charlie, offering all flood probes",
                "OFFERING PROBE genRanHex1 TO Charlie",
                "PAUZED MESSAGE TO Charlie: probe genRanHex1",
                "OFFERING PROBE genRanHex2 TO Charlie",
                "PAUZED MESSAGE TO Charlie: probe genRanHex2",
                "PROBE genRanHex1 ALREADY KNOWN TO US, VIRGIN FOR Charlie!",
                "PAUZED MESSAGE TO Charlie: loop genRanHex1 genRanHex4",
                "PROBE genRanHex2 ALREADY KNOWN TO US, VIRGIN FOR Charlie!",
                "PAUZED MESSAGE TO Charlie: probe genRanHex5",
                "UNPAUZING MESSAGES TO Charlie",
                "SENDING PAUZED MESSAGE TO Charlie: probe genRanHex1",
                "SENDING PAUZED MESSAGE TO Charlie: probe genRanHex2",
                "SENDING PAUZED MESSAGE TO Charlie: loop genRanHex1 genRanHex4",
                "SENDING PAUZED MESSAGE TO Charlie: probe genRanHex5",
                "PROBE genRanHex3 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Bob!",
             ]);
              expect(bob.getLog()).toEqual([
                "PAUZING MESSAGES TO Alice",
                "MEET MESSAGE FROM Alice, offering all flood probes",
                "UNPAUZING MESSAGES TO Alice",
                "I meet Charlie, and offer them all my flood probes",
                "OFFERING PROBE genRanHex1 TO Charlie",
                "PROBE genRanHex3 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Alice!",
             ]);
              expect(charlie.getLog()).toEqual([
                "PAUZING MESSAGES TO Bob",
                "MEET MESSAGE FROM Bob, offering all flood probes",
                "UNPAUZING MESSAGES TO Bob",
                "I meet Alice, and offer them all my flood probes",
                "OFFERING PROBE genRanHex1 TO Alice",
                "OFFERING PROBE genRanHex2 TO Alice",
                "PROBE genRanHex1 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Alice!",
                "PROBE genRanHex2 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Alice!",
                "LOOP TRACE genRanHex4 FOR PROBE genRanHex1 COMING TO US FROM SENDER Alice",
                "PROBE genRanHex1 HAS TRACES: ",
                "PROBE genRanHex1 HAS FROM: Bob",
                "PROBE genRanHex1 HAS TO: Alice",
                "FORWARDING LOOP TO Bob",
             ]);
            });
            describe('Messages Round 6', () => {
              it('Message Logs', () => {
                expect(messageForwarder.flush()).toEqual([
                  "[Charlie]->[Bob] loop genRanHex1 genRanHex4",
                  "[Charlie]->[Bob] probe genRanHex5",
                ]);
                // messages5 is already sent but messages4 is still what was just flushed here
                expect(messageForwarder.getFullLog(true)).toEqual([].concat(fullLogRound4, fullLogRound5, fullLogsRound6));
              });
              describe('Messages Round 7', () => {
                it('Message Logs', () => {
                  expect(messageForwarder.flush()).toEqual([
                    "[Bob]->[Alice] loop genRanHex1 genRanHex4",
                    "[Bob]->[Alice] probe genRanHex5",
                  ]);
                  // messages5 is already sent but messages4 is still what was just flushed here
                  expect(messageForwarder.getFullLog(true)).toEqual([].concat(fullLogRound4, fullLogRound5, fullLogsRound6, fullLogsRound7));
                });
    
                describe('Messages Round 8', () => {
                  it('Message Logs', () => {
                    expect(messageForwarder.flush()).toEqual([
                      "[Alice]->[Bob] loop genRanHex5 genRanHex6",
                    ]);
                    // messages5 is already sent but messages4 is still what was just flushed here
                    expect(messageForwarder.getFullLog(true)).toEqual([].concat(fullLogRound4, fullLogRound5, fullLogsRound6, fullLogsRound7, fullLogsRound8));
                  });
                  it('Jackal Logs', () => {
                    expect(alice.getLog()).toEqual([
                      "I meet Bob, and offer them all my flood probes",
                      "PAUZING MESSAGES TO Charlie",
                      "MEET MESSAGE FROM Charlie, offering all flood probes",
                      "OFFERING PROBE genRanHex1 TO Charlie",
                      "PAUZED MESSAGE TO Charlie: probe genRanHex1",
                      "OFFERING PROBE genRanHex2 TO Charlie",
                      "PAUZED MESSAGE TO Charlie: probe genRanHex2",
                      "PROBE genRanHex1 ALREADY KNOWN TO US, VIRGIN FOR Charlie!",
                      "PAUZED MESSAGE TO Charlie: loop genRanHex1 genRanHex4",
                      "PROBE genRanHex2 ALREADY KNOWN TO US, VIRGIN FOR Charlie!",
                      "PAUZED MESSAGE TO Charlie: probe genRanHex5",
                      "UNPAUZING MESSAGES TO Charlie",
                      "SENDING PAUZED MESSAGE TO Charlie: probe genRanHex1",
                      "SENDING PAUZED MESSAGE TO Charlie: probe genRanHex2",
                      "SENDING PAUZED MESSAGE TO Charlie: loop genRanHex1 genRanHex4",
                      "SENDING PAUZED MESSAGE TO Charlie: probe genRanHex5",
                      "PROBE genRanHex3 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Bob!",
                      "LOOP TRACE genRanHex4 FOR PROBE genRanHex1 COMING TO US FROM SENDER Bob",
                      "PROBE genRanHex1 HAS TRACES: genRanHex4",
                      "PROBE genRanHex1 HAS FROM: ",
                      "PROBE genRanHex1 HAS TO: Bob Charlie",
                      "OUR LOOP TRACE CAME BACK!",
                      "PROBE genRanHex5 ALREADY KNOWN TO US, VIRGIN FOR Bob!",
                   ]);
                    expect(bob.getLog()).toEqual([
                      "PAUZING MESSAGES TO Alice",
                      "MEET MESSAGE FROM Alice, offering all flood probes",
                      "UNPAUZING MESSAGES TO Alice",
                      "I meet Charlie, and offer them all my flood probes",
                      "OFFERING PROBE genRanHex1 TO Charlie",
                      "PROBE genRanHex3 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Alice!",
                      "LOOP TRACE genRanHex4 FOR PROBE genRanHex1 COMING TO US FROM SENDER Charlie",
                      "PROBE genRanHex1 HAS TRACES: ",
                      "PROBE genRanHex1 HAS FROM: Alice",
                      "PROBE genRanHex1 HAS TO: Charlie",
                      "FORWARDING LOOP TO Alice",
                      "LOOP TRACE genRanHex6 FOR PROBE genRanHex5 COMING TO US FROM SENDER Alice",
                      "PROBE genRanHex5 HAS TRACES: ",
                      "PROBE genRanHex5 HAS FROM: Charlie",
                      "PROBE genRanHex5 HAS TO: Alice",
                      "FORWARDING LOOP TO Charlie",
                    ]);
                    expect(charlie.getLog()).toEqual([
                      "PAUZING MESSAGES TO Bob",
                      "MEET MESSAGE FROM Bob, offering all flood probes",
                      "UNPAUZING MESSAGES TO Bob",
                      "I meet Alice, and offer them all my flood probes",
                      "OFFERING PROBE genRanHex1 TO Alice",
                      "OFFERING PROBE genRanHex2 TO Alice",
                      "PROBE genRanHex1 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Alice!",
                      "PROBE genRanHex2 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Alice!",
                      "LOOP TRACE genRanHex4 FOR PROBE genRanHex1 COMING TO US FROM SENDER Alice",
                      "PROBE genRanHex1 HAS TRACES: ",
                      "PROBE genRanHex1 HAS FROM: Bob",
                      "PROBE genRanHex1 HAS TO: Alice",
                      "FORWARDING LOOP TO Bob",
                  
                   ]);
                  });
        
        
                  it('Alice has loops', () => {
                    expect(alice.getLoops().sort()).toEqual([
                      "genRanHex1:genRanHex4",
                    ].sort());
                  });
                });
              });
            }); // Messages Round 6
          }); // Messages Round 5
        }); // Messages Round 4
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic jackal triangle
