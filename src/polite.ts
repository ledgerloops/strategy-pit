import { Message, OverToYou, RaiseHand } from './messages.js';
import { Node, BasicMessageForwarder } from "./node.js";

export abstract class Polite extends Node {
  private politeProtocolLog: string[] = [];
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  public getPoliteProtocolLog(): string[] {
    return this.politeProtocolLog;
  }
  private raiseHand(to: string): void {
    this.politeProtocolLog.push(`${this.name} raises hand to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, new RaiseHand());
  }
  private handleRaiseHand(from: string): void {
    this.politeProtocolLog.push(`${this.name} receives raised hand from ${from}`);
    this.friends[from].talking = false;
    super.sendMessage(from, new OverToYou());
  }
  private handleOverToYouMessage(from: string): void {
    this.politeProtocolLog.push(`${this.name} receives over-to-you from ${from}`);
    this.friends[from].talking = true;
    while (this.friends[from].outbox.length > 0) {
      const message = this.friends[from].outbox.shift();
      this.sendMessage(from, message);
    }
  }
  
  protected sendMessage(to: string, message: Message): void {
    if(this.friends[to].talking) {
      this.politeProtocolLog.push(`${this.name} is talking and sends message to ${to}`);
      this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
    } else {
      this.politeProtocolLog.push(`${this.name} is not talking and queues message for ${to}, then raises hand to ${to}`);
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
      this.politeProtocolLog.push(`${this.name} receives payload message from ${sender.getName()}`);
      super.receiveMessage(sender, message);
    }
  }
  getMessageLog(): string[] {
    return this.messageForwarder.getLocalLog(this.name);
  }
}