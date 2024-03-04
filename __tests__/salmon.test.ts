import { Salmon } from '../src/salmon.js';

describe('triangle', () => {
  const alice = new Salmon('Alice');
  const bob = new Salmon('Bob');
  const charlie = new Salmon('Charlie');

  describe('Alice and Bob meet', () => {
    beforeAll(() => {
      alice.meet(bob);
      bob.meet(alice);
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
        bob.meet(charlie);
        charlie.meet(bob);
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
          charlie.meet(alice);
          alice.meet(charlie);
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
