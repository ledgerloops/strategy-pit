import { Meet } from "../src/messages.js";
import { BasicMessageForwarder } from "../src/node.js";
import { Polite } from "../src/polite.js";

export class Butterfly extends Polite {
    constructor(name: string, messageForwarder: BasicMessageForwarder) {
        super(name, messageForwarder);
    }
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