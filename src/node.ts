import { Message, MeetMessage, ProbeMessage, LoopMessage } from "./messages.js";

class Entry {
  sender: string;
  receiver: string;
  message: Message;
  event: string;
  constructor(sender: string, receiver: string, message: Message, event: string) {
    this.sender = sender;
    this.receiver = receiver;
    this.message = message;
    this.event = event;
  }
  describePath(): string {
    if (this.event === 'sent') {
      return `[${this.sender}]->[${this.receiver}]`;
    } else {
      return `[${this.sender}]>-[${this.receiver}]`;
    }
  }
}
export class BasicMessageForwarder {
  private log: Entry[] = [];
  logMessageSent(sender: string, receiver: string, message: Message): void {
    this.log.push(new Entry(sender, receiver, message, 'sent'));
  }
  logMessageReceived(sender: string, receiver: string, message: Message): void {
    this.log.push(new Entry(sender, receiver, message, 'received'));
  }
  forwardMessage(sender: Node, receiver: Node, message: Message): void {
    this.logMessageSent(sender.getName(), receiver.getName(), message);
    receiver.receiveMessage(sender, message);
  }
  getLocalLog(name: string): string[] {
    return this.log.filter(entry => {
      if (entry.sender === name) {
        return (entry.event === 'sent');
      }
      if (entry.receiver === name) {
        return (entry.event === 'received');
      }
      // istanbul ignore next
      return false;
    }).map(entry => {
      if (entry.event === 'sent') {
        return `TO[${entry.receiver}] ${entry.message.toString()}`;
      } else {
        return `FROM[${entry.sender}] ${entry.message.toString()}`;
      }
    });
  }
  getFullLog(includeEachMessageTwice: boolean = false): string[] {
    const filtered = (includeEachMessageTwice) ? this.log : this.log.filter(entry => entry.event === 'sent');
    return filtered.map(entry => `${entry.describePath()} ${entry.message.toString()}`);
  }
  getProbeLogs(): {
    [text: string]: string[]
  } {
    const probeLogs: {
      [text: string]: string[]
    } = {};
    // console.log(this.log);
    this.log.filter(entry => entry.message.getMessageType() === 'probe').map(entry => {
      if (typeof probeLogs[entry.message.toString()] === 'undefined') {
        probeLogs[entry.message.toString()] = [];
      }
      probeLogs[entry.message.toString()].push(entry.describePath());
    });
    return probeLogs;
  }
}
export class BatchedMessageForwarder extends BasicMessageForwarder {
  private batch: {
    sender: Node,
    receiver: Node,
    message: Message
  }[] = [];
  forwardMessage(sender: Node, receiver: Node, message: Message): void {
    this.logMessageSent(sender.getName(), receiver.getName(), message);
    this.batch.push({ sender, receiver, message });
  }
  async flush(): Promise<string[]> {
    this.logMessageSent('---', '---', { toString: () => '---', getMessageType: () => 'separator' } as Message);
    const flushReport: string[] = [];
    const batch = this.batch;
    this.batch = [];
    const promises: Promise<void>[] = batch.map(entry => {
      const promise: Promise<void> = entry.receiver.receiveMessage(entry.sender, entry.message);
      flushReport.push(`[${entry.sender.getName()}]->[${entry.receiver.getName()}] ${entry.message.toString()}`);
      return promise;
    });
    await Promise.all(promises);
    return flushReport;
  }
  getBatch(): string[] {
    return this.batch.map(entry => `[${entry.sender.getName()}]->[${entry.receiver.getName()}] ${entry.message.toString()}`);
  }
}

export enum HandRaisingStatus {
  Listening,
  Waiting,
  Talking,
}

export class Friend {
  public handRaisingStatus: HandRaisingStatus;
  public node: Node;
  public promises: {
      resolve: () => void,
      reject: () => void,
    }[];

  constructor(node: Node, handRaisingStatus: HandRaisingStatus) {
    this.node = node;
    this.handRaisingStatus = handRaisingStatus;
    this.promises = [];
  }
}

export abstract class Node {
  protected debugLog: string[] = [];
  protected messageForwarder: BasicMessageForwarder;
  protected name: string;
  protected friends: {
    [name: string]: Friend
   }  = {};
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    this.name = name;
    this.messageForwarder = messageForwarder || new BasicMessageForwarder();
  }
  getName(): string {
      return this.name;
  }
  getDebugLog(): string[] {
    return this.debugLog;
  }
  abstract onMeet(other: string): Promise<void>;
  protected addFriend(other: Node, handRaisingStatus: HandRaisingStatus): void {
    const otherName = other.getName();
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[other.getName()] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }
    this.friends[otherName] = new Friend(other, handRaisingStatus);
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }

  meet(other: Node): Promise<void> {
    this.addFriend(other, HandRaisingStatus.Talking);
    return this.onMeet(other.getName());
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  protected handleMeetMessage(_sender: string, _message: MeetMessage): void {}
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  protected handleProbeMessage(_sender: string, _message: ProbeMessage): void {}
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  protected handleLoopMessage(_sender: string, _message: LoopMessage): void {}
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  protected handleHaveProbesMessage(_from: string): void {}
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  protected handleOkayToSendProbesMessage(_from: string): void {}

  protected sendMessage(to: string, message: Message): void {
    this.messageForwarder.forwardMessage(this, this.friends[to].node, message);
  }
  async receiveMessage(sender: Node, message: Message): Promise<void> {
    this.debugLog.push(`[Node#receiveMessage] ${this.name} receives message from ${sender.getName()}`);
    this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
    // console.log(`${this.name} receives message from ${sender}`, message);
    if (message.getMessageType() === `meet`) {
      this.addFriend(sender, HandRaisingStatus.Listening);
      return this.handleMeetMessage(sender.getName(), message as MeetMessage);
    } else if (message.getMessageType() === `probe`) {
      return this.handleProbeMessage(sender.getName(), message as ProbeMessage);
    } else if (message.getMessageType() === `loop`) {
      return this.handleLoopMessage(sender.getName(), message as LoopMessage);
    } else if (message.getMessageType() === `have-probes`) {
      this.messageForwarder.logMessageReceived(sender.getName(), this.getName(), message);
      this.handleHaveProbesMessage(sender.getName());
    } else if (message.getMessageType() === `okay-to-send-probes`) {
      this.handleOkayToSendProbesMessage(sender.getName());

    }
  }
  getMessageLog(): string[] {
    return this.messageForwarder.getLocalLog(this.name);
  }
}
