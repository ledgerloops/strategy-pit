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
const { Pelican, MessageLogger } = await import('../src/main.js');

const triangleMessages = [
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex1",
  "[Bob]->[Charlie] meet",
  "[Bob]->[Alice] probe genRanHex2",
  "[Bob]->[Charlie] probe genRanHex2",
  "[Bob]->[Charlie] probe genRanHex1",
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Bob] probe genRanHex3",
  "[Bob]->[Alice] probe genRanHex3",
  "[Alice]->[Charlie] probe genRanHex3",
  "[Charlie]->[Bob] loop genRanHex3 genRanHex3",
  "[Bob]->[Alice] loop genRanHex3 genRanHex3",
  "[Alice]->[Charlie] loop genRanHex3 genRanHex3",
  "[Charlie]->[Alice] probe genRanHex2",
  "[Alice]->[Bob] loop genRanHex2 genRanHex3",
  "[Bob]->[Charlie] loop genRanHex2 genRanHex3",
  "[Charlie]->[Alice] loop genRanHex2 genRanHex3",
  "[Charlie]->[Alice] probe genRanHex1",
  "[Alice]->[Bob] loop genRanHex1 genRanHex3",
  "[Bob]->[Charlie] loop genRanHex1 genRanHex3",
  "[Charlie]->[Alice] loop genRanHex1 genRanHex3",
  "[Alice]->[Dave] meet",
  "[Alice]->[Bob] probe genRanHex4",
  "[Bob]->[Charlie] probe genRanHex4",
  "[Charlie]->[Alice] probe genRanHex4",
  "[Alice]->[Bob] loop genRanHex4 genRanHex4",
  "[Bob]->[Charlie] loop genRanHex4 genRanHex4",
  "[Charlie]->[Alice] loop genRanHex4 genRanHex4",
];
const messagesgenRanHex4 = [
    "[Alice]->[Dave] probe genRanHex4",
];
const messagesgenRanHex5 = [
  "[Dave]->[Edward] meet",
  "[Dave]->[Alice] probe genRanHex5",
  "[Alice]->[Bob] probe genRanHex5",
  "[Bob]->[Charlie] probe genRanHex5",
  "[Charlie]->[Alice] probe genRanHex5",
  "[Alice]->[Dave] loop genRanHex5 genRanHex5",
  "[Alice]->[Bob] loop genRanHex5 genRanHex5",
  "[Bob]->[Charlie] loop genRanHex5 genRanHex5",
  "[Charlie]->[Alice] loop genRanHex5 genRanHex5",
  "[Dave]->[Edward] probe genRanHex5",
  "[Dave]->[Edward] probe genRanHex4",
];
const messagesgenRanHex9 = [
   "[Edward]->[Alice] meet",
   "[Edward]->[Dave] probe genRanHex9",
   "[Dave]->[Alice] probe genRanHex9",
   "[Alice]->[Bob] probe genRanHex9",
   "[Bob]->[Charlie] probe genRanHex9",
   "[Charlie]->[Alice] probe genRanHex9",
   "[Alice]->[Dave] loop genRanHex9 genRanHex9",
   "[Dave]->[Edward] loop genRanHex9 genRanHex9",
   "[Alice]->[Bob] loop genRanHex9 genRanHex9",
   "[Bob]->[Charlie] loop genRanHex9 genRanHex9",
   "[Charlie]->[Alice] loop genRanHex9 genRanHex9",
   "[Alice]->[Edward] probe genRanHex9",
   "[Edward]->[Dave] loop genRanHex9 genRanHex9",
   "[Edward]->[Alice] probe genRanHex5",
   "[Alice]->[Dave] loop genRanHex5 genRanHex9",
   "[Dave]->[Edward] loop genRanHex5 genRanHex9",
   "[Edward]->[Alice] loop genRanHex5 genRanHex9",
   "[Alice]->[Bob] loop genRanHex5 genRanHex9",
   "[Bob]->[Charlie] loop genRanHex5 genRanHex9",
   "[Charlie]->[Alice] loop genRanHex5 genRanHex9",
   "[Alice]->[Charlie] loop genRanHex5 genRanHex9",
   "[Edward]->[Alice] probe genRanHex4",
   "[Alice]->[Bob] loop genRanHex4 genRanHex9",
   "[Bob]->[Charlie] loop genRanHex4 genRanHex9",
   "[Charlie]->[Alice] loop genRanHex4 genRanHex9",
   "[Alice]->[Charlie] loop genRanHex4 genRanHex9",
   "[Alice]->[Dave] loop genRanHex4 genRanHex9",
   "[Dave]->[Edward] loop genRanHex4 genRanHex9",
   "[Edward]->[Alice] loop genRanHex4 genRanHex9",
];

describe('Basic Pelican Hourglass', () => {
  // let Pelican: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let dave: any;
  let edward: any;
  let messageLogger: any;
  beforeAll(async () => {
    messageLogger = new MessageLogger();
    alice = new Pelican('Alice', messageLogger);
    bob = new Pelican('Bob', messageLogger);
    charlie = new Pelican('Charlie', messageLogger);
    dave = new Pelican('Dave', messageLogger);
    edward = new Pelican('Edward', messageLogger);
  });

  describe('Triangle, then Alice meets Dave', () => {
    beforeAll(() => {
      // First go through the steps of the Basic Pelican Triangle test:
      alice.meet(bob);
      bob.meet(charlie);
      charlie.meet(alice);
      // Now add Dave:
      alice.meet(dave);
    });
    it('Alice is friends with triangle + Dave', () => {
      expect(alice.getFriends().sort()).toEqual([
        'Bob',
        'Charlie',
        'Dave'
      ]);
    });
    it('Alice has the triangle probes plus an genRanHex4 probe for Dave', () => {
      expect(alice.getProbes()).toEqual({
        genRanHex1: { Bob: true, Charlie: true },
        genRanHex2: { Bob: true, Charlie: true },
        genRanHex3: { Bob: true, Charlie: true },
        genRanHex4: { Bob: true, Charlie: true, Dave: true }
      });
    });
    it('Alice has the triangle loops', () => {
      expect(alice.getLoops().sort()).toEqual([
        'genRanHex1:genRanHex3',
        'genRanHex2:genRanHex3',
        'genRanHex3:genRanHex3',
        'genRanHex4:genRanHex4'
      ].sort());
    });
    it('the message logs are as expected', () => {
      expect(messageLogger.getFullLog()).toEqual(triangleMessages.concat(messagesgenRanHex4));
    });

    describe('Dave meets Edward', () => {
      beforeAll(() => {
        dave.meet(edward);
      });
      it('Alice is friends with the triangle plus Dave', () => {
        expect(alice.getFriends().sort()).toEqual([ 'Bob', 'Charlie', 'Dave' ].sort());
      });
      it('Alice has probes for the triangle plus Dave and Edward', () => {
        expect(alice.getProbes()).toEqual({
          genRanHex1: { Bob: true, Charlie: true },
          genRanHex2: { Bob: true, Charlie: true },
          genRanHex3: { Bob: true, Charlie: true },
          genRanHex4: { Bob: true, Charlie: true, Dave: true },
          genRanHex5: { Bob: true, Charlie: true, Dave: true }
        });
      });
      it('Dave is friends with Alice and Edward', () => {
        expect(dave.getFriends().sort()).toEqual([ 'Alice', 'Edward' ].sort());
      });
      it('Dave has all the triangle probes plus one for Edward', () => {
        expect(dave.getProbes()).toEqual({
          genRanHex4: { Alice: true, Edward: true },
          genRanHex5: { Alice: true, Edward: true }
        });
      });
      it('Edward is friends with Dave', () => {
        expect(edward.getFriends().sort()).toEqual([ 'Dave' ]);
      });
      it('Edward has all the triangle probes plus one for Dave', () => {
        expect(edward.getProbes()).toEqual({
          genRanHex4: { Dave: true },
          genRanHex5: { Dave: true }
        });
      });
      it('the message logs are as expected', () => {
        expect(messageLogger.getFullLog()).toEqual([].concat(
            triangleMessages,
            messagesgenRanHex4,
            messagesgenRanHex5
          )
        );
      });
  
   
      describe('Edward meets Alice', () => {
        beforeAll(() => {
          edward.meet(alice);
        });

        it('Alice is friends with everyone', () => {
          expect(alice.getFriends().sort()).toEqual([ 'Bob', 'Charlie', 'Dave', 'Edward' ]);
        });

        it('Alice has probes for each hourglass edge', () => {
          expect(alice.getProbes()).toEqual({
            genRanHex1: { Bob: true, Charlie: true }, // probes from the first triangle don't travel into the second triangle 
            genRanHex2: { Bob: true, Charlie: true }, // probes from the first triangle don't travel into the second triangle
            genRanHex3: { Bob: true, Charlie: true }, // probes from the first triangle don't travel into the second triangle
            genRanHex4: { Bob: true, Charlie: true, Dave: true, Edward: true },
            genRanHex5: { Bob: true, Charlie: true, Dave: true, Edward: true },
            genRanHex9: { Bob: true, Charlie: true, Dave: true, Edward: true }
          });
        });
        it('Alice has 8 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            'genRanHex1:genRanHex3',
            'genRanHex2:genRanHex3',
            'genRanHex3:genRanHex3',
            'genRanHex4:genRanHex4',
            'genRanHex4:genRanHex9',
            'genRanHex5:genRanHex5',
            'genRanHex5:genRanHex9',
            'genRanHex9:genRanHex9'
          ].sort());
        });
   
        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends().sort()).toEqual([ 'Alice', 'Charlie' ]);
        });
   
        it('Bob has one probe for each hourglass edge', () => {
          expect(bob.getProbes()).toEqual({
            genRanHex1: { Alice: true, Charlie: true },
            genRanHex2: { Alice: true, Charlie: true },
            genRanHex3: { Alice: true, Charlie: true },
            genRanHex4: { Alice: true, Charlie: true },
            genRanHex5: { Alice: true, Charlie: true },
            genRanHex9: { Alice: true, Charlie: true }
          }); 
        });
        it('Bob has 8 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'genRanHex1:genRanHex3',
            'genRanHex2:genRanHex3',
            'genRanHex3:genRanHex3',
            'genRanHex4:genRanHex4',
            'genRanHex4:genRanHex9',
            'genRanHex5:genRanHex5',
            'genRanHex5:genRanHex9',
            'genRanHex9:genRanHex9'
          ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends().sort()).toEqual([ 'Bob', 'Alice' ].sort());
        });

        it('Charlie has one probe for each hourglass edge', () => {
          expect(charlie.getProbes()).toEqual({
            genRanHex1: { Alice: true, Bob: true },
            genRanHex2: { Alice: true, Bob: true },
            genRanHex3: { Alice: true, Bob: true },
            genRanHex4: { Alice: true, Bob: true },
            genRanHex5: { Alice: true, Bob: true },
            genRanHex9: { Alice: true, Bob: true }
          });
        });
        it('Charlie has 8 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            'genRanHex1:genRanHex3',
            'genRanHex2:genRanHex3',
            'genRanHex3:genRanHex3',
            'genRanHex4:genRanHex4',
            'genRanHex4:genRanHex9',
            'genRanHex5:genRanHex5',
            'genRanHex5:genRanHex9',
            'genRanHex9:genRanHex9'
          ].sort());
        });

        it('Dave is friends with Edward and Alice', () => {
          expect(dave.getFriends().sort()).toEqual([ 'Edward', 'Alice' ].sort());
        });

        it('Dave has probes for the second triangel of the hourglass edge', () => {
          expect(dave.getProbes()).toEqual({
            // genRanHex1: { Alice: true, Edward: true },
            // genRanHex2: { Alice: true, Edward: true },
            // genRanHex3: { Alice: true, Edward: true },
            genRanHex4: { Alice: true, Edward: true },
            genRanHex5: { Alice: true, Edward: true },
            genRanHex9: { Alice: true, Edward: true }
          });
        });
        it('Dave has 3 loops', () => {
          expect(dave.getLoops().sort()).toEqual([
            // 'genRanHex1:genRanHex3',
            // 'genRanHex2:genRanHex3',
            // 'genRanHex3:genRanHex3',
            // 'genRanHex4:genRanHex4',
            'genRanHex4:genRanHex9',
            // 'genRanHex5:genRanHex5',
            'genRanHex5:genRanHex9',
            'genRanHex9:genRanHex9'
          ].sort());
        });

        it('Edward is friends with Dave and Alice', () => {
          expect(edward.getFriends().sort()).toEqual([ 'Dave', 'Alice' ].sort());
        });

        it('Edward has probes for the second triangle of the hourglass edge', () => {
          expect(edward.getProbes()).toEqual({
            // genRanHex1: { Alice: true, Dave: true },
            // genRanHex2: { Alice: true, Dave: true },
            // genRanHex3: { Alice: true, Dave: true },
            genRanHex4: { Alice: true, Dave: true },
            genRanHex5: { Alice: true, Dave: true },
            genRanHex9: { Alice: true, Dave: true }
          });
        });
        it('Edward has 3 loops', () => {
          expect(edward.getLoops().sort()).toEqual([
            // 'genRanHex1:genRanHex3',
            // 'genRanHex2:genRanHex3',
            // 'genRanHex3:genRanHex3',
            // 'genRanHex4:genRanHex4',
            'genRanHex4:genRanHex9',
            // 'genRanHex5:genRanHex5',
            'genRanHex5:genRanHex9',
            'genRanHex9:genRanHex9'
          ].sort());
        });
        it('the message logs are as expected', () => {
          expect(messageLogger.getFullLog()).toEqual([].concat(
            triangleMessages,
            messagesgenRanHex4,
            messagesgenRanHex5,
            messagesgenRanHex9
          )
        );
        });
    
      }); // Edward meets Alice
    }); // Dave meets Edward
  }); // Alice meets Dave
}); // basic pelican hourglass
