/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

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
  beforeAll(async () => {
    const { Stingray } = await import('../src/main.js');
    alice = new Stingray('Alice');
    bob = new Stingray('Bob');
    charlie = new Stingray('Charlie');
  });

  describe('Alice meets Bob', () => {
    beforeAll(() => {
      alice.meet(bob);
    });
    it('Alice is friends with Bob', () => {
      expect(alice.getFriends()).toEqual([ 'Bob' ]);
    });
    it('Alice has an genRanHex1 probe for Bob', () => {
      expect(alice.getProbes()).toEqual({
        genRanHex1: {
          flood: true,
          from: [],
          homeMinted: true,
          to: ['Bob']
        }
      });
    });
    it('Alice has no loops', () => {
      expect(alice.getLoops()).toEqual({});
    });
    it('Alice has sent and received some messages', () => {
      expect(alice.getMessageLog()).toEqual([
        'TO[Bob] meet',
        'TO[Bob] probe genRanHex1'
      ]);
    });
    it('Bob is friends with Alice', () => {
      expect(bob.getFriends()).toEqual([ 'Alice' ]);
    });
    it('Bob has an genRanHex1 probe with Alice', () => {
      expect(bob.getProbes()).toEqual({
        genRanHex1: {
          flood: true,
          from: ['Alice'],
          homeMinted: false,
          to: []
        }
      });
    });
    it('Bob has no loops', () => {
      expect(bob.getLoops()).toEqual({});
    });

    it('Bob has sent and received some messages', () => {
      expect(bob.getMessageLog()).toEqual([
        "FROM[Alice] meet",
        "FROM[Alice] probe genRanHex1",
      ]);
    });

    it('Charlie is friends with nobody', () => {
      expect(charlie.getFriends()).toEqual([]);
    });
    it('Charlie has no probes', () => {
      expect(charlie.getProbes()).toEqual({
      });
    });
    it('Charlie has no loops', () => {
      expect(charlie.getLoops()).toEqual({});
    });
    it('Charlie has sent and received no messages', () => {
      expect(charlie.getMessageLog()).toEqual([
      ]);
    });

    describe('Bob meets Charlie', () => {
      beforeAll(() => {
        bob.meet(charlie);
      });
      it('Alice is friends with Bob', () => {
        expect(alice.getFriends()).toEqual([ 'Bob' ]);
      });
      it('Alice has some probes', () => {
        expect(alice.getProbes()).toEqual({
          genRanHex1: {
            flood: true,
            from: [],
            homeMinted: true,
            to: ['Bob']
          },
          genRanHex2: {
            flood: true,
            from: ['Bob'],
            homeMinted: false,
            to: []
          }
        });
      });
      it('Alice has no loops', () => {
        expect(alice.getLoops()).toEqual({});
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
            flood: true,
            from: ['Alice'],
            homeMinted: false,
            to: ['Charlie']
          },
          genRanHex2: {
            flood: true,
            from: [],
            homeMinted: true,
            to: ['Alice','Charlie']
          }
        });
      });
      it('Bob has no loops', () => {
        expect(bob.getLoops()).toEqual({});
      });
      it('Bob has sent and received some messages', () => {
        expect(bob.getMessageLog()).toEqual([
          "FROM[Alice] meet",
          "FROM[Alice] probe genRanHex1",
          "TO[Charlie] meet",
          "TO[Charlie] probe genRanHex1",      
          "TO[Alice] probe genRanHex2",
          "TO[Charlie] probe genRanHex2",
        ]);
      });
  
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual([ 'Bob' ]);
      });
      it('Charlie has some probes', () => {
        expect(charlie.getProbes()).toEqual({
          genRanHex1: {
            flood: true,
            from: ['Bob'],
            homeMinted: false,
            to: []
          },
          genRanHex2: {
            flood: true,
            from: ['Bob'],
            homeMinted: false,
            to: []
          }
        });
      });
      it('Charlie has no loops', () => {
        expect(charlie.getLoops()).toEqual({});
      });  
      it('Charlie has sent and received some messages', () => {
        expect(charlie.getMessageLog()).toEqual([
          "FROM[Bob] meet",
          "FROM[Bob] probe genRanHex1",
          "FROM[Bob] probe genRanHex2",
        ]);
      });
  
      // describe('Charlie meets Alice', () => {
      //   beforeAll(() => {
      //     charlie.meet(alice);
      //   });

      //   it('Alice is friends with Bob and Charlie', () => {
      //     expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
      //   });
      //   it('Alice has some probes', () => {
      //     expect(alice.getProbes()).toEqual({
      //       genRanHex1: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       },
      //       genRanHex2: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       },
      //       genRanHex3: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       }
      //     });
      //   });
      //   it('Alice has 3 loops', () => {
      //     expect(alice.getLoops().sort()).toEqual([
      //       'genRanHex1',
      //       'genRanHex2',
      //       'genRanHex3'
      //     ].sort());
      //   });
      //   it('Alice has sent and received some messages', () => {
      //     expect(alice.getMessageLog()).toEqual([
      //       'TO[Bob] meet',
      //       'TO[Bob] probe genRanHex1',
      //       "FROM[Bob] probe genRanHex2",
      //       "FROM[Charlie] meet",
      //       "FROM[Bob] probe genRanHex3",
      //       "TO[Charlie] probe genRanHex3",
      //       "FROM[Bob] loop genRanHex3 default",
      //       "TO[Charlie] loop genRanHex3 default",
      //       "FROM[Charlie] probe genRanHex2",
      //       "TO[Bob] loop genRanHex2 default",
      //       "FROM[Charlie] loop genRanHex2 default",
      //       "FROM[Charlie] probe genRanHex1",
      //       "TO[Bob] loop genRanHex1 default",
      //       "FROM[Charlie] loop genRanHex1 default",
      //     ]);
      //   });
    
      //   it('Bob is friends with Alice and Charlie', () => {
      //     expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
      //   });
      //   it('Bob has some probes', () => {
      //     expect(bob.getProbes()).toEqual({
      //       genRanHex1: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       },
      //       genRanHex2: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       },
      //       genRanHex3: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       }
      //     }); 
      //   });
      //   it('Bob has 3 loops', () => {
      //     expect(bob.getLoops().sort()).toEqual([
      //       'genRanHex1',
      //       'genRanHex2',
      //       'genRanHex3'
      //     ].sort());
      //   });
      //   it('Bob has sent and received some messages', () => {
      //     expect(bob.getMessageLog()).toEqual([
      //       "FROM[Alice] meet",
      //       "FROM[Alice] probe genRanHex1",
      //       "TO[Charlie] meet",
      //       "TO[Alice] probe genRanHex2",
      //       "TO[Charlie] probe genRanHex2",
      //       "TO[Charlie] probe genRanHex1",
      //       "FROM[Charlie] probe genRanHex3",
      //       "TO[Alice] probe genRanHex3",
      //       "FROM[Charlie] loop genRanHex3 default",
      //       "TO[Alice] loop genRanHex3 default",
      //       "FROM[Alice] loop genRanHex2 default",
      //       "TO[Charlie] loop genRanHex2 default",
      //       "FROM[Alice] loop genRanHex1 default",
      //       "TO[Charlie] loop genRanHex1 default",
      //     ]);
      //   });
  
      //   it('Charlie is friends with Bob and Alice', () => {
      //     expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
      //   });
      //   it('Charlie has some probes', () => {
      //     expect(charlie.getProbes()).toEqual({
      //       genRanHex1: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       },
      //       genRanHex2: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       },
      //       genRanHex3: {
      //         flood: true,
      //         from: [],
      //         homeMinted: true,
      //         to: ['Alice']
      //       }
      //     });
      //   });
      //   it('Charlie has 3 loops', () => {
      //     expect(charlie.getLoops().sort()).toEqual([
      //       'genRanHex1',
      //       'genRanHex2',
      //       'genRanHex3'
      //     ].sort());
      //   });
      //   it('Charlie has sent and received some messages', () => {
      //     expect(charlie.getMessageLog()).toEqual([
      //       "FROM[Bob] meet",
      //       "FROM[Bob] probe genRanHex2",
      //       "FROM[Bob] probe genRanHex1",
      //       "TO[Alice] meet",
      //       "TO[Bob] probe genRanHex3",
      //       "FROM[Alice] probe genRanHex3",
      //       "TO[Bob] loop genRanHex3 default",
      //       "FROM[Alice] loop genRanHex3 default",
      //       "TO[Alice] probe genRanHex2",
      //       "FROM[Bob] loop genRanHex2 default",
      //       "TO[Alice] loop genRanHex2 default",
      //       "TO[Alice] probe genRanHex1",
      //       "FROM[Bob] loop genRanHex1 default",
      //       "TO[Alice] loop genRanHex1 default"
      //     ]);
      //   });    
      // }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic stingray triangle


// describe('Basic Stingray Triangle - synchronous', () => {
//   // let Stingray: unknown;
//   let alice: any;
//   let bob: any;
//   let charlie: any;
//   beforeAll(async () => {
//     const { Stingray } = await import('../src/main.js');
//     alice = new Stingray('Alice');
//     bob = new Stingray('Bob');
//     charlie = new Stingray('Charlie');
//   });

//   describe('Alice meets Bob meet Charlie meets Alice', () => {
//     beforeAll(() => {
//       alice.meet(bob);
//       bob.meet(charlie);
//       charlie.meet(alice);
//     });

//     it('Alice is friends with Bob and Charlie', () => {
//       expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
//     });
//     it('Alice has some probes', () => {
//       expect(alice.getProbes()).toEqual({
//         genRanHex4: { Bob: true, Charlie: true },
//         genRanHex5: { Bob: true, Charlie: true },
//         genRanHex6: { Bob: true, Charlie: true },
//       });
//     });
//     it('Alice has some loop', () => {
//       expect(alice.getLoops().sort()).toEqual([
//         'genRanHex4',
//         'genRanHex5',
//         'genRanHex6',
//       ].sort());
//     });

//     it('Bob is friends with Alice and Charlie', () => {
//       expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
//     });
//     it('Bob has some probes', () => {
//       expect(bob.getProbes()).toEqual({
//         genRanHex4: { Alice: true, Charlie: true },
//         genRanHex5: { Alice: true, Charlie: true },
//         genRanHex6: { Alice: true, Charlie: true },
//       }); 
//     });
//     it('Bob has some loops', () => {
//       expect(bob.getLoops().sort()).toEqual([
//         'genRanHex4',
//         'genRanHex5',
//         'genRanHex6',
//       ].sort());
//     });

//     it('Charlie is friends with Bob and Alice', () => {
//       expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
//     });
//     it('Charlie has some probes', () => {
//       expect(charlie.getProbes()).toEqual({
//         genRanHex4: { Bob: true, Alice: true },
//         genRanHex5: { Bob: true, Alice: true },
//         genRanHex6: { Bob: true, Alice: true },
//       });
//     });
//     it('Charlie has 1 loop', () => {
//       expect(charlie.getLoops().sort()).toEqual([
//         'genRanHex4',
//         'genRanHex5',
//         'genRanHex6',        
//       ].sort());
//     });
//     it('Alice has sent and received some messages', () => {
//       expect(alice.getMessageLog()).toEqual([
//         'TO[Bob] meet',
//         'TO[Bob] probe genRanHex4',
//         'FROM[Bob] probe genRanHex5',
//         "FROM[Charlie] meet",
//         "FROM[Bob] probe genRanHex6",
//         "TO[Charlie] probe genRanHex6",
//         "FROM[Bob] loop genRanHex6 default",
//         "TO[Charlie] loop genRanHex6 default",
//         "FROM[Charlie] probe genRanHex5",
//         "TO[Bob] loop genRanHex5 default",
//         "FROM[Charlie] loop genRanHex5 default",
//         "FROM[Charlie] probe genRanHex4",
//         "TO[Bob] loop genRanHex4 default",
//         "FROM[Charlie] loop genRanHex4 default",
//       ]);
//     });
//     it('Bob has sent and received some messages', () => {
//       expect(bob.getMessageLog()).toEqual([
//         "FROM[Alice] meet",
//         "FROM[Alice] probe genRanHex4",
//         "TO[Charlie] meet",
//         "TO[Alice] probe genRanHex5",
//         "TO[Charlie] probe genRanHex5",
//         "TO[Charlie] probe genRanHex4",
//         "FROM[Charlie] probe genRanHex6",
//         "TO[Alice] probe genRanHex6",
//         "FROM[Charlie] loop genRanHex6 default",
//         "TO[Alice] loop genRanHex6 default",
//         "FROM[Alice] loop genRanHex5 default",
//         "TO[Charlie] loop genRanHex5 default",
//         "FROM[Alice] loop genRanHex4 default",
//         "TO[Charlie] loop genRanHex4 default",
//       ]);
//     });
//     it('Charlie has sent and received some messages', () => {
//       expect(charlie.getMessageLog()).toEqual([
//         "FROM[Bob] meet",
//         "FROM[Bob] probe genRanHex5",
//         "FROM[Bob] probe genRanHex4",
//         "TO[Alice] meet",
//         "TO[Bob] probe genRanHex6",
//         "FROM[Alice] probe genRanHex6",
//         "TO[Bob] loop genRanHex6 default",
//         "FROM[Alice] loop genRanHex6 default",
//         "TO[Alice] probe genRanHex5",
//         "FROM[Bob] loop genRanHex5 default",
//         "TO[Alice] loop genRanHex5 default",
//         "TO[Alice] probe genRanHex4",
//         "FROM[Bob] loop genRanHex4 default",
//         "TO[Alice] loop genRanHex4 default",
//       ]);
//     }); // Charlie has sent and received some messages
//   }); // Alice meest Bob meets Charlie meets Alice
// }); // basic stingray triangle
