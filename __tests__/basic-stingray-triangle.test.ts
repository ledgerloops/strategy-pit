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
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic stingray triangle
