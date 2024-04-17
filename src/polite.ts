import { Message, OverToYou, RaiseHand } from './messages.js';
import { Node, BasicMessageForwarder, HandRaisingStatus } from "./node.js";

export abstract class Polite extends Node {
  private politeProtocolLog: string[] = [];
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  public getPoliteProtocolLog(): string[] {
    return this.politeProtocolLog;
  }
  private raiseHand(to: string): void {
    this.friends[to].handRaisingStatus = HandRaisingStatus.Waiting;
    this.politeProtocolLog.push(`${this.name} raises hand to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, new RaiseHand());
  }
  private handleRaiseHand(from: string): void {
    // console.log(this.name, 'receives raised hand from', from);
    this.politeProtocolLog.push(`${this.name} receives raised hand from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Listening;
    this.politeProtocolLog.push(`${this.name} sends over-to-you message to ${from}`);
    super.sendMessage(from, new OverToYou());
  }
  private handleOverToYouMessage(from: string): void {
    // console.log(this.name, 'receives over-to-you from', from);
    this.politeProtocolLog.push(`${this.name} receives over-to-you from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Talking;
    if (typeof this.friends[from].promises !== 'undefined') {
      this.friends[from].promises.forEach(promise => {
        promise.resolve();
      });
      delete this.friends[from].promises;
    }
  }
  protected async semaphore(to: string): Promise<void> {
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Talking) {
      // console.log(this.name, 'is talking to', to);
      return;
    }
    // console.log(this.name, 'is waiting to talk to', to);

    this.politeProtocolLog.push(`${this.name} waits for semaphore to talk to ${to}`);
    const ret: Promise<void> = new Promise((resolve, reject) => {
      if (typeof this.friends[to].promises === 'undefined') {
        this.friends[to].promises = [];
      }
      this.friends[to].promises.push({ resolve, reject });
    });
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Listening) {
      // console.log(this.name, 'raising hand to', to);
      this.raiseHand(to);
    }
    return ret;
  }
  protected async sendMessage(to: string, message: Message): Promise<void> {
    await this.semaphore(to);
    this.politeProtocolLog.push(`${this.name} is talking and sends ${message.getMessageType()} message to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
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