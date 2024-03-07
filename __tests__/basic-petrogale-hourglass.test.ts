/* eslint-disable @typescript-eslint/no-explicit-any */

import { jest } from '@jest/globals';

const triangleMessages = [
  // Alice meets Bob
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe AliceBob",
  // Bob meets Charlie
  "[Bob]->[Charlie] meet",
  // | New probe back
  "[Bob]->[Alice] probe BobCharlie",
  // | Probes forward
  "[Bob]->[Charlie] probe BobCharlie",
  "[Bob]->[Charlie] probe AliceBob",
  // Charlie meets Alice
  "[Charlie]->[Alice] meet",
  // | New probe back
  "[Charlie]->[Bob] probe CharlieAlice",
  "[Bob]->[Alice] probe CharlieAlice",
  "[Alice]->[Charlie] probe CharlieAlice",
  "[Charlie]->[Bob] loop CharlieAlice CharlieAlice",
  "[Bob]->[Alice] loop CharlieAlice CharlieAlice",
  "[Alice]->[Charlie] loop CharlieAlice CharlieAlice",
  // | Probes forward
  // | | BobCharlie
  "[Charlie]->[Alice] probe BobCharlie",
  "[Alice]->[Bob] loop BobCharlie CharlieAlice",
  "[Bob]->[Charlie] loop BobCharlie CharlieAlice",
  "[Charlie]->[Alice] loop BobCharlie CharlieAlice",
  // | | AliceBob
  "[Charlie]->[Alice] probe AliceBob",
  "[Alice]->[Bob] loop AliceBob CharlieAlice",
  "[Bob]->[Charlie] loop AliceBob CharlieAlice",
  "[Charlie]->[Alice] loop AliceBob CharlieAlice",
];
const messagesAliceDave = [
  // Alice meets Dave
  "[Alice]->[Dave] meet",
  // | New probe back
  "[Alice]->[Bob] probe AliceDave",
  "[Bob]->[Charlie] probe AliceDave",
  "[Charlie]->[Alice] probe AliceDave",
  "[Alice]->[Bob] loop AliceDave AliceDave",
  "[Bob]->[Charlie] loop AliceDave AliceDave",
  "[Charlie]->[Alice] loop AliceDave AliceDave",
  // | (no need to send `[Alice]->[Charlie] probe AliceDave` because it already looped back `[Charlie]->[Alice] probe AliceDave`)
  // | Probes forward
  "[Alice]->[Dave] probe AliceDave",
  "[Alice]->[Dave] probe AliceBob",
  "[Alice]->[Dave] probe BobCharlie",
  "[Alice]->[Dave] probe CharlieAlice",
];
const messagesDaveEdward = [
  // Dave meets Edward
  "[Dave]->[Edward] meet",
  // | New probe back
  // | | DaveEdward
  "[Dave]->[Alice] probe DaveEdward",
  "[Alice]->[Bob] probe DaveEdward",
  "[Bob]->[Charlie] probe DaveEdward",
  "[Charlie]->[Alice] probe DaveEdward",
  "[Alice]->[Dave] loop DaveEdward DaveEdward",
  "[Alice]->[Bob] loop DaveEdward DaveEdward",
  "[Bob]->[Charlie] loop DaveEdward DaveEdward",
  "[Charlie]->[Alice] loop DaveEdward DaveEdward",
  // | Probes forward
  "[Dave]->[Edward] probe DaveEdward",
  "[Dave]->[Edward] probe AliceDave",
  "[Dave]->[Edward] probe AliceBob",
  "[Dave]->[Edward] probe BobCharlie",
  "[Dave]->[Edward] probe CharlieAlice",
];
const messagesEdwardAlice = [
  // Edward meets Alice
  "[Edward]->[Alice] meet",
  // | New probe back
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
  // | Probes forward
  // | | DaveEdward
  "[Edward]->[Alice] probe DaveEdward",
  "[Alice]->[Dave] loop DaveEdward EdwardAlice",
  "[Dave]->[Edward] loop DaveEdward EdwardAlice",
  "[Edward]->[Alice] loop DaveEdward EdwardAlice",
  "[Alice]->[Bob] loop DaveEdward EdwardAlice",
  "[Bob]->[Charlie] loop DaveEdward EdwardAlice",
  "[Charlie]->[Alice] loop DaveEdward EdwardAlice",
  "[Alice]->[Charlie] loop DaveEdward EdwardAlice",
  // | | AliceDave
  "[Edward]->[Alice] probe AliceDave",
  "[Alice]->[Bob] loop AliceDave EdwardAlice",
  "[Bob]->[Charlie] loop AliceDave EdwardAlice",
  "[Charlie]->[Alice] loop AliceDave EdwardAlice",
  "[Alice]->[Charlie] loop AliceDave EdwardAlice",
  "[Alice]->[Dave] loop AliceDave EdwardAlice",
  "[Dave]->[Edward] loop AliceDave EdwardAlice",
  "[Edward]->[Alice] loop AliceDave EdwardAlice",
  // | | AliceBob
  "[Edward]->[Alice] probe AliceBob",
  "[Alice]->[Bob] loop AliceBob EdwardAlice",
  "[Bob]->[Charlie] loop AliceBob EdwardAlice",
  "[Charlie]->[Alice] loop AliceBob EdwardAlice",
  "[Alice]->[Charlie] loop AliceBob EdwardAlice",
  "[Alice]->[Dave] loop AliceBob EdwardAlice",
  "[Dave]->[Edward] loop AliceBob EdwardAlice",
  "[Edward]->[Alice] loop AliceBob EdwardAlice",
  // | | BobCharlie
  "[Edward]->[Alice] probe BobCharlie",
  "[Alice]->[Bob] loop BobCharlie EdwardAlice",
  "[Bob]->[Charlie] loop BobCharlie EdwardAlice",
  "[Charlie]->[Alice] loop BobCharlie EdwardAlice",
  "[Alice]->[Charlie] loop BobCharlie EdwardAlice",
  "[Alice]->[Dave] loop BobCharlie EdwardAlice",
  "[Dave]->[Edward] loop BobCharlie EdwardAlice",
  "[Edward]->[Alice] loop BobCharlie EdwardAlice",
  // | | CharlieAlice
  "[Edward]->[Alice] probe CharlieAlice",
  "[Alice]->[Bob] loop CharlieAlice EdwardAlice",
  "[Bob]->[Charlie] loop CharlieAlice EdwardAlice",
  "[Charlie]->[Alice] loop CharlieAlice EdwardAlice",
  "[Alice]->[Charlie] loop CharlieAlice EdwardAlice",
  "[Alice]->[Dave] loop CharlieAlice EdwardAlice",
  "[Dave]->[Edward] loop CharlieAlice EdwardAlice",
  "[Edward]->[Alice] loop CharlieAlice EdwardAlice",
];

let stage: string = "setup";

describe('Basic Petrogale Hourglass', () => {
  // let Petrogale: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let dave: any;
  let edward: any;
  let messageLogger: any;
  beforeAll(async () => {
    jest.unstable_mockModule('../src/util.js', () => {
      return {
        genRanHex: jest.fn((): string => {
          return stage
        })
      };
    });
    const { Petrogale, MessageLogger } = await import('../src/main.js');
    stage = "hourglass-setup"
    messageLogger = new MessageLogger();
    alice = new Petrogale('Alice', messageLogger);
    bob = new Petrogale('Bob', messageLogger);
    charlie = new Petrogale('Charlie', messageLogger);
    dave = new Petrogale('Dave', messageLogger);
    edward = new Petrogale('Edward', messageLogger);
  });

  // This creates an P topology:
  // Bob - Charlie
  //   \   /
  //    Alice
  //   /
  // Dave
  describe('Triangle, then Alice meets Dave', () => {
    beforeAll(() => {
      // First go through the steps of the Basic Petrogale Triangle test:
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
      expect(alice.getFriends().sort()).toEqual([
        'Bob',
        'Charlie',
        'Dave'
      ]);
    });
    it('Alice has the triangle probes plus an AliceDave probe for Dave', () => {
      expect(alice.getProbes()).toEqual({
        AliceBob: { Bob: true, Charlie: true, Dave: true },
        BobCharlie: { Bob: true, Charlie: true, Dave: true },
        CharlieAlice: { Bob: true, Charlie: true, Dave: true },
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

    // This creates an P topology:
    // Bob - Charlie
    //   \   /
    //    Alice
    //   /
    // Dave - Edward
    describe('Dave meets Edward', () => {
      beforeAll(() => {
        stage = "DaveEdward";
        dave.meet(edward);
      });
      it('Alice is friends with the triangle plus Dave', () => {
        expect(alice.getFriends().sort()).toEqual(['Bob', 'Charlie', 'Dave'].sort());
      });
      it('Alice has probes for the triangle plus Dave and Edward', () => {
        expect(alice.getProbes()).toEqual({
          AliceBob: { Bob: true, Charlie: true, Dave: true },
          BobCharlie: { Bob: true, Charlie: true, Dave: true },
          CharlieAlice: { Bob: true, Charlie: true, Dave: true },
          AliceDave: { Bob: true, Charlie: true, Dave: true },
          DaveEdward: { Bob: true, Charlie: true, Dave: true }
        });
      });
      it('Dave is friends with Alice and Edward', () => {
        expect(dave.getFriends().sort()).toEqual(['Alice', 'Edward'].sort());
      });
      it('Dave has all the triangle probes plus one for Edward', () => {
        expect(dave.getProbes()).toEqual({
          AliceBob: { Alice: true, Edward: true },
          BobCharlie: { Alice: true, Edward: true },
          CharlieAlice: { Alice: true, Edward: true },
          AliceDave: { Alice: true, Edward: true },
          DaveEdward: { Alice: true, Edward: true }
        });
      });
      it('Edward is friends with Dave', () => {
        expect(edward.getFriends().sort()).toEqual(['Dave']);
      });
      it('Edward has all the triangle probes plus one for Dave', () => {
        expect(edward.getProbes()).toEqual({
          AliceBob: { Dave: true },
          AliceDave: { Dave: true },
          BobCharlie: { Dave: true },
          CharlieAlice: { Dave: true },
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

      // This creates an hourglass topology:
      // Bob - Charlie
      //   \   /
      //    Alice
      //   /   \
      // Dave - Edward
      describe('Edward meets Alice', () => {
        beforeAll(() => {
          stage = "EdwardAlice";
          edward.meet(alice);
        });

        it('Alice is friends with everyone', () => {
          expect(alice.getFriends().sort()).toEqual(['Bob', 'Charlie', 'Dave', 'Edward']);
        });

        it('Alice has probes for each hourglass edge', () => {
          expect(alice.getProbes()).toEqual({
            AliceBob: { Bob: true, Charlie: true, Dave: true, Edward: true },
            BobCharlie: { Bob: true, Charlie: true, Dave: true, Edward: true },
            CharlieAlice: { Bob: true, Charlie: true, Dave: true, Edward: true },
            AliceDave: { Bob: true, Charlie: true, Dave: true, Edward: true },
            DaveEdward: { Bob: true, Charlie: true, Dave: true, Edward: true },
            EdwardAlice: { Bob: true, Charlie: true, Dave: true, Edward: true }
          });
        });
        it('Alice has 11 loops', () => {
          expect(alice.getLoops().sort()).toEqual([
            'AliceBob:CharlieAlice',
            'AliceBob:EdwardAlice',
            'BobCharlie:CharlieAlice',
            'BobCharlie:EdwardAlice',
            'CharlieAlice:CharlieAlice',
            'CharlieAlice:EdwardAlice',
            'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });

        it('Bob is friends with Alice and Charlie', () => {
          expect(bob.getFriends().sort()).toEqual(['Alice', 'Charlie']);
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
        it('Bob has 11 loops', () => {
          expect(bob.getLoops().sort()).toEqual([
            'AliceBob:CharlieAlice',
            'AliceBob:EdwardAlice',
            'BobCharlie:CharlieAlice',
            'BobCharlie:EdwardAlice',
            'CharlieAlice:CharlieAlice',
            'CharlieAlice:EdwardAlice',
            'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });

        it('Charlie is friends with Bob and Alice', () => {
          expect(charlie.getFriends().sort()).toEqual(['Bob', 'Alice'].sort());
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
        it('Charlie has 11 loops', () => {
          expect(charlie.getLoops().sort()).toEqual([
            'AliceBob:CharlieAlice',
            'AliceBob:EdwardAlice',
            'AliceDave:AliceDave',
            'AliceDave:EdwardAlice',
            'BobCharlie:CharlieAlice',
            'BobCharlie:EdwardAlice',
            'CharlieAlice:CharlieAlice',
            'CharlieAlice:EdwardAlice',
            'DaveEdward:DaveEdward',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });

        it('Dave is friends with Edward and Alice', () => {
          expect(dave.getFriends().sort()).toEqual(['Edward', 'Alice'].sort());
        });

        it('Dave has probes for the second triangel of the hourglass edge', () => {
          expect(dave.getProbes()).toEqual({
            AliceBob: { Alice: true, Edward: true },
            BobCharlie: { Alice: true, Edward: true },
            CharlieAlice: { Alice: true, Edward: true },
            AliceDave: { Alice: true, Edward: true },
            DaveEdward: { Alice: true, Edward: true },
            EdwardAlice: { Alice: true, Edward: true }
          });
        });
        it('Dave has 6 loops', () => {
          expect(dave.getLoops().sort()).toEqual([
            'AliceBob:EdwardAlice',
            'BobCharlie:EdwardAlice',
            'CharlieAlice:EdwardAlice',
            'AliceDave:EdwardAlice',
            'DaveEdward:EdwardAlice',
            'EdwardAlice:EdwardAlice'
          ].sort());
        });

        it('Edward is friends with Dave and Alice', () => {
          expect(edward.getFriends().sort()).toEqual(['Dave', 'Alice'].sort());
        });

        it('Edward has probes for the second triangle of the hourglass edge', () => {
          expect(edward.getProbes()).toEqual({
            AliceBob: { Alice: true, Dave: true },
            BobCharlie: { Alice: true, Dave: true },
            CharlieAlice: { Alice: true, Dave: true },
            AliceDave: { Alice: true, Dave: true },
            DaveEdward: { Alice: true, Dave: true },
            EdwardAlice: { Alice: true, Dave: true }
          });
        });
        it('Edward has 6 loops', () => {
          expect(edward.getLoops().sort()).toEqual([
            'AliceBob:EdwardAlice',
            'AliceDave:EdwardAlice',
            'BobCharlie:EdwardAlice',
            'CharlieAlice:EdwardAlice',
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
}); // basic petrogale hourglass
