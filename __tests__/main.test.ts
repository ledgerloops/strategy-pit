
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

describe('triangle', () => {
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
      // bob.meet(alice);
    });
    it('Alice is friends with Bob', () => {
      expect(alice.getFriends()).toEqual([ 'Bob' ]);
    }); // Alice is friends with Bob
    it('Bob is friends with Alice', () => {
      expect(bob.getFriends()).toEqual([ 'Alice' ]);
    }); // Alice is friends with Bob
    it('Charlie is friends with nobody', () => {
      expect(charlie.getFriends()).toEqual([]);
    }); // Alice is friends with Bob

    describe('Bob and Charlie meet', () => {
      beforeAll(() => {
        stage = "BobCharlie";
        bob.meet(charlie);
        // charlie.meet(bob);
      });
      it('Alice is friends with Bob', () => {
        expect(alice.getFriends()).toEqual([ 'Bob' ]);
      }); // Alice is friends with Bob
      it('Bob is friends with Alice and Charlie', () => {
        expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
      }); // Alice is friends with Bob
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual([ 'Bob' ]);
      }); // Alice is friends with Bob
    
      describe('Charlie and Alice meet', () => {
        beforeAll(() => {
          stage = "CharlieAlice";
          charlie.meet(alice);
          // alice.meet(charlie);
        });

        it('Alice is friends with Bob and Charlie', () => {
          expect(alice.getFriends()).toEqual([ 'Bob', 'Charlie' ]);
        }); // Alice is friends with Bob
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual([ 'Alice', 'Charlie' ]);
        }); // Alice is friends with Bob
        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual([ 'Bob', 'Alice' ]);
        }); // Alice is friends with Bob
        }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // triangle
