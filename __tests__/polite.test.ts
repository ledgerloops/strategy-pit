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
    it('[FIXME: fails!] queues messages when listening', () => {
      const messageForwarder = new BasicMessageForwarder();
      const alice = new PoliteNode('Alice', messageForwarder);
      const bob = new PoliteNode('Bob', messageForwarder);
      alice.meet(bob);
      expect(alice.getFriends()).toEqual(['Bob']);
      expect(bob.getFriends()).toEqual(['Alice']);
      alice.sendTestMessage('Bob');
      bob.sendTestMessage('Alice');
      alice.sendTestMessage('Bob');
      expect(messageForwarder.getFullLog()).toEqual([
        "[Alice]->[Bob] meet",
        "[Alice]->[Bob] test",
        "[Bob]->[Alice] test",
        "[Alice]->[Bob] test",
      ]);
    });
});