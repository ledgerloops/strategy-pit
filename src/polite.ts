import { Message, OkayToSendProbesMessage, HaveProbesMessage } from './messages.js';
import { Node, BasicMessageForwarder, HandRaisingStatus } from "./node.js";

export abstract class Polite extends Node {
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  private raiseHand(to: string): void {
    this.friends[to].handRaisingStatus = HandRaisingStatus.Waiting;
    this.debugLog.push(`${this.name} raises hand to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, new HaveProbesMessage());
  }
  private handleRaiseHand(from: string): void {
    // console.log(this.name, 'receives raised hand from', from);
    this.debugLog.push(`${this.name} receives raised hand from ${from}`);
    this.friends[from].handRaisingStatus = HandRaisingStatus.Listening;
    this.debugLog.push(`${this.name} sends okay-to-send-probes message to ${from}`);
    super.sendMessage(from, new OkayToSendProbesMessage());
  }
  private handleOverToYouMessage(from: string): void {
    // console.log(this.name, 'receives okay-to-send-probes from', from);
    this.debugLog.push(`${this.name} receives okay-to-send-probes from ${from}`);
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
      this.debugLog.push(`${this.name} is talking to ${to}`);
      return;
    }
    this.debugLog.push(`${this.name} is waiting to talk to ${to}`);

    this.debugLog.push(`${this.name} waits for semaphore to talk to ${to}`);
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
    this.debugLog.push(`sendMessage ${this.name} to ${to}, semaphore wait START`);
    await this.semaphore(to);
    this.debugLog.push(`sendMessage ${this.name} to ${to}, semaphore wait END`);
    this.debugLog.push(`${this.name} is talking and sends ${message.getMessageType()} message to ${to}`);
    this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
  }
  async receiveMessage(sender: Node, message: Message): Promise<void> {
    this.debugLog.push(`[Polite#receiveMessage] ${this.name} receives message from ${sender.getName()}`);
    // console.log(`${this.name} receives message from ${sender}`, message);
    if (message.getMessageType() === `have-probes`) {
      this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
      this.handleRaiseHand(sender.getName());
    } else if (message.getMessageType() === `okay-to-send-probes`) {
      this.handleOverToYouMessage(sender.getName());
    } else {
      this.debugLog.push(`${this.name} receives payload message from ${sender.getName()}`);
      super.receiveMessage(sender, message);
    }
  }
}