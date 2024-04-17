import { Meet } from "../src/messages.js";
import { BasicMessageForwarder } from "../src/node.js";
import { Polite } from "../src/polite.js";

class PoliteNode extends Polite {
    async onMeet(other: string): Promise<void> {
        this.sendMessage(other, new Meet());
      }
    async handleMeetMessage(): Promise<void> {}
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
      // console.log('1');
      expect(alice.getFriends()).toEqual(['Bob']);
      expect(bob.getFriends()).toEqual(['Alice']);
      await alice.sendTestMessage('Bob');
      // console.log('2');
      await bob.sendTestMessage('Alice');
      // console.log('3');
      await alice.sendTestMessage('Bob');
      // console.log('4');
      expect(alice.getDebugLog()).toEqual([
        "sendMessage Alice to Bob, semaphore wait START",
        "Alice is talking to Bob",
        "sendMessage Alice to Bob, semaphore wait END",
        "Alice is talking and sends meet message to Bob",
        "sendMessage Alice to Bob, semaphore wait START",
        "Alice is talking to Bob",
        "sendMessage Alice to Bob, semaphore wait END",
        "Alice is talking and sends test message to Bob",
        "[Polite#receiveMessage] Alice receives message from Bob",
        "Alice receives raised hand from Bob",
        "Alice sends over-to-you message to Bob",
        "[Polite#receiveMessage] Alice receives message from Bob",
        "Alice receives payload message from Bob",
        "[Node#receiveMessage] Alice receives message from Bob",
        "sendMessage Alice to Bob, semaphore wait START",
        "Alice is waiting to talk to Bob",
        "Alice waits for semaphore to talk to Bob",
        "Alice raises hand to Bob",
        "[Polite#receiveMessage] Alice receives message from Bob",
        "Alice receives over-to-you from Bob",
        "sendMessage Alice to Bob, semaphore wait END",
        "Alice is talking and sends test message to Bob",
      ]);
      expect(bob.getDebugLog()).toEqual([
        "[Polite#receiveMessage] Bob receives message from Alice",
        "Bob receives payload message from Alice",
        "[Node#receiveMessage] Bob receives message from Alice",
        "[Polite#receiveMessage] Bob receives message from Alice",
        "Bob receives payload message from Alice",
        "[Node#receiveMessage] Bob receives message from Alice",
        "sendMessage Bob to Alice, semaphore wait START",
        "Bob is waiting to talk to Alice",
        "Bob waits for semaphore to talk to Alice",
        "Bob raises hand to Alice",
        "[Polite#receiveMessage] Bob receives message from Alice",
        "Bob receives over-to-you from Alice",
        "sendMessage Bob to Alice, semaphore wait END",
        "Bob is talking and sends test message to Alice",
        "[Polite#receiveMessage] Bob receives message from Alice",
        "Bob receives raised hand from Alice",
        "Bob sends over-to-you message to Alice",
        "[Polite#receiveMessage] Bob receives message from Alice",
        "Bob receives payload message from Alice",
        "[Node#receiveMessage] Bob receives message from Alice",
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