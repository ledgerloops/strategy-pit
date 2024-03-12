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

describe('Basic Pelican Triangle - step-by-step', () => {
  // let Pelican: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  beforeAll(async () => {
    const { Pelican } = await import('../src/main.js');
    alice = new Pelican('Alice');
    bob = new Pelican('Bob');
    charlie = new Pelican('Charlie');
  });

  describe('Alice meets Bob', () => {
    beforeAll(() => {
      alice.meet(bob);
    });
    it('Alice is friends with Bob', () => {
      expect(alice.getFriends()).toEqual(['Bob']);
    });
    it('Alice has a probe for Bob', () => {
      expect(alice.getProbes()).toEqual({
        genRanHex0: { Bob: true }
      });
    });
    it('Alice has no loops', () => {
      expect(alice.getLoops()).toEqual([]);
    });
    it('Alice has sent and received some messages', () => {
      expect(alice.getMessageLog()).toEqual([
        'TO[Bob] meet',
        'TO[Bob] probe genRanHex0'
     ]);
    });
    it('Bob is friends with Alice', () => {
      expect(bob.getFriends()).toEqual(['Alice']);
    });
    it('Bob has an genRanHex0 probe with Alice', () => {
      expect(bob.getProbes()).toEqual({
        genRanHex0: { Alice: true }
      });
    });
    it('Bob has no loops', () => {
      expect(bob.getLoops()).toEqual([]);
    });

    it('Bob has sent and received some messages', () => {
      expect(bob.getMessageLog()).toEqual([
        "FROM[Alice] meet",
        "FROM[Alice] probe genRanHex0",
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
        expect(alice.getFriends()).toEqual(['Bob']);
      });
      it('Alice has some probes', () => {
        expect(alice.getProbes()).toEqual({
          genRanHex0: { Bob: true },
          genRanHex1: { Bob: true }
        });
      });
      it('Alice has no loops', () => {
        expect(alice.getLoops()).toEqual([]);
      });
      it('Alice has sent and received some messages', () => {
        expect(alice.getMessageLog()).toEqual([
          'TO[Bob] meet',
          'TO[Bob] probe genRanHex0',
          "FROM[Bob] probe genRanHex1",
       ]);
      });
 
      it('Bob is friends with Alice and Charlie', () => {
        expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
      });
      it('Bob has some probes', () => {
        expect(bob.getProbes()).toEqual({
          genRanHex0: { Alice: true, Charlie: true },
          genRanHex1: { Alice: true, Charlie: true }
        });
      });
      it('Bob has no loops', () => {
        expect(bob.getLoops()).toEqual([]);
      });
      it('Bob has sent and received some messages', () => {
        expect(bob.getMessageLog()).toEqual([
          "FROM[Alice] meet",
          "FROM[Alice] probe genRanHex0",
          "TO[Charlie] meet",
          "TO[Alice] probe genRanHex1",
          "TO[Charlie] probe genRanHex1",
          "TO[Charlie] probe genRanHex0",
       ]);
      });
 
      it('Charlie is friends with Bob', () => {
        expect(charlie.getFriends()).toEqual(['Bob']);
      });
      it('Charlie has some probes', () => {
        expect(charlie.getProbes()).toEqual({
          genRanHex0: { Bob: true },
          genRanHex1: { Bob: true }
        });
      });
      it('Charlie has no loops', () => {
        expect(charlie.getLoops()).toEqual([]);
      }); 
      it('Charlie has sent and received some messages', () => {
        expect(charlie.getMessageLog()).toEqual([
          "FROM[Bob] meet",
          "FROM[Bob] probe genRanHex1",
          "FROM[Bob] probe genRanHex0",
       ]);
      });
 
      describe('Charlie meets Alice', () => {
        beforeAll(() => {
          charlie.meet(alice);
        });

        it('Alice is friends with Bob and Charlie', () => {
          expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
        });
        it('Alice has some probes', () => {
          expect(alice.getProbes()).toEqual({
            genRanHex0: { Bob: true, Charlie: true },
            genRanHex1: { Bob: true, Charlie: true },
            genRanHex2: { Bob: true, Charlie: true }
          });
        });
        it('Alice has 3 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            'genRanHex0:genRanHex9',
            'genRanHex1:genRanHex6',
            'genRanHex2:genRanHex3'
         ].sort());
        });
        it('Alice has sent and received some messages', () => {
          expect(alice.getMessageLog()).toEqual([
            'TO[Bob] meet',
            'TO[Bob] probe genRanHex0',
            "FROM[Bob] probe genRanHex1",
            "FROM[Charlie] meet",
            "FROM[Bob] probe genRanHex2",
            "TO[Charlie] probe genRanHex2",
            "FROM[Bob] loop genRanHex2 genRanHex3",
            "TO[Charlie] loop genRanHex2 genRanHex3",
            "FROM[Charlie] probe genRanHex1",
            "TO[Bob] loop genRanHex1 genRanHex6",
            "FROM[Charlie] loop genRanHex1 genRanHex6",
            "FROM[Charlie] probe genRanHex0",
            "TO[Bob] loop genRanHex0 genRanHex9",
            "FROM[Charlie] loop genRanHex0 genRanHex9",
         ]);
        });

        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
        });
        it('Bob has some probes', () => {
          expect(bob.getProbes()).toEqual({
            genRanHex0: { Alice: true, Charlie: true },
            genRanHex1: { Alice: true, Charlie: true },
            genRanHex2: { Alice: true, Charlie: true }
          });
        });
        it('Bob has 3 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'genRanHex0:genRanHex9',
            'genRanHex1:genRanHex6',
            'genRanHex2:genRanHex3'
         ].sort());
        });
        it('Bob has sent and received some messages', () => {
          expect(bob.getMessageLog()).toEqual([
            "FROM[Alice] meet",
            "FROM[Alice] probe genRanHex0",
            "TO[Charlie] meet",
            "TO[Alice] probe genRanHex1",
            "TO[Charlie] probe genRanHex1",
            "TO[Charlie] probe genRanHex0",
            "FROM[Charlie] probe genRanHex2",
            "TO[Alice] probe genRanHex2",
            "FROM[Charlie] loop genRanHex2 genRanHex3",
            "TO[Alice] loop genRanHex2 genRanHex3",
            "FROM[Alice] loop genRanHex1 genRanHex6",
            "TO[Charlie] loop genRanHex1 genRanHex6",
            "FROM[Alice] loop genRanHex0 genRanHex9",
            "TO[Charlie] loop genRanHex0 genRanHex9",
         ]);
        });
 
        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
        });
        it('Charlie has some probes', () => {
          expect(charlie.getProbes()).toEqual({
            genRanHex0: { Alice: true, Bob: true },
            genRanHex1: { Alice: true, Bob: true },
            genRanHex2: { Alice: true, Bob: true }
          });
        });
        it('Charlie has 3 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            'genRanHex0:genRanHex9',
            'genRanHex1:genRanHex6',
            'genRanHex2:genRanHex3',
         ].sort());
        });
        it('Charlie has sent and received some messages', () => {
          expect(charlie.getMessageLog()).toEqual([
            "FROM[Bob] meet",
            "FROM[Bob] probe genRanHex1",
            "FROM[Bob] probe genRanHex0",
            "TO[Alice] meet",
            "TO[Bob] probe genRanHex2",
            "FROM[Alice] probe genRanHex2",
            "TO[Bob] loop genRanHex2 genRanHex3",
            "FROM[Alice] loop genRanHex2 genRanHex3",
            "TO[Alice] probe genRanHex1",
            "FROM[Bob] loop genRanHex1 genRanHex6",
            "TO[Alice] loop genRanHex1 genRanHex6",
            "TO[Alice] probe genRanHex0",
            "FROM[Bob] loop genRanHex0 genRanHex9",
            "TO[Alice] loop genRanHex0 genRanHex9"
         ]);
        });
      }); // Charlie meets Alice
    }); // Bob meets Charlie
  }); // Alice meets Bob
}); // basic pelican triangle


describe('Basic Pelican Triangle - synchronous', () => {
  // let Pelican: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  beforeAll(async () => {
    const { Pelican } = await import('../src/main.js');
    alice = new Pelican('Alice');
    bob = new Pelican('Bob');
    charlie = new Pelican('Charlie');
  });

  describe('Alice meets Bob meet Charlie meets Alice', () => {
    beforeAll(() => {
      alice.meet(bob);
      bob.meet(charlie);
      charlie.meet(alice);
    });

    it('Alice is friends with Bob and Charlie', () => {
      expect(alice.getFriends()).toEqual(['Bob', 'Charlie']);
    });
    it('Alice has some probes', () => {
      expect(alice.getProbes()).toEqual({
        genRanHex12: { Bob: true, Charlie: true },
        genRanHex13: { Bob: true, Charlie: true },
        genRanHex14: { Bob: true, Charlie: true },
      });
    });
    it('Alice has some loops', () => {
      expect(alice.getLoops().sort()).toEqual([
        'genRanHex12:genRanHex21',
        'genRanHex13:genRanHex18',
        'genRanHex14:genRanHex15',
     ].sort());
    });

    it('Bob is friends with Alice and Charlie', () => {
      expect(bob.getFriends()).toEqual(['Alice', 'Charlie']);
    });
    it('Bob has some probes', () => {
      expect(bob.getProbes()).toEqual({
        genRanHex12: { Alice: true, Charlie: true },
        genRanHex13: { Alice: true, Charlie: true },
        genRanHex14: { Alice: true, Charlie: true },
      });
    });
    it('Bob has some loops', () => {
      expect(bob.getLoops().sort()).toEqual([
        'genRanHex12:genRanHex21',
        'genRanHex13:genRanHex18',
        'genRanHex14:genRanHex15',
     ].sort());
    });

    it('Charlie is friends with Bob and Alice', () => {
      expect(charlie.getFriends()).toEqual(['Bob', 'Alice']);
    });
    it('Charlie has some probes', () => {
      expect(charlie.getProbes()).toEqual({
        genRanHex12: { Alice: true, Bob: true },
        genRanHex13: { Alice: true, Bob: true },
        genRanHex14: { Alice: true, Bob: true },
      });
    });
    it('Charlie has 1 loop', () => {
      expect(charlie.getLoops().sort()).toEqual([
        'genRanHex12:genRanHex21',
        'genRanHex13:genRanHex18',
        'genRanHex14:genRanHex15',
     ].sort());
    });
    it('Alice has sent and received some messages', () => {
      expect(alice.getMessageLog()).toEqual([
        'TO[Bob] meet',
        'TO[Bob] probe genRanHex12',
        'FROM[Bob] probe genRanHex13',
        "FROM[Charlie] meet",
        "FROM[Bob] probe genRanHex14",
        "TO[Charlie] probe genRanHex14",
        "FROM[Bob] loop genRanHex14 genRanHex15",
        "TO[Charlie] loop genRanHex14 genRanHex15",
        "FROM[Charlie] probe genRanHex13",
        "TO[Bob] loop genRanHex13 genRanHex18",
        "FROM[Charlie] loop genRanHex13 genRanHex18",
        "FROM[Charlie] probe genRanHex12",
        "TO[Bob] loop genRanHex12 genRanHex21",
        "FROM[Charlie] loop genRanHex12 genRanHex21",
     ]);
    });
    it('Bob has sent and received some messages', () => {
      expect(bob.getMessageLog()).toEqual([
        "FROM[Alice] meet",
        "FROM[Alice] probe genRanHex12",
        "TO[Charlie] meet",
        "TO[Alice] probe genRanHex13",
        "TO[Charlie] probe genRanHex13",
        "TO[Charlie] probe genRanHex12",
        "FROM[Charlie] probe genRanHex14",
        "TO[Alice] probe genRanHex14",
        "FROM[Charlie] loop genRanHex14 genRanHex15",
        "TO[Alice] loop genRanHex14 genRanHex15",
        "FROM[Alice] loop genRanHex13 genRanHex18",
        "TO[Charlie] loop genRanHex13 genRanHex18",
        "FROM[Alice] loop genRanHex12 genRanHex21",
        "TO[Charlie] loop genRanHex12 genRanHex21",
     ]);
    });
    it('Charlie has sent and received some messages', () => {
      expect(charlie.getMessageLog()).toEqual([
        "FROM[Bob] meet",
        "FROM[Bob] probe genRanHex13",
        "FROM[Bob] probe genRanHex12",
        "TO[Alice] meet",
        "TO[Bob] probe genRanHex14",
        "FROM[Alice] probe genRanHex14",
        "TO[Bob] loop genRanHex14 genRanHex15",
        "FROM[Alice] loop genRanHex14 genRanHex15",
        "TO[Alice] probe genRanHex13",
        "FROM[Bob] loop genRanHex13 genRanHex18",
        "TO[Alice] loop genRanHex13 genRanHex18",
        "TO[Alice] probe genRanHex12",
        "FROM[Bob] loop genRanHex12 genRanHex21",
        "TO[Alice] loop genRanHex12 genRanHex21",
     ]);
    }); // Charlie has sent and received some messages
  }); // Alice meest Bob meets Charlie meets Alice
}); // basic pelican triangle
