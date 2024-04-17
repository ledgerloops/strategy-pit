import { Message, Pauze } from "./messages.js";
import { BasicMessageForwarder, Node } from "./node.js";
import { Stingray } from "./stingray.js";

export class Jackal extends Stingray {
  private pauzed: { [name: string]: Message[] } = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  async onMeet(node: string): Promise<void> {
    this.sendMessage(node, new Pauze(true));
    super.onMeet(node);
    this.sendMessage(node, new Pauze(false));
  }
  handlePauzeMessage(other: string, message: Pauze): void {
    if (message.getPauze()) {
      this.log.push(`PAUZING MESSAGES TO ${other}`);
      this.pauzed[other] = this.pauzed[other] || [];
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
  async receiveMessage(sender: Node, message: Message): Promise<void> {
    if (message.getMessageType() === 'pauze') {
      this.handlePauzeMessage(sender.getName(), message as Pauze);
    } else {
      super.receiveMessage(sender, message);
    }
  }
}