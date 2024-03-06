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
    const { Pelican } = await import('../src/main.js');
    stage = 'already-friends-test';
    const alice = new Pelican('Alice');
    const bob = new Pelican('Bob');

    alice.meet(bob);
    expect(() => alice.meet(bob)).toThrow('Alice is already friends with Bob');
  });
});

describe('Basic Pelican Hourglass', () => {
  // let Pelican: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let dave: any;
  let edward: any;

  beforeAll(async () => {
    jest.unstable_mockModule('../src/util.js', () => {
      return{
        genRanHex: jest.fn((): string => {
          return stage
        })
      };
    });
    const { Pelican } = await import('../src/main.js');
    stage = "hourglass-setup"
    alice = new Pelican('Alice');
    bob = new Pelican('Bob');
    charlie = new Pelican('Charlie');
    dave = new Pelican('Dave');
    edward = new Pelican('Edward');
  });

  describe('Triangle, then Alice meets Dave', () => {
    beforeAll(() => {
      // First go through the steps of the Basic Pelican Triangle test:
      stage = "AliceBob";
      alice.meet(bob);
      stage = "BobCharlie";
      bob.meet(charlie);
      stage = "CharlieAlice";
      charlie.meet(alice);
      // Now add Dave:
      stage = "AliceDave";
      alice.meet(dave);
    });
    it('Alice is friends with triangle + Dave', () => {
      expect(alice.getFriends()).toEqual([
        'Bob',
        'Charlie',
        'Dave'
      ]);
    });
    it('Alice has the triangle probes plus an AliceDave probe for Dave', () => {
      expect(alice.getProbes()).toEqual({
        AliceBob: { Bob: true, Charlie: true },
        BobCharlie: { Bob: true, Charlie: true },
        CharlieAlice: { Bob: true, Charlie: true },
        AliceDave: { Bob: true, Charlie: true, Dave: true }
      });
    });
    it('Alice has the triangle loops', () => {
      expect(alice.getLoops().sort()).toEqual([
        'AliceBob:CharlieAlice',
        'BobCharlie:CharlieAlice',
        'CharlieAlice:CharlieAlice',
        'AliceDave:AliceDave'
      ].sort());
    });

    describe('Dave meets Edward', () => {
      beforeAll(() => {
        stage = "DaveEdward";
        dave.meet(edward);
      });
      it('Alice is friends with the triangle plus Dave', () => {
        expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie', 'Dave' ]);
      });
      it('Alice has probes for the triangle plus Dave and Edward', () => {
        expect(alice.getProbes()).toEqual({
          AliceBob: { Bob: true, Charlie: true },
          BobCharlie: { Bob: true, Charlie: true },
          CharlieAlice: { Bob: true, Charlie: true },
          AliceDave: { Bob: true, Charlie: true, Dave: true },
          DaveEdward: { Bob: true, Charlie: true, Dave: true }
        });
      });
      it('Dave is friends with Alice and Edward', () => {
        expect(dave.getFriends()).toEqual([ 'Alice', 'Edward' ]);
      });
      it('Dave has all the triangle probes plus one for Edward', () => {
        expect(dave.getProbes()).toEqual({
          AliceDave: { Alice: true, Edward: true },
          DaveEdward: { Alice: true, Edward: true }
        });
      });
      it('Edward is friends with Dave', () => {
        expect(edward.getFriends()).toEqual([ 'Dave' ]);
      });
      it('Edward has all the triangle probes plus one for Dave', () => {
        expect(edward.getProbes()).toEqual({
          AliceDave: { Dave: true },
          DaveEdward: { Dave: true }
        });
      });
   
      describe('Edward meets Alice', () => {
        beforeAll(() => {
          stage = "EdwardAlice";
          edward.meet(alice);
        });

        it('Alice is friends with everyone', () => {
          expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie', 'Dave', 'Edward' ]);
        });

        it('Alice has probes for each hourglass edge', () => {
          expect(alice.getProbes()).toEqual({
            AliceBob: { Bob: true, Charlie: true }, // probes from the first triangle don't travel into the second triangle 
            BobCharlie: { Bob: true, Charlie: true }, // probes from the first triangle don't travel into the second triangle
            CharlieAlice: { Bob: true, Charlie: true }, // probes from the first triangle don't travel into the second triangle
            AliceDave: { Bob: true, Charlie: true, Dave: true, Edward: true },
            DaveEdward: { Bob: true, Charlie: true, Dave: true, Edward: true },
            EdwardAlice: { Bob: true, Charlie: true, Dave: true, Edward: true }
          });
        });
        it('Alice has 8 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            'AliceBob:CharlieAlice',
            'BobCharlie:CharlieAlice',
            'CharlieAlice:CharlieAlice',
            'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });
   
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
        });
   
        it('Bob has one probe for each hourglass edge', () => {
          expect(bob.getProbes()).toEqual({
            AliceBob: { Alice: true, Charlie: true },
            BobCharlie: { Alice: true, Charlie: true },
            CharlieAlice: { Alice: true, Charlie: true },
            AliceDave: { Alice: true, Charlie: true },
            DaveEdward: { Alice: true, Charlie: true },
            EdwardAlice: { Alice: true, Charlie: true }
          }); 
        });
        it('Bob has 8 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'AliceBob:CharlieAlice',
            'BobCharlie:CharlieAlice',
            'CharlieAlice:CharlieAlice',
            'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
        });

        it('Charlie has one probe for each hourglass edge', () => {
          expect(charlie.getProbes()).toEqual({
            AliceBob: { Alice: true, Bob: true },
            BobCharlie: { Alice: true, Bob: true },
            CharlieAlice: { Alice: true, Bob: true },
            AliceDave: { Alice: true, Bob: true },
            DaveEdward: { Alice: true, Bob: true },
            EdwardAlice: { Alice: true, Bob: true }
          });
        });
        it('Charlie has 8 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            'AliceBob:CharlieAlice',
            'BobCharlie:CharlieAlice',
            'CharlieAlice:CharlieAlice',
            'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });
      }); // Edward meets Alice
    }); // Dave meets Edward
  }); // Alice meets Dave
}); // basic pelican hourglass
