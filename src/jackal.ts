import { Message, Pauze } from "./messages.js";
import { BasicMessageForwarder, Node } from "./node.js";
import { Stingray } from "./stingray.js";

export class Jackal extends Stingray {
  private pauzed: { [name: string]: Message[] } = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  onMeet(node: string): void {
    this.sendMessage(node, new Pauze(true));
    super.onMeet(node);
    this.sendMessage(node, new Pauze(false));
  }
  handlePauzeMessage(sender: Node, message: Pauze): void {
    if (message.getPauze()) {
      this.pauzed[sender.getName()] = this.pauzed[sender.getName()] || [];
    } else {
      this.pauzed[sender.getName()].forEach((message) => {
        super.receiveMessage(sender, message);
      });
      delete this.pauzed[sender.getName()];
    }
  }
  handleRegularMessage(sender: Node, message: Message): void {
    if (typeof this.pauzed[sender.getName()] !== 'undefined') {
      this.pauzed[sender.getName()].push(message);
    } else {
      super.receiveMessage(sender, message);
    }
  }
  receiveMessage(sender: Node, message: Message): void {
    if (typeof this.pauzed[sender.getName()] !== 'undefined') {
      this.pauzed[sender.getName()].push(message);
      if (message.getMessageType() === 'pauze') {
        this.handlePauzeMessage(sender, message as Pauze);
      } else {
        this.handleRegularMessage(sender, message);
      }
    }
  }
}