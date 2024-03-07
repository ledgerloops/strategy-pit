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
    const { Salmon } = await import('../src/main.js');
    const alice = new Salmon('Alice');
    const bob = new Salmon('Bob');

    alice.meet(bob);
    expect(() => alice.meet(bob)).toThrow('Alice is already friends with Bob');
  });
});

describe('Basic Salmon Triangle - step-by-step', () => {
  // let Salmon: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  beforeAll(async () => {
    const { Salmon } = await import('../src/main.js');
    alice = new Salmon('Alice');
    bob = new Salmon('Bob');
    charlie = new Salmon('Charlie');
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
        genRanHex1: { Bob: true }
      });
    });
    it('Alice has no loops', () => {
      expect(alice.getLoops()).toEqual([]);
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
        genRanHex1: { Alice: true }
      });
    });
    it('Bob has no loops', () => {
      expect(bob.getLoops()).toEqual([]);
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
      expect(charlie.getLoops()).toEqual([]);
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
          genRanHex1: { Bob: true },
          genRanHex2: { Bob: true }
        });
      });
      it('Alice has no loops', () => {
        expect(alice.getLoops()).toEqual([]);
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
          genRanHex1: { Alice: true, Charlie: true },
          genRanHex2: { Alice: true, Charlie: true }
        });
      });
      it('Bob has no loops', () => {
        expect(bob.getLoops()).toEqual([]);
      });
      it('Bob has sent and received some messages', () => {
        expect(bob.getMessageLog()).toEqual([
          "FROM[Alice] meet",
          "FROM[Alice] probe genRanHex1",
          "TO[Charlie] meet",
          "TO[Alice] probe genRanHex2",
          "TO[Charlie] probe genRanHex2",
          "TO[Charlie] probe genRanHex1",      
        ]);
      });
  
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual([ 'Bob' ]);
      });
      it('Charlie has some probes', () => {
        expect(charlie.getProbes()).toEqual({
          genRanHex1: { Bob: true },
          genRanHex2: { Bob: true }
        });
      });
      it('Charlie has no loops', () => {
        expect(charlie.getLoops()).toEqual([]);
      });  
      it('Charlie has sent and received some messages', () => {
        expect(charlie.getMessageLog()).toEqual([
          "FROM[Bob] meet",
          "FROM[Bob] probe genRanHex2",
          "FROM[Bob] probe genRanHex1",
        ]);
      });
  
      describe('Charlie meets Alice', () => {
        beforeAll(() => {
          charlie.meet(alice);
        });

        it('Alice is friends with Bob and Charlie', () => {
          expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
        });
        it('Alice has some probes', () => {
          expect(alice.getProbes()).toEqual({
            genRanHex1: { Bob: true, Charlie: true },
            genRanHex2: { Bob: true, Charlie: true },
            genRanHex3: { Bob: true, Charlie: true }
          });
        });
        it('Alice has 3 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            'genRanHex1',
            'genRanHex2',
            'genRanHex3'
          ].sort());
        });
        it('Alice has sent and received some messages', () => {
          expect(alice.getMessageLog()).toEqual([
            'TO[Bob] meet',
            'TO[Bob] probe genRanHex1',
            "FROM[Bob] probe genRanHex2",
            "FROM[Charlie] meet",
            "FROM[Bob] probe genRanHex3",
            "TO[Charlie] probe genRanHex3",
            "FROM[Bob] loop genRanHex3 default",
            "TO[Charlie] loop genRanHex3 default",
            "FROM[Charlie] probe genRanHex2",
            "TO[Bob] loop genRanHex2 default",
            "FROM[Charlie] loop genRanHex2 default",
            "FROM[Charlie] probe genRanHex1",
            "TO[Bob] loop genRanHex1 default",
            "FROM[Charlie] loop genRanHex1 default",
          ]);
        });
    
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
        });
        it('Bob has some probes', () => {
          expect(bob.getProbes()).toEqual({
            genRanHex1: { Alice: true, Charlie: true },
            genRanHex2: { Alice: true, Charlie: true },
            genRanHex3: { Alice: true, Charlie: true }
          }); 
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'genRanHex1',
            'genRanHex2',
            'genRanHex3'
          ].sort());
        });
        it('Bob has sent and received some messages', () => {
          expect(bob.getMessageLog()).toEqual([
            "FROM[Alice] meet",
            "FROM[Alice] probe genRanHex1",
            "TO[Charlie] meet",
            "TO[Alice] probe genRanHex2",
            "TO[Charlie] probe genRanHex2",
            "TO[Charlie] probe genRanHex1",
            "FROM[Charlie] probe genRanHex3",
            "TO[Alice] probe genRanHex3",
            "FROM[Charlie] loop genRanHex3 default",
            "TO[Alice] loop genRanHex3 default",
            "FROM[Alice] loop genRanHex2 default",
            "TO[Charlie] loop genRanHex2 default",
            "FROM[Alice] loop genRanHex1 default",
            "TO[Charlie] loop genRanHex1 default",
          ]);
        });
  
        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
        });
        it('Charlie has some probes', () => {
          expect(charlie.getProbes()).toEqual({
            genRanHex1: { Alice: true, Bob: true },
            genRanHex2: { Alice: true, Bob: true },
            genRanHex3: { Alice: true, Bob: true }
          });
        });
        it('Charlie has 3 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            'genRanHex1',
            'genRanHex2',
            'genRanHex3'
          ].sort());
        });
        it('Charlie has sent and received some messages', () => {
          expect(charlie.getMessageLog()).toEqual([
            "FROM[Bob] meet",
            "FROM[Bob] probe genRanHex2",
            "FROM[Bob] probe genRanHex1",
            "TO[Alice] meet",
            "TO[Bob] probe genRanHex3",
            "FROM[Alice] probe genRanHex3",
            "TO[Bob] loop genRanHex3 default",
            "FROM[Alice] loop genRanHex3 default",
            "TO[Alice] probe genRanHex2",
            "FROM[Bob] loop genRanHex2 default",
            "TO[Alice] loop genRanHex2 default",
            "TO[Alice] probe genRanHex1",
            "FROM[Bob] loop genRanHex1 default",
            "TO[Alice] loop genRanHex1 default"
          ]);
        });    
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic salmon triangle


describe('Basic Salmon Triangle - synchronous', () => {
  // let Salmon: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  beforeAll(async () => {
    const { Salmon } = await import('../src/main.js');
    alice = new Salmon('Alice');
    bob = new Salmon('Bob');
    charlie = new Salmon('Charlie');
  });

  describe('Alice meets Bob meet Charlie meets Alice', () => {
    beforeAll(() => {
      alice.meet(bob);
      bob.meet(charlie);
      charlie.meet(alice);
    });

    it('Alice is friends with Bob and Charlie', () => {
      expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
      expect(alice.getProbes()).toEqual({
        genRanHex6: { Bob: true, Charlie: true }
      });
    });
    it('Alice has 1 loop', () => {
      expect(alice.getLoops().sort()).toEqual([
        'genRanHex6'
      ].sort());
    });

    it('Bob is friends with Alice and Charlie', () => {
      expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
      expect(bob.getProbes()).toEqual({
        genRanHex6: { Alice: true, Charlie: true }
      }); 
    });
    it('Bob has 1 loop', () => {
      expect(bob.getLoops().sort()).toEqual([
        'genRanHex6'
      ].sort());
    });

    it('Charlie is friends with Bob and Alice', () => {
      expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
      expect(charlie.getProbes()).toEqual({
        genRanHex6: { Alice: true, Bob: true }
      });
    });
    it('Charlie has 1 loop', () => {
      expect(charlie.getLoops().sort()).toEqual([
        'genRanHex6'
      ].sort());
    });
    it('Alice has sent and received some messages', () => {
      expect(alice.getMessageLog()).toEqual([
        'TO[Bob] meet',
        'TO[Bob] probe genRanHex6',
        "FROM[Charlie] meet",
        "FROM[Charlie] probe genRanHex6",
        "TO[Bob] loop genRanHex6 default",
        "FROM[Charlie] loop genRanHex6 default",
      ]);
    });
    it('Bob has sent and received some messages', () => {
      expect(bob.getMessageLog()).toEqual([
        "FROM[Alice] meet",
        "FROM[Alice] probe genRanHex6",
        "TO[Charlie] meet",
        "TO[Charlie] probe genRanHex6",
        "FROM[Alice] loop genRanHex6 default",
        "TO[Charlie] loop genRanHex6 default",
      ]);
    });
    it('Charlie has sent and received some messages', () => {
      expect(charlie.getMessageLog()).toEqual([
        "FROM[Bob] meet",
        "FROM[Bob] probe genRanHex6",
        "TO[Alice] meet",
        "TO[Alice] probe genRanHex6",
        "FROM[Bob] loop genRanHex6 default",
        "TO[Alice] loop genRanHex6 default",
      ]);
    }); // Charlie has sent and received some messages
  }); // Alice meest Bob meets Charlie meets Alice
}); // basic salmon triangle
