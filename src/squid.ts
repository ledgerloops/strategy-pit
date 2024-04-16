import { Message, Pauze } from "./messages.js";
import { BasicMessageForwarder, Node } from "./node.js";
import { Stingray } from "./stingray.js";

export class Squid extends Stingray {
  private pauzed: { [name: string]: Message[] } = {};
  private theyHaveTheirHandUp: { [name: string]: boolean } = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  async onMeet(node: string): Promise<void> {
    this.sendMessage(node, new Pauze(true));
    super.onMeet(node);
    if (this.theyHaveTheirHandUp[node]) {
      delete this.theyHaveTheirHandUp[node];
      this.sendMessage(node, new Pauze(false));
    }
  }
  handlePauzeMessage(other: string, message: Pauze): void {
    if (message.getPauze()) {
      this.log.push(`PAUZING MESSAGES TO ${other}`);
      this.pauzed[other] = this.pauzed[other] || [];
      // unpauze the other party as an acknowledgement that they now have the semaphore on the half duplex channel
      this.sendMessage(other, new Pauze(false));
    } else {
      this.log.push(`UNPAUZING MESSAGES TO ${other}`);
      this.pauzed[other].forEach((message) => {
        this.log.push(`SENDING PAUZED MESSAGE TO ${other}: ${message.toString()}`);
        super.sendMessage(other, message);
      });
      delete this.pauzed[other];
    }
  }
  sendMessage(to: string, message: Message): void {
    if (typeof this.pauzed[to] !== 'undefined') {
      this.log.push(`PAUZED MESSAGE TO ${to}: ${message.toString()}`);
      this.pauzed[to].push(message);
    } else {
      super.sendMessage(to, message);
    }
  }
  receiveMessage(sender: Node, message: Message): void {
    if (message.getMessageType() === 'pauze') {
      if ((message as Pauze).getPauze()) {
        this.theyHaveTheirHandUp[sender.getName()] = true;
      }
      this.handlePauzeMessage(sender.getName(), message as Pauze);
    } else {
      super.receiveMessage(sender, message);
    }
  }
}