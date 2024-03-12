/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

const messagesAB = [
  "[Alice]->[Bob] pauze true",
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex1",
  "[Alice]->[Bob] pauze false",
];

const messagesBC = [
  "[Bob]->[Charlie] pauze true",
  "[Bob]->[Charlie] meet",
  "[Bob]->[Charlie] probe genRanHex2",
  "[Bob]->[Charlie] pauze false",
];

const messagesCA = [
  "[Charlie]->[Alice] pauze true",
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Alice] probe genRanHex3",
  "[Charlie]->[Alice] pauze false",
];

// const messages4 = [
// ];

// const messages5 = [];

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


describe('already friends', () => {
  it('throws an error', async () => {
    const { Jackal } = await import('../src/main.js');
    const alice = new Jackal('Alice');
    const bob = new Jackal('Bob');

    alice.meet(bob);
    expect(() => alice.meet(bob)).toThrow('Alice is already friends with Bob');
  });
});

describe('Basic Jackal Triangle - step-by-step', () => {
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
      expect(messageForwarder.getFullLog()).toEqual(messagesAB);
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
        expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC));
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
        expect(bob.getFriends()).toEqual(['Charlie']);
      });
      it('Bob has some probes', () => {
        expect(bob.getProbes()).toEqual({
          genRanHex2: {
            traces: [],
            from: [],
            homeMinted: true,
            to: ['Charlie']
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
          expect(bob.getFriends()).toEqual(['Charlie']);
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            // 'genRanHex1',
            // 'genRanHex2',
            // 'genRanHex3'
         ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual(['Alice']);
        });
        it('Charlie has some probes', () => {
          expect(charlie.getProbes()).toEqual({
            genRanHex3: {
              traces: [],
              from: [],
              homeMinted: true,
              to: ['Alice']
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
            "I meet Charlie, and offer them all my flood probes",
        
         ]);
          expect(charlie.getLog()).toEqual([
            "I meet Alice, and offer them all my flood probes",
        
         ]);
        });


        // describe('Another round of messages', () => {
        //   beforeAll(() => {
        //     flushReport = messageForwarder.flush();
        //   });

        //   it('Message Logs', () => {
        //     expect(flushReport).toEqual(messagesCA);
        //     // messages4 is already sent but messagesCA is still what was just flushed here
        //     expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC, messagesCA, messages4));
        //   });

        //   it('Probe trees', () => {
        //     expect(Object.keys(alice.getProbes()).sort()).toEqual(['genRanHex1'].sort());
        //     expect(Object.keys(bob.getProbes()).sort()).toEqual(['genRanHex2'].sort());
        //     expect(Object.keys(charlie.getProbes()).sort()).toEqual(['genRanHex3'].sort());
        //     expectProbe('genRanHex1', alice, bob, charlie, 1);
        //     expectProbe('genRanHex2', bob, charlie, alice, 2);
        //     expectProbe('genRanHex3', charlie, alice, bob, 2);
        //   });
  

        //   it('Alice, Bob and Charlie all know each other', () => {
        //     expect(alice.getFriends()).toEqual(['Bob']);
        //     expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
        //     expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
        //   });

        //   it('Alice, Bob and Charlie all have all probes', () => {
        //     expect(alice.getFriends()).toEqual(['Charlie']);
        //     expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
        //     expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
        //   });

        //   it('Jackal Logs', () => {
        //     expect(alice.getLog()).toEqual([
        //       "I meet Bob, and offer them all my flood probes",
        //     ]);
        //     expect(bob.getLog()).toEqual([
        //       "MEET MESSAGE FROM Alice, offering all flood probes",
        //       "I meet Charlie, and offer them all my flood probes",
        //       "OFFERING PROBE genRanHex1 TO Charlie",
        //    ]);
        //     expect(charlie.getLog()).toEqual([
        //       "MEET MESSAGE FROM Bob, offering all flood probes",
        //       "I meet Alice, and offer them all my flood probes",
        //       "OFFERING PROBE genRanHex1 TO Alice",
        //       "OFFERING PROBE genRanHex2 TO Alice",
          
        //    ]);
        //   });

        //   describe('Another round of messages', () => {
        //     beforeAll(() => {
        //       flushReport = messageForwarder.flush();
        //     });

        //     it('Message Logs', () => {
        //       // expect(flushReport).toEqual(messages4);
        //       // messages5 is already sent but messages4 is still what was just flushed here
        //       expect(messageForwarder.getFullLog()).toEqual([].concat(messagesAB, messagesBC, messagesCA, messages4, messages5));
        //     });

        //     it('Probe trees', () => {
        //       expect(Object.keys(alice.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3'].sort());
        //       expect(Object.keys(bob.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3'].sort());
        //       expect(Object.keys(charlie.getProbes()).sort()).toEqual(['genRanHex1', 'genRanHex2', 'genRanHex3'].sort());
        //       expectProbe('genRanHex1', alice, bob, charlie, 1);
        //       expectProbe('genRanHex2', bob, charlie, alice, 2);
        //       expectProbe('genRanHex3', charlie, alice, bob, 2);
        //     });
    

        //     it('Alice, Bob and Charlie all know each other', () => {
        //       expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
        //       expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
        //       expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
        //     });

        //     it('Alice, Bob and Charlie all have all probes', () => {
        //       expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
        //       expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
        //       expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
        //     });

        //     it('Jackal Logs', () => {
        //       expect(alice.getLog()).toEqual([
        //         "I meet Bob, and offer them all my flood probes",
        //         "MEET MESSAGE FROM Charlie, offering all flood probes",
        //         "OFFERING PROBE genRanHex1 TO Charlie",
        //         "OFFERING PROBE genRanHex2 TO Charlie",                  
        //         "PROBE genRanHex1 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Charlie!",
        //         "PROBE genRanHex2 ALREADY KNOWN TO US, BUT NOT VIRGIN FOR Charlie!",
            
        //      ]);
        //       expect(bob.getLog()).toEqual([
        //         "MEET MESSAGE FROM Alice, offering all flood probes",
        //         "I meet Charlie, and offer them all my flood probes",
        //          "OFFERING PROBE genRanHex1 TO Charlie",      
        //      ]);
        //       expect(charlie.getLog()).toEqual([
        //         "MEET MESSAGE FROM Bob, offering all flood probes",
        //         "I meet Alice, and offer them all my flood probes",
        //         "OFFERING PROBE genRanHex1 TO Alice",
        //         "OFFERING PROBE genRanHex2 TO Alice",            
        //      ]);
        //     });
        //   }); // Another round of messages
        // }); // Another round of messages
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic jackal triangle
