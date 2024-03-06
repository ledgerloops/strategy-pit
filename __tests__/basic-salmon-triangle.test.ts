/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

let stage: string = "setup";

describe('already friends', () => {
  it('throws an error', async () => {
    jest.unstable_mockModule('../src/util.js', () => {
      return{
        genRanHex: jest.fn((): string => {
          return stage
        })
      };
    });
    const { Salmon } = await import('../src/main.js');
    stage = 'already-friends-test';
    const alice = new Salmon('Alice');
    const bob = new Salmon('Bob');

    alice.meet(bob);
    expect(() => alice.meet(bob)).toThrow('Alice is already friends with Bob');
  });
});

describe('Basic Salmon Triangle', () => {
  // let Salmon: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  beforeAll(async () => {
    jest.unstable_mockModule('../src/util.js', () => {
      return{
        genRanHex: jest.fn((): string => {
          return stage
        })
      };
    });
    const { Salmon } = await import('../src/main.js');
    stage = "triangle-setup"
    alice = new Salmon('Alice');
    bob = new Salmon('Bob');
    charlie = new Salmon('Charlie');
  });

  describe('Alice and Bob meet', () => {
    beforeAll(() => {
      stage = "AliceBob";
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
    it('Bob is friends with Alice', () => {
      expect(bob.getFriends()).toEqual([ 'Alice' ]);
      expect(bob.getProbes()).toEqual({
        AliceBob: { Alice: true }
      });
    });
    it('Charlie is friends with nobody', () => {
      expect(charlie.getFriends()).toEqual([]);
      expect(charlie.getProbes()).toEqual({
      });
    });

    describe('Bob and Charlie meet', () => {
      beforeAll(() => {
        stage = "BobCharlie";
        bob.meet(charlie);
      });
      it('Alice is friends with Bob', () => {
        expect(alice.getFriends()).toEqual([ 'Bob' ]);
        expect(alice.getProbes()).toEqual({
          AliceBob: { Bob: true },
          BobCharlie: { Bob: true }
        });
      });
      it('Alice has no loops', () => {
        expect(alice.getLoops()).toEqual([]);
      }); 
      it('Bob is friends with Alice and Charlie', () => {
        expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
        expect(bob.getProbes()).toEqual({
          AliceBob: { Alice: true, Charlie: true },
          BobCharlie: { Alice: true, Charlie: true }
        });
      });
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual([ 'Bob' ]);
        expect(charlie.getProbes()).toEqual({
          AliceBob: { Bob: true },
          BobCharlie: { Bob: true }
        });
      });
   
      describe('Charlie and Alice meet', () => {
        beforeAll(() => {
          stage = "CharlieAlice";
          charlie.meet(alice);
        });

        it('Alice is friends with Bob and Charlie', () => {
          expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
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
   
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
          expect(bob.getProbes()).toEqual({
            AliceBob: { Alice: true, Charlie: true },
            BobCharlie: { Alice: true, Charlie: true },
            CharlieAlice: { Alice: true, Charlie: true }
          }); 
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'CharlieAlice',
            'BobCharlie',
            'AliceBob'
          ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
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
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // triangle
