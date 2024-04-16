import { Meet } from "../src/messages.js";
import { BasicMessageForwarder } from "../src/node.js";
import { Polite } from "../src/polite.js";

class PoliteNode extends Polite {
    async onMeet(other: string): Promise<void> {
        this.sendMessage(other, new Meet());
      }
    handleMeetMessage(): void {}
    handleProbeMessage(): void {}
    handleLoopMessage(): void {}
    sendTestMessage(to: string): Promise<void> {
      return this.sendMessage(to, { getMessageType: () => 'test', toString: () => 'test' });
    }
}
describe('Polite', () => {
    it('queues messages when listening', async () => {
      const messageForwarder = new BasicMessageForwarder();
      const alice = new PoliteNode('Alice', messageForwarder);
      const bob = new PoliteNode('Bob', messageForwarder);
      await alice.meet(bob);
      console.log('1');
      expect(alice.getFriends()).toEqual(['Bob']);
      expect(bob.getFriends()).toEqual(['Alice']);
      await alice.sendTestMessage('Bob');
      console.log('2');
      await bob.sendTestMessage('Alice');
      console.log('3');
      await alice.sendTestMessage('Bob');
      console.log('4');
      expect(alice.getPoliteProtocolLog()).toEqual([
        "Alice is talking and sends meet message to Bob",
        "Alice is talking and sends test message to Bob",
        "Alice receives raised hand from Bob",
        "Alice sends over-to-you message to Bob",
        "Alice receives payload message from Bob",
        "Alice waits for semaphore to talk to Bob",
        "Alice raises hand to Bob",
        "Alice receives over-to-you from Bob",
        "Alice is talking and sends test message to Bob",
    ]);
      expect(bob.getPoliteProtocolLog()).toEqual([
        "Bob receives payload message from Alice",
        "Bob receives payload message from Alice",
        "Bob waits for semaphore to talk to Alice",
        "Bob raises hand to Alice",
        "Bob receives over-to-you from Alice",
        "Bob is talking and sends test message to Alice",
        "Bob receives raised hand from Alice",
        "Bob sends over-to-you message to Alice",
        "Bob receives payload message from Alice",
      ]);
      expect(messageForwarder.getFullLog()).toEqual([
        "[Alice]->[Bob] meet",
        "[Alice]->[Bob] test",
        "[Bob]->[Alice] raise-hand",
        "[Alice]->[Bob] over-to-you",
        "[Bob]->[Alice] test",
        "[Alice]->[Bob] raise-hand",
        "[Bob]->[Alice] over-to-you",
        "[Alice]->[Bob] test",
    
      ]);
    });
});