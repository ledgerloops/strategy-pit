import { jest } from '@jest/globals';

let counter: number = 0;
jest.unstable_mockModule('../src/util.js', () => {
  return{
    genRanHex: jest.fn((): string => {
      return `genRanHex${counter++}`;
    })
  };
});
const { Butterfly, BasicMessageForwarder } = await import('../src/main.js');

describe('Butterfly', () => {
  it('starts a flood probe when it meets a new node', async () => {
    const messageForwarder = new BasicMessageForwarder();
    const alice = new Butterfly('Alice', messageForwarder);
    const bob = new Butterfly('Bob', messageForwarder);
    const charlie = new Butterfly('Charlie', messageForwarder);
    await alice.meet(bob);
    expect(alice.getFriends()).toEqual(['Bob']);
    expect(bob.getFriends()).toEqual(['Alice']);
    await bob.meet(charlie);
    expect(messageForwarder.getFullLog()).toEqual([
      "[Alice]->[Bob] meet",
      "[Alice]->[Bob] probe genRanHex0",
      "[Bob]->[Charlie] meet",
      "[Bob]->[Charlie] probe genRanHex0",
      // "[Bob]->[Alice] raise-hand",
      // "[Alice]->[Bob] over-to-you",
      // "[Bob]->[Alice] probe genRanHex1",
      "[Bob]->[Charlie] probe genRanHex1",
    ]);
  });
});