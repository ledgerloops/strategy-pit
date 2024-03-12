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
  let messageForwarder: any;
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
      messageForwarder.flush();
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
          traces: [],
          from: ['Alice'],
          homeMinted: false,
          to: []
        }
      });
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
    it('Charlie has sent and received no messages', () => {
      expect(charlie.getMessageLog()).toEqual([
      ]);
    });

    describe('Bob meets Charlie', () => {
      beforeAll(() => {
        bob.meet(charlie);
        messageForwarder.flush();
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
      it('Charlie has sent and received some messages', () => {
        expect(charlie.getMessageLog()).toEqual([
          "FROM[Bob] meet",
          "FROM[Bob] probe genRanHex1",
          "FROM[Bob] probe genRanHex2",
        ]);
      });
  
      describe('Charlie meets Alice', () => {
        beforeAll(() => {
          charlie.meet(alice);
        });

        it('Alice is friends with Bob and Charlie', () => {
          // FIXME
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
        it('Alice has sent and received some messages', () => {
          expect(alice.getMessageLog()).toEqual([
            'TO[Bob] meet',
            'TO[Bob] probe genRanHex1',
            "FROM[Bob] probe genRanHex2",
            // "FROM[Charlie] meet",
            // "FROM[Bob] probe genRanHex3",
            // "TO[Charlie] probe genRanHex3",
            // "FROM[Bob] loop genRanHex3 default",
            // "TO[Charlie] loop genRanHex3 default",
            // "FROM[Charlie] probe genRanHex2",
            // "TO[Bob] loop genRanHex2 default",
            // "FROM[Charlie] loop genRanHex2 default",
            // "FROM[Charlie] probe genRanHex1",
            // "TO[Bob] loop genRanHex1 default",
            // "FROM[Charlie] loop genRanHex1 default",
          ]);
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
          }); 
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            // 'genRanHex1',
            // 'genRanHex2',
            // 'genRanHex3'
          ].sort());
        });
        it('Bob has sent and received some messages', () => {
          expect(bob.getMessageLog()).toEqual([
            "FROM[Alice] meet",
            "FROM[Alice] probe genRanHex1",
            "TO[Charlie] meet",
            "TO[Charlie] probe genRanHex1",
            "TO[Alice] probe genRanHex2",
            "TO[Charlie] probe genRanHex2",
            // "FROM[Charlie] probe genRanHex3",
            // "TO[Alice] probe genRanHex3",
            // "FROM[Charlie] loop genRanHex3 default",
            // "TO[Alice] loop genRanHex3 default",
            // "FROM[Alice] loop genRanHex2 default",
            // "TO[Charlie] loop genRanHex2 default",
            // "FROM[Alice] loop genRanHex1 default",
            // "TO[Charlie] loop genRanHex1 default",
          ]);
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
        it('Charlie has sent and received some messages', () => {
          expect(charlie.getMessageLog()).toEqual([
            "FROM[Bob] meet",
            "FROM[Bob] probe genRanHex1",
            "FROM[Bob] probe genRanHex2",
            "TO[Alice] meet",
            "TO[Alice] probe genRanHex1",
            "TO[Alice] probe genRanHex2",
            "TO[Bob] probe genRanHex3",
            "TO[Alice] probe genRanHex3",
            // "FROM[Alice] probe genRanHex3",
            // "TO[Bob] loop genRanHex3 default",
            // "FROM[Alice] loop genRanHex3 default",
            // "FROM[Bob] loop genRanHex2 default",
            // "FROM[Bob] loop genRanHex1 default",
            // "TO[Alice] loop genRanHex1 default"
          ]);
        });    
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic stingray triangle
