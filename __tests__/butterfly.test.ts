import { BasicMessageForwarder } from "../src/node.js";
import { Butterfly } from "../src/butterfly.js";

describe('Butterfly', () => {
  it('starts a flood probe when it meets a new node', () => {
    const messageForwarder = new BasicMessageForwarder();
    const alice = new Butterfly('Alice', messageForwarder);
    const bob = new Butterfly('Bob', messageForwarder);
    const charlie = new Butterfly('Charlie', messageForwarder);
    alice.meet(bob);
    expect(alice.getFriends()).toEqual(['Bob']);
    expect(bob.getFriends()).toEqual(['Alice']);
    bob.meet(charlie);
    expect(messageForwarder.getFullLog()).toEqual([
      "[Alice]->[Bob] meet",
      "[Bob]->[Charlie] meet",
      // "[Bob]->[Alice] raise-hand",
      // "[Alice]->[Bob] over-to-you",
      // "[Bob]->[Alice] probe",
    ]);
  });
});