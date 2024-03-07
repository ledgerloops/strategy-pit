/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

let counter: number = 0;
jest.unstable_mockModule('../src/util.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `gen-ran-hex-${counter++}`;
    })
  };
});
const { Salmon } = await import('../src/main.js');

describe('already friends', () => {
  it('throws an error', async () => {
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
    it('Alice has an AliceBob probe for Bob', () => {
      expect(alice.getProbes()).toEqual({
        AliceBob: { Bob: true }
      });
    });
    it('Alice has no loops', () => {
      expect(alice.getLoops()).toEqual([]);
    });
    it('Alice has sent and received some messages', () => {
      expect(alice.getMessageLog()).toEqual([
        'TO[Bob] meet',
        'TO[Bob] probe AliceBob'
      ]);
    });
    it('Bob is friends with Alice', () => {
      expect(bob.getFriends()).toEqual([ 'Alice' ]);
    });
    it('Bob has an AliceBob probe with Alice', () => {
      expect(bob.getProbes()).toEqual({
        AliceBob: { Alice: true }
      });
    });
    it('Bob has no loops', () => {
      expect(bob.getLoops()).toEqual([]);
    });

    it('Bob has sent and received some messages', () => {
      expect(bob.getMessageLog()).toEqual([
        "FROM[Alice] meet",
        "FROM[Alice] probe AliceBob",
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
          AliceBob: { Bob: true },
          BobCharlie: { Bob: true }
        });
      });
      it('Alice has no loops', () => {
        expect(alice.getLoops()).toEqual([]);
      });
      it('Alice has sent and received some messages', () => {
        expect(alice.getMessageLog()).toEqual([
          'TO[Bob] meet',
          'TO[Bob] probe AliceBob',
          "FROM[Bob] probe BobCharlie",
        ]);
      });
  
      it('Bob is friends with Alice and Charlie', () => {
        expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
      });
      it('Bob has some probes', () => {
        expect(bob.getProbes()).toEqual({
          AliceBob: { Alice: true, Charlie: true },
          BobCharlie: { Alice: true, Charlie: true }
        });
      });
      it('Bob has no loops', () => {
        expect(bob.getLoops()).toEqual([]);
      });
      it('Bob has sent and received some messages', () => {
        expect(bob.getMessageLog()).toEqual([
          "FROM[Alice] meet",
          "FROM[Alice] probe AliceBob",
          "TO[Charlie] meet",
          "TO[Alice] probe BobCharlie",
          "TO[Charlie] probe BobCharlie",
          "TO[Charlie] probe AliceBob",      
        ]);
      });
  
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual([ 'Bob' ]);
      });
      it('Charlie has some probes', () => {
        expect(charlie.getProbes()).toEqual({
          AliceBob: { Bob: true },
          BobCharlie: { Bob: true }
        });
      });
      it('Charlie has no loops', () => {
        expect(charlie.getLoops()).toEqual([]);
      });  
      it('Charlie has sent and received some messages', () => {
        expect(charlie.getMessageLog()).toEqual([
          "FROM[Bob] meet",
          "FROM[Bob] probe BobCharlie",
          "FROM[Bob] probe AliceBob",
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
            AliceBob: { Bob: true, Charlie: true },
            BobCharlie: { Bob: true, Charlie: true },
            CharlieAlice: { Bob: true, Charlie: true }
          });
        });
        it('Alice has 3 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            'AliceBob',
            'BobCharlie',
            'CharlieAlice'
          ].sort());
        });
        it('Alice has sent and received some messages', () => {
          expect(alice.getMessageLog()).toEqual([
            'TO[Bob] meet',
            'TO[Bob] probe AliceBob',
            "FROM[Bob] probe BobCharlie",
            "FROM[Charlie] meet",
            "FROM[Bob] probe CharlieAlice",
            "TO[Charlie] probe CharlieAlice",
            "FROM[Bob] loop CharlieAlice default",
            "TO[Charlie] loop CharlieAlice default",
            "FROM[Charlie] probe BobCharlie",
            "TO[Bob] loop BobCharlie default",
            "FROM[Charlie] loop BobCharlie default",
            "FROM[Charlie] probe AliceBob",
            "TO[Bob] loop AliceBob default",
            "FROM[Charlie] loop AliceBob default",
          ]);
        });
    
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
        });
        it('Bob has some probes', () => {
          expect(bob.getProbes()).toEqual({
            AliceBob: { Alice: true, Charlie: true },
            BobCharlie: { Alice: true, Charlie: true },
            CharlieAlice: { Alice: true, Charlie: true }
          }); 
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'AliceBob',
            'BobCharlie',
            'CharlieAlice'
          ].sort());
        });
        it('Bob has sent and received some messages', () => {
          expect(bob.getMessageLog()).toEqual([
            "FROM[Alice] meet",
            "FROM[Alice] probe AliceBob",
            "TO[Charlie] meet",
            "TO[Alice] probe BobCharlie",
            "TO[Charlie] probe BobCharlie",
            "TO[Charlie] probe AliceBob",
            "FROM[Charlie] probe CharlieAlice",
            "TO[Alice] probe CharlieAlice",
            "FROM[Charlie] loop CharlieAlice default",
            "TO[Alice] loop CharlieAlice default",
            "FROM[Alice] loop BobCharlie default",
            "TO[Charlie] loop BobCharlie default",
            "FROM[Alice] loop AliceBob default",
            "TO[Charlie] loop AliceBob default",
          ]);
        });
  
        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
        });
        it('Charlie has some probes', () => {
          expect(charlie.getProbes()).toEqual({
            AliceBob: { Alice: true, Bob: true },
            BobCharlie: { Alice: true, Bob: true },
            CharlieAlice: { Alice: true, Bob: true }
          });
        });
        it('Charlie has 3 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            'AliceBob',
            'BobCharlie',
            'CharlieAlice'
          ].sort());
        });
        it('Charlie has sent and received some messages', () => {
          expect(charlie.getMessageLog()).toEqual([
            "FROM[Bob] meet",
            "FROM[Bob] probe BobCharlie",
            "FROM[Bob] probe AliceBob",
            "TO[Alice] meet",
            "TO[Bob] probe CharlieAlice",
            "FROM[Alice] probe CharlieAlice",
            "TO[Bob] loop CharlieAlice default",
            "FROM[Alice] loop CharlieAlice default",
            "TO[Alice] probe BobCharlie",
            "FROM[Bob] loop BobCharlie default",
            "TO[Alice] loop BobCharlie default",
            "TO[Alice] probe AliceBob",
            "FROM[Bob] loop AliceBob default",
            "TO[Alice] loop AliceBob default"
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
        AliceBobCharlieAlice: { Bob: true, Charlie: true }
      });
    });
    it('Alice has 1 loop', () => {
      expect(alice.getLoops().sort()).toEqual([
        'AliceBobCharlieAlice'
      ].sort());
    });

    it('Bob is friends with Alice and Charlie', () => {
      expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
      expect(bob.getProbes()).toEqual({
        AliceBobCharlieAlice: { Alice: true, Charlie: true }
      }); 
    });
    it('Bob has 1 loop', () => {
      expect(bob.getLoops().sort()).toEqual([
        'AliceBobCharlieAlice'
      ].sort());
    });

    it('Charlie is friends with Bob and Alice', () => {
      expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
      expect(charlie.getProbes()).toEqual({
        AliceBobCharlieAlice: { Alice: true, Bob: true }
      });
    });
    it('Charlie has 1 loop', () => {
      expect(charlie.getLoops().sort()).toEqual([
        'AliceBobCharlieAlice'
      ].sort());
    });
    it('Alice has sent and received some messages', () => {
      expect(alice.getMessageLog()).toEqual([
        'TO[Bob] meet',
        'TO[Bob] probe AliceBobCharlieAlice',
        "FROM[Charlie] meet",
        "FROM[Charlie] probe AliceBobCharlieAlice",
        "TO[Bob] loop AliceBobCharlieAlice default",
        "FROM[Charlie] loop AliceBobCharlieAlice default",
      ]);
    });
    it('Bob has sent and received some messages', () => {
      expect(bob.getMessageLog()).toEqual([
        "FROM[Alice] meet",
        "FROM[Alice] probe AliceBobCharlieAlice",
        "TO[Charlie] meet",
        "TO[Charlie] probe AliceBobCharlieAlice",
        "FROM[Alice] loop AliceBobCharlieAlice default",
        "TO[Charlie] loop AliceBobCharlieAlice default",
      ]);
    });
    it('Charlie has sent and received some messages', () => {
      expect(charlie.getMessageLog()).toEqual([
        "FROM[Bob] meet",
        "FROM[Bob] probe AliceBobCharlieAlice",
        "TO[Alice] meet",
        "TO[Alice] probe AliceBobCharlieAlice",
        "FROM[Bob] loop AliceBobCharlieAlice default",
        "TO[Alice] loop AliceBobCharlieAlice default",
      ]);
    }); // Charlie has sent and received some messages
  }); // Alice meest Bob meets Charlie meets Alice
}); // basic salmon triangle
