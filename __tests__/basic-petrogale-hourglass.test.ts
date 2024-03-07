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

const triangleMessages = [
  // Alice meets Bob
  "[Alice]->[Bob] meet",
  "[Alice]->[Bob] probe genRanHex0",
  // Bob meets Charlie
  "[Bob]->[Charlie] meet",
  // | New probe back
  "[Bob]->[Alice] probe genRanHex1",
  // | Probes forward
  "[Bob]->[Charlie] probe genRanHex1",
  "[Bob]->[Charlie] probe genRanHex0",
  // Charlie meets Alice
  "[Charlie]->[Alice] meet",
  // | New probe back
  "[Charlie]->[Bob] probe genRanHex2",
  "[Bob]->[Alice] probe genRanHex2",
  "[Alice]->[Charlie] probe genRanHex2",
  "[Charlie]->[Bob] loop genRanHex2 genRanHex3",
  "[Bob]->[Alice] loop genRanHex2 genRanHex3",
  "[Alice]->[Charlie] loop genRanHex2 genRanHex3",
  // | Probes forward
  // | | genRanHex1
  "[Charlie]->[Alice] probe genRanHex1",
  "[Alice]->[Bob] loop genRanHex1 genRanHex6",
  "[Bob]->[Charlie] loop genRanHex1 genRanHex6",
  "[Charlie]->[Alice] loop genRanHex1 genRanHex6",
  // | | genRanHex0
  "[Charlie]->[Alice] probe genRanHex0",
  "[Alice]->[Bob] loop genRanHex0 genRanHex9",
  "[Bob]->[Charlie] loop genRanHex0 genRanHex9",
  "[Charlie]->[Alice] loop genRanHex0 genRanHex9",
];
const messagesgenRanHex12 = [
  // Alice meets Dave
  "[Alice]->[Dave] meet",
  // | New probe back
  "[Alice]->[Bob] probe genRanHex12",
  "[Bob]->[Charlie] probe genRanHex12",
  "[Charlie]->[Alice] probe genRanHex12",
  "[Alice]->[Bob] loop genRanHex12 genRanHex13",
  "[Bob]->[Charlie] loop genRanHex12 genRanHex13",
  "[Charlie]->[Alice] loop genRanHex12 genRanHex13",
  // | (no need to send `[Alice]->[Charlie] probe genRanHex12` because it already looped back `[Charlie]->[Alice] probe genRanHex12`)
  // | Probes forward
  "[Alice]->[Dave] probe genRanHex12",
  "[Alice]->[Dave] probe genRanHex0",
  "[Alice]->[Dave] probe genRanHex1",
  "[Alice]->[Dave] probe genRanHex2",
];
const messagesgenRanHex16 = [
  // Dave meets Edward
  "[Dave]->[Edward] meet",
  // | New probe back
  // | | genRanHex16
  "[Dave]->[Alice] probe genRanHex16",
  "[Alice]->[Bob] probe genRanHex16",
  "[Bob]->[Charlie] probe genRanHex16",
  "[Charlie]->[Alice] probe genRanHex16",
  "[Alice]->[Dave] loop genRanHex16 genRanHex17",
  "[Alice]->[Bob] loop genRanHex16 genRanHex17",
  "[Bob]->[Charlie] loop genRanHex16 genRanHex17",
  "[Charlie]->[Alice] loop genRanHex16 genRanHex17",
  // | Probes forward
  "[Dave]->[Edward] probe genRanHex16",
  "[Dave]->[Edward] probe genRanHex12",
  "[Dave]->[Edward] probe genRanHex0",
  "[Dave]->[Edward] probe genRanHex1",
  "[Dave]->[Edward] probe genRanHex2",
];
// const messagesgenRanHex9 = [
//   // Edward meets Alice
//   "[Edward]->[Alice] meet",
//   // | New probe back
//   "[Edward]->[Dave] probe genRanHex9",
//   "[Dave]->[Alice] probe genRanHex9",
//   "[Alice]->[Bob] probe genRanHex9",
//   "[Bob]->[Charlie] probe genRanHex9",
//   "[Charlie]->[Alice] probe genRanHex9",
//   "[Alice]->[Dave] loop genRanHex9 genRanHex9",
//   "[Dave]->[Edward] loop genRanHex9 genRanHex9",
//   "[Alice]->[Bob] loop genRanHex9 genRanHex9",
//   "[Bob]->[Charlie] loop genRanHex9 genRanHex9",
//   "[Charlie]->[Alice] loop genRanHex9 genRanHex9",
//   "[Alice]->[Edward] probe genRanHex9",
//   "[Edward]->[Dave] loop genRanHex9 genRanHex9",
//   // | Probes forward
//   // | | genRanHex16
//   "[Edward]->[Alice] probe genRanHex16",
//   "[Alice]->[Dave] loop genRanHex16 genRanHex9",
//   "[Dave]->[Edward] loop genRanHex16 genRanHex9",
//   "[Edward]->[Alice] loop genRanHex16 genRanHex9",
//   "[Alice]->[Bob] loop genRanHex16 genRanHex9",
//   "[Bob]->[Charlie] loop genRanHex16 genRanHex9",
//   "[Charlie]->[Alice] loop genRanHex16 genRanHex9",
//   "[Alice]->[Charlie] loop genRanHex16 genRanHex9",
//   // | | genRanHex12
//   "[Edward]->[Alice] probe genRanHex12",
//   "[Alice]->[Bob] loop genRanHex12 genRanHex9",
//   "[Bob]->[Charlie] loop genRanHex12 genRanHex9",
//   "[Charlie]->[Alice] loop genRanHex12 genRanHex9",
//   "[Alice]->[Charlie] loop genRanHex12 genRanHex9",
//   "[Alice]->[Dave] loop genRanHex12 genRanHex9",
//   "[Dave]->[Edward] loop genRanHex12 genRanHex9",
//   "[Edward]->[Alice] loop genRanHex12 genRanHex9",
//   // | | genRanHex0
//   "[Edward]->[Alice] probe genRanHex0",
//   "[Alice]->[Bob] loop genRanHex0 genRanHex9",
//   "[Bob]->[Charlie] loop genRanHex0 genRanHex9",
//   "[Charlie]->[Alice] loop genRanHex0 genRanHex9",
//   "[Alice]->[Charlie] loop genRanHex0 genRanHex9",
//   "[Alice]->[Dave] loop genRanHex0 genRanHex9",
//   "[Dave]->[Edward] loop genRanHex0 genRanHex9",
//   "[Edward]->[Alice] loop genRanHex0 genRanHex9",
//   // | | genRanHex1
//   "[Edward]->[Alice] probe genRanHex1",
//   "[Alice]->[Bob] loop genRanHex1 genRanHex9",
//   "[Bob]->[Charlie] loop genRanHex1 genRanHex9",
//   "[Charlie]->[Alice] loop genRanHex1 genRanHex9",
//   "[Alice]->[Charlie] loop genRanHex1 genRanHex9",
//   "[Alice]->[Dave] loop genRanHex1 genRanHex9",
//   "[Dave]->[Edward] loop genRanHex1 genRanHex9",
//   "[Edward]->[Alice] loop genRanHex1 genRanHex9",
//   // | | genRanHex2
//   "[Edward]->[Alice] probe genRanHex2",
//   "[Alice]->[Bob] loop genRanHex2 genRanHex9",
//   "[Bob]->[Charlie] loop genRanHex2 genRanHex9",
//   "[Charlie]->[Alice] loop genRanHex2 genRanHex9",
//   "[Alice]->[Charlie] loop genRanHex2 genRanHex9",
//   "[Alice]->[Dave] loop genRanHex2 genRanHex9",
//   "[Dave]->[Edward] loop genRanHex2 genRanHex9",
//   "[Edward]->[Alice] loop genRanHex2 genRanHex9",
// ];

describe('Basic Petrogale Hourglass', () => {
  // let Petrogale: unknown;
  let alice: any;
  let bob: any;
  let charlie: any;
  let dave: any;
  let edward: any;
  let messageLogger: any;
  beforeAll(async () => {
    const { Petrogale, MessageLogger } = await import('../src/main.js');
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
    it('Alice has the triangle probes plus an genRanHex12 probe for Dave', () => {
      expect(alice.getProbes()).toEqual({
        genRanHex0: { Bob: true, Charlie: true, Dave: true },
        genRanHex1: { Bob: true, Charlie: true, Dave: true },
        genRanHex2: { Bob: true, Charlie: true, Dave: true },
        genRanHex12: { Bob: true, Charlie: true, Dave: true }
      });
    });
    it('Alice has the triangle loops', () => {
      expect(alice.getLoops().sort()).toEqual([
        'genRanHex0:genRanHex9',
        'genRanHex1:genRanHex6',
        'genRanHex2:genRanHex3',
        'genRanHex12:genRanHex13'
      ].sort());
    });
    it('the message logs are as expected', () => {
      expect(messageLogger.getFullLog()).toEqual(triangleMessages.concat(messagesgenRanHex12));
    });

    // This creates an P topology:
    // Bob - Charlie
    //   \   /
    //    Alice
    //   /
    // Dave - Edward
    describe('Dave meets Edward', () => {
      beforeAll(() => {
        dave.meet(edward);
      });
      it('Alice is friends with the triangle plus Dave', () => {
        expect(alice.getFriends().sort()).toEqual(['Bob', 'Charlie', 'Dave'].sort());
      });
      it('Alice has probes for the triangle plus Dave and Edward', () => {
        expect(alice.getProbes()).toEqual({
          genRanHex0: { Bob: true, Charlie: true, Dave: true },
          genRanHex1: { Bob: true, Charlie: true, Dave: true },
          genRanHex2: { Bob: true, Charlie: true, Dave: true },
          genRanHex12: { Bob: true, Charlie: true, Dave: true },
          genRanHex16: { Bob: true, Charlie: true, Dave: true }
        });
      });
      it('Dave is friends with Alice and Edward', () => {
        expect(dave.getFriends().sort()).toEqual(['Alice', 'Edward'].sort());
      });
      it('Dave has all the triangle probes plus one for Edward', () => {
        expect(dave.getProbes()).toEqual({
          genRanHex0: { Alice: true, Edward: true },
          genRanHex1: { Alice: true, Edward: true },
          genRanHex2: { Alice: true, Edward: true },
          genRanHex12: { Alice: true, Edward: true },
          genRanHex16: { Alice: true, Edward: true }
        });
      });
      it('Edward is friends with Dave', () => {
        expect(edward.getFriends().sort()).toEqual(['Dave']);
      });
      it('Edward has all the triangle probes plus one for Dave', () => {
        expect(edward.getProbes()).toEqual({
          genRanHex0: { Dave: true },
          genRanHex12: { Dave: true },
          genRanHex1: { Dave: true },
          genRanHex2: { Dave: true },
          genRanHex16: { Dave: true }
        });
      });
      it('the message logs are as expected', () => {
        expect(messageLogger.getFullLog()).toEqual([].concat(
          triangleMessages,
          messagesgenRanHex12,
          messagesgenRanHex16
        )
        );
      });

      // This creates an hourglass topology:
      // Bob - Charlie
      //   \   /
      //    Alice
      //   /   \
      // Dave - Edward
      // describe('Edward meets Alice', () => {
      //   beforeAll(() => {
      //     edward.meet(alice);
      //   });

      //   it('Alice is friends with everyone', () => {
      //     expect(alice.getFriends().sort()).toEqual(['Bob', 'Charlie', 'Dave', 'Edward']);
      //   });

      //   it('Alice has probes for each hourglass edge', () => {
      //     expect(alice.getProbes()).toEqual({
      //       genRanHex0: { Bob: true, Charlie: true, Dave: true, Edward: true },
      //       genRanHex1: { Bob: true, Charlie: true, Dave: true, Edward: true },
      //       genRanHex2: { Bob: true, Charlie: true, Dave: true, Edward: true },
      //       genRanHex12: { Bob: true, Charlie: true, Dave: true, Edward: true },
      //       genRanHex16: { Bob: true, Charlie: true, Dave: true, Edward: true },
      //       genRanHex9: { Bob: true, Charlie: true, Dave: true, Edward: true }
      //     });
      //   });
      //   it('Alice has 11 loops', () => {
      //     expect(alice.getLoops().sort()).toEqual([
      //       'genRanHex0:genRanHex2',
      //       'genRanHex0:genRanHex9',
      //       'genRanHex1:genRanHex6',
      //       'genRanHex1:genRanHex9',
      //       'genRanHex2:genRanHex3',
      //       'genRanHex2:genRanHex9',
      //       'genRanHex12:genRanHex13',
      //       'genRanHex12:genRanHex9',
      //       'genRanHex16:genRanHex16',
      //       'genRanHex16:genRanHex9',
      //       'genRanHex9:genRanHex9'
      //     ].sort());
      //   });

      //   it('Bob is friends with Alice and Charlie', () => {
      //     expect(bob.getFriends().sort()).toEqual(['Alice', 'Charlie']);
      //   });

      //   it('Bob has one probe for each hourglass edge', () => {
      //     expect(bob.getProbes()).toEqual({
      //       genRanHex0: { Alice: true, Charlie: true },
      //       genRanHex1: { Alice: true, Charlie: true },
      //       genRanHex2: { Alice: true, Charlie: true },
      //       genRanHex12: { Alice: true, Charlie: true },
      //       genRanHex16: { Alice: true, Charlie: true },
      //       genRanHex9: { Alice: true, Charlie: true }
      //     });
      //   });
      //   it('Bob has 11 loops', () => {
      //     expect(bob.getLoops().sort()).toEqual([
      //       'genRanHex0:genRanHex2',
      //       'genRanHex0:genRanHex9',
      //       'genRanHex1:genRanHex6',
      //       'genRanHex1:genRanHex9',
      //       'genRanHex2:genRanHex3',
      //       'genRanHex2:genRanHex9',
      //       'genRanHex12:genRanHex13',
      //       'genRanHex12:genRanHex9',
      //       'genRanHex16:genRanHex16',
      //       'genRanHex16:genRanHex9',
      //       'genRanHex9:genRanHex9'
      //     ].sort());
      //   });

      //   it('Charlie is friends with Bob and Alice', () => {
      //     expect(charlie.getFriends().sort()).toEqual(['Bob', 'Alice'].sort());
      //   });

      //   it('Charlie has one probe for each hourglass edge', () => {
      //     expect(charlie.getProbes()).toEqual({
      //       genRanHex0: { Alice: true, Bob: true },
      //       genRanHex1: { Alice: true, Bob: true },
      //       genRanHex2: { Alice: true, Bob: true },
      //       genRanHex12: { Alice: true, Bob: true },
      //       genRanHex16: { Alice: true, Bob: true },
      //       genRanHex9: { Alice: true, Bob: true }
      //     });
      //   });
      //   it('Charlie has 11 loops', () => {
      //     expect(charlie.getLoops().sort()).toEqual([
      //       'genRanHex0:genRanHex2',
      //       'genRanHex0:genRanHex9',
      //       'genRanHex12:genRanHex13',
      //       'genRanHex12:genRanHex9',
      //       'genRanHex1:genRanHex6',
      //       'genRanHex1:genRanHex9',
      //       'genRanHex2:genRanHex3',
      //       'genRanHex2:genRanHex9',
      //       'genRanHex16:genRanHex16',
      //       'genRanHex16:genRanHex9',
      //       'genRanHex9:genRanHex9'
      //     ].sort());
      //   });

      //   it('Dave is friends with Edward and Alice', () => {
      //     expect(dave.getFriends().sort()).toEqual(['Edward', 'Alice'].sort());
      //   });

      //   it('Dave has probes for the second triangel of the hourglass edge', () => {
      //     expect(dave.getProbes()).toEqual({
      //       genRanHex0: { Alice: true, Edward: true },
      //       genRanHex1: { Alice: true, Edward: true },
      //       genRanHex2: { Alice: true, Edward: true },
      //       genRanHex12: { Alice: true, Edward: true },
      //       genRanHex16: { Alice: true, Edward: true },
      //       genRanHex9: { Alice: true, Edward: true }
      //     });
      //   });
      //   it('Dave has 6 loops', () => {
      //     expect(dave.getLoops().sort()).toEqual([
      //       'genRanHex0:genRanHex9',
      //       'genRanHex1:genRanHex9',
      //       'genRanHex2:genRanHex9',
      //       'genRanHex12:genRanHex9',
      //       'genRanHex16:genRanHex9',
      //       'genRanHex9:genRanHex9'
      //     ].sort());
      //   });

      //   it('Edward is friends with Dave and Alice', () => {
      //     expect(edward.getFriends().sort()).toEqual(['Dave', 'Alice'].sort());
      //   });

      //   it('Edward has probes for the second triangle of the hourglass edge', () => {
      //     expect(edward.getProbes()).toEqual({
      //       genRanHex0: { Alice: true, Dave: true },
      //       genRanHex1: { Alice: true, Dave: true },
      //       genRanHex2: { Alice: true, Dave: true },
      //       genRanHex12: { Alice: true, Dave: true },
      //       genRanHex16: { Alice: true, Dave: true },
      //       genRanHex9: { Alice: true, Dave: true }
      //     });
      //   });
      //   it('Edward has 6 loops', () => {
      //     expect(edward.getLoops().sort()).toEqual([
      //       'genRanHex0:genRanHex9',
      //       'genRanHex12:genRanHex9',
      //       'genRanHex1:genRanHex9',
      //       'genRanHex2:genRanHex9',
      //       'genRanHex16:genRanHex9',
      //       'genRanHex9:genRanHex9'
      //     ].sort());
      //   });
      //   it('the message logs are as expected', () => {
      //     expect(messageLogger.getFullLog()).toEqual([].concat(
      //       triangleMessages,
      //       messagesgenRanHex12,
      //       messagesgenRanHex16,
      //       messagesgenRanHex9
      //     )
      //     );
      //   });

      // }); // Edward meets Alice
    }); // Dave meets Edward
  }); // Alice meets Dave
}); // basic petrogale hourglass
