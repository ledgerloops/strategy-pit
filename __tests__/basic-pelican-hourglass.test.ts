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
const { Pelican, MessageLogger } = await import('../src/main.js');

const triangleMessages = [
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe AliceBob",
  "[Bob]->[Charlie] meet",
  "[Bob]->[Alice] probe BobCharlie",
  "[Bob]->[Charlie] probe BobCharlie",
  "[Bob]->[Charlie] probe AliceBob",
  "[Charlie]->[Alice] meet",
  "[Charlie]->[Bob] probe CharlieAlice",
  "[Bob]->[Alice] probe CharlieAlice",
  "[Alice]->[Charlie] probe CharlieAlice",
  "[Charlie]->[Bob] loop CharlieAlice CharlieAlice",
  "[Bob]->[Alice] loop CharlieAlice CharlieAlice",
  "[Alice]->[Charlie] loop CharlieAlice CharlieAlice",
  "[Charlie]->[Alice] probe BobCharlie",
  "[Alice]->[Bob] loop BobCharlie CharlieAlice",
  "[Bob]->[Charlie] loop BobCharlie CharlieAlice",
  "[Charlie]->[Alice] loop BobCharlie CharlieAlice",
  "[Charlie]->[Alice] probe AliceBob",
  "[Alice]->[Bob] loop AliceBob CharlieAlice",
  "[Bob]->[Charlie] loop AliceBob CharlieAlice",
  "[Charlie]->[Alice] loop AliceBob CharlieAlice",
  "[Alice]->[Dave] meet",
  "[Alice]->[Bob] probe AliceDave",
  "[Bob]->[Charlie] probe AliceDave",
  "[Charlie]->[Alice] probe AliceDave",
  "[Alice]->[Bob] loop AliceDave AliceDave",
  "[Bob]->[Charlie] loop AliceDave AliceDave",
  "[Charlie]->[Alice] loop AliceDave AliceDave",
];
const messagesAliceDave = [
    "[Alice]->[Dave] probe AliceDave",
];
const messagesDaveEdward = [
  "[Dave]->[Edward] meet",
  "[Dave]->[Alice] probe DaveEdward",
  "[Alice]->[Bob] probe DaveEdward",
  "[Bob]->[Charlie] probe DaveEdward",
  "[Charlie]->[Alice] probe DaveEdward",
  "[Alice]->[Dave] loop DaveEdward DaveEdward",
  "[Alice]->[Bob] loop DaveEdward DaveEdward",
  "[Bob]->[Charlie] loop DaveEdward DaveEdward",
  "[Charlie]->[Alice] loop DaveEdward DaveEdward",
  "[Dave]->[Edward] probe DaveEdward",
  "[Dave]->[Edward] probe AliceDave",
];
const messagesEdwardAlice = [
   "[Edward]->[Alice] meet",
   "[Edward]->[Dave] probe EdwardAlice",
   "[Dave]->[Alice] probe EdwardAlice",
   "[Alice]->[Bob] probe EdwardAlice",
   "[Bob]->[Charlie] probe EdwardAlice",
   "[Charlie]->[Alice] probe EdwardAlice",
   "[Alice]->[Dave] loop EdwardAlice EdwardAlice",
   "[Dave]->[Edward] loop EdwardAlice EdwardAlice",
   "[Alice]->[Bob] loop EdwardAlice EdwardAlice",
   "[Bob]->[Charlie] loop EdwardAlice EdwardAlice",
   "[Charlie]->[Alice] loop EdwardAlice EdwardAlice",
   "[Alice]->[Edward] probe EdwardAlice",
   "[Edward]->[Dave] loop EdwardAlice EdwardAlice",
   "[Edward]->[Alice] probe DaveEdward",
   "[Alice]->[Dave] loop DaveEdward EdwardAlice",
   "[Dave]->[Edward] loop DaveEdward EdwardAlice",
   "[Edward]->[Alice] loop DaveEdward EdwardAlice",
   "[Alice]->[Bob] loop DaveEdward EdwardAlice",
   "[Bob]->[Charlie] loop DaveEdward EdwardAlice",
   "[Charlie]->[Alice] loop DaveEdward EdwardAlice",
   "[Alice]->[Charlie] loop DaveEdward EdwardAlice",
   "[Edward]->[Alice] probe AliceDave",
   "[Alice]->[Bob] loop AliceDave EdwardAlice",
   "[Bob]->[Charlie] loop AliceDave EdwardAlice",
   "[Charlie]->[Alice] loop AliceDave EdwardAlice",
   "[Alice]->[Charlie] loop AliceDave EdwardAlice",
   "[Alice]->[Dave] loop AliceDave EdwardAlice",
   "[Dave]->[Edward] loop AliceDave EdwardAlice",
   "[Edward]->[Alice] loop AliceDave EdwardAlice",
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
    it('the message logs are as expected', () => {
      expect(messageLogger.getFullLog()).toEqual(triangleMessages.concat(messagesAliceDave));
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
          AliceBob: { Bob: true, Charlie: true },
          BobCharlie: { Bob: true, Charlie: true },
          CharlieAlice: { Bob: true, Charlie: true },
          AliceDave: { Bob: true, Charlie: true, Dave: true },
          DaveEdward: { Bob: true, Charlie: true, Dave: true }
        });
      });
      it('Dave is friends with Alice and Edward', () => {
        expect(dave.getFriends().sort()).toEqual([ 'Alice', 'Edward' ].sort());
      });
      it('Dave has all the triangle probes plus one for Edward', () => {
        expect(dave.getProbes()).toEqual({
          AliceDave: { Alice: true, Edward: true },
          DaveEdward: { Alice: true, Edward: true }
        });
      });
      it('Edward is friends with Dave', () => {
        expect(edward.getFriends().sort()).toEqual([ 'Dave' ]);
      });
      it('Edward has all the triangle probes plus one for Dave', () => {
        expect(edward.getProbes()).toEqual({
          AliceDave: { Dave: true },
          DaveEdward: { Dave: true }
        });
      });
      it('the message logs are as expected', () => {
        expect(messageLogger.getFullLog()).toEqual([].concat(
            triangleMessages,
            messagesAliceDave,
            messagesDaveEdward
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
          expect(bob.getFriends().sort()).toEqual([ 'Alice', 'Charlie' ]);
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
          expect(charlie.getFriends().sort()).toEqual([ 'Bob', 'Alice' ].sort());
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

        it('Dave is friends with Edward and Alice', () => {
          expect(dave.getFriends().sort()).toEqual([ 'Edward', 'Alice' ].sort());
        });

        it('Dave has probes for the second triangel of the hourglass edge', () => {
          expect(dave.getProbes()).toEqual({
            // AliceBob: { Alice: true, Edward: true },
            // BobCharlie: { Alice: true, Edward: true },
            // CharlieAlice: { Alice: true, Edward: true },
            AliceDave: { Alice: true, Edward: true },
            DaveEdward: { Alice: true, Edward: true },
            EdwardAlice: { Alice: true, Edward: true }
          });
        });
        it('Dave has 3 loops', () => {
          expect(dave.getLoops().sort()).toEqual([
            // 'AliceBob:CharlieAlice',
            // 'BobCharlie:CharlieAlice',
            // 'CharlieAlice:CharlieAlice',
            // 'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            // 'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });

        it('Edward is friends with Dave and Alice', () => {
          expect(edward.getFriends().sort()).toEqual([ 'Dave', 'Alice' ].sort());
        });

        it('Edward has probes for the second triangle of the hourglass edge', () => {
          expect(edward.getProbes()).toEqual({
            // AliceBob: { Alice: true, Dave: true },
            // BobCharlie: { Alice: true, Dave: true },
            // CharlieAlice: { Alice: true, Dave: true },
            AliceDave: { Alice: true, Dave: true },
            DaveEdward: { Alice: true, Dave: true },
            EdwardAlice: { Alice: true, Dave: true }
          });
        });
        it('Edward has 3 loops', () => {
          expect(edward.getLoops().sort()).toEqual([
            // 'AliceBob:CharlieAlice',
            // 'BobCharlie:CharlieAlice',
            // 'CharlieAlice:CharlieAlice',
            // 'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            // 'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });
        it('the message logs are as expected', () => {
          expect(messageLogger.getFullLog()).toEqual([].concat(
            triangleMessages,
            messagesAliceDave,
            messagesDaveEdward,
            messagesEdwardAlice
          )
        );
        });
    
      }); // Edward meets Alice
    }); // Dave meets Edward
  }); // Alice meets Dave
}); // basic pelican hourglass
