import { Message, OverToYou, RaiseHand } from './messages.js';
import { Node, BasicMessageForwarder, HandRaisingStatus } from "./node.js";

export abstract class Polite extends Node {
  private promises: {
    [name: string]: {
      resolve: () => void,
      reject: () => void,
    }[]
  } = {};
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
    this.politeProtocolLog.push(`${this.name} receives raised hand from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Listening;
    this.politeProtocolLog.push(`${this.name} sends over-to-you message to ${from}`);
    super.sendMessage(from, new OverToYou());
  }
  private handleOverToYouMessage(from: string): void {
    this.politeProtocolLog.push(`${this.name} receives over-to-you from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Talking;
    while (this.friends[from].outbox.length > 0) {
      const message = this.friends[from].outbox.shift();
      super.sendMessage(from, message);
    }
    if (typeof this.promises[from] !== 'undefined') {
      this.promises[from].forEach(promise => {
        promise.resolve();
      });
      delete this.promises[from];
    }
  }
  protected async semaphore(to: string): Promise<void> {
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Talking) {
      return;
    }
    this.politeProtocolLog.push(`${this.name} waits for semaphore to talk to ${to}`);
    return new Promise((resolve, reject) => {
      if (typeof this.promises[to] === 'undefined') {
        this.promises[to] = [];
      }
      this.promises[to].push({ resolve, reject });
    });
  }
  protected sendMessage(to: string, message: Message): void {
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Talking) {
      this.politeProtocolLog.push(`${this.name} is talking and sends ${message.getMessageType()} message to ${to}`);
      this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
      return;
    }
    this.politeProtocolLog.push(`${this.name} is not talking and queues ${message.getMessageType()} message for ${to}`);
    this.friends[to].outbox.push(message);
    if(this.friends[to].handRaisingStatus === HandRaisingStatus.Listening) {
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