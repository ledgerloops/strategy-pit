import { Meet } from "../src/messages.js";
import { BasicMessageForwarder } from "../src/node.js";
import { Polite } from "../src/polite.js";

class PoliteNode extends Polite {
    onMeet(other: string): void {
        this.sendMessage(other, new Meet());
      }
    handleMeetMessage(): void {}
    handleProbeMessage(): void {}
    handleLoopMessage(): void {}
    sendTestMessage(to: string): void {
      this.sendMessage(to, { getMessageType: () => 'test', toString: () => 'test' });
    }
}
describe('Polite', () => {
    it('queues messages when listening', () => {
      const messageForwarder = new BasicMessageForwarder();
      const alice = new PoliteNode('Alice', messageForwarder);
      const bob = new PoliteNode('Bob', messageForwarder);
      alice.meet(bob);
      expect(alice.getFriends()).toEqual(['Bob']);
      expect(bob.getFriends()).toEqual(['Alice']);
      alice.sendTestMessage('Bob');
      bob.sendTestMessage('Alice');
      alice.sendTestMessage('Bob');
      expect(alice.getPoliteProtocolLog()).toEqual([
        "Alice is talking and sends meet message to Bob",
        "Alice is talking and sends test message to Bob",
        "Alice receives raised hand from Bob",
        "Alice sends over-to-you message to Bob",
        "Alice receives payload message from Bob",
        "Alice is not talking and queues test message for Bob",
        "Alice raises hand to Bob",
        "Alice receives over-to-you from Bob",
      ]);
      expect(bob.getPoliteProtocolLog()).toEqual([
        "Bob receives payload message from Alice",
        "Bob receives payload message from Alice",
        "Bob is not talking and queues test message for Alice",
        "Bob raises hand to Alice",
        "Bob receives over-to-you from Alice",
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