import { Message, OverToYou, RaiseHand } from './messages.js';
import { Node, BasicMessageForwarder } from "./node.js";

export abstract class Polite extends Node {
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }

  private raiseHand(to: string): void {
    this.messageForwarder.forwardMessage(this, this.friends[to].node, new RaiseHand());
  }
  private handleRaiseHand(from: string): void {
    this.friends[from].talking = false;
    this.sendMessage(from, new OverToYou());
  }
  private handleOverToYouMessage(from: string): void {
    this.friends[from].talking = true;
    while (this.friends[from].outbox.length > 0) {
      const message = this.friends[from].outbox.shift();
      this.sendMessage(from, message);
    }
  }
  
  protected sendMessage(to: string, message: Message): void {
    if(this.friends[to].talking) {
      this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
    } else {
      this.friends[to].outbox.push(message);
      this.raiseHand(to);
    }
  }
  receiveMessage(sender: Node, message: Message): void {
    // console.log(`${this.name} receives message from ${sender}`, message);
    if (message.getMessageType() === `raise-hand`) {
      this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
      this.handleRaiseHand(sender.getName());
    } else if (message.getMessageType() === `over-to-you`) {
      this.handleOverToYouMessage(sender.getName());
    } else {
      super.receiveMessage(sender, message);
    }
  }
  getMessageLog(): string[] {
    return this.messageForwarder.getLocalLog(this.name);
  }
}