import { Message, Meet, Probe, Loop } from "./messages.js";

export class MessageLogger {
  private log: {
    sender: string,
    receiver: string,
    message: Message,
    event: string
  }[] = [];
  logMessageSent(sender: string, receiver: string, message: Message): void {
    this.log.push({ sender, receiver, message, event: 'sent' });
  }
  logMessageReceived(sender: string, receiver: string, message: Message): void {
    this.log.push({ sender, receiver, message, event: 'received' });
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
    return filtered.map(entry => {
      if (entry.event === 'sent') {
        return `[${entry.sender}]->[${entry.receiver}] ${entry.message.toString()}`;
      } else {
        return `[${entry.sender}]>-[${entry.receiver}] ${entry.message.toString()}`;
      }
    });
  }
}
export abstract class Node {
    protected messageLogger: MessageLogger;
    protected name: string;
    protected friends: {
      [name: string]: Node
     }  = {};
   
    constructor(name: string, messageLogger?: MessageLogger) {
      this.name = name;
      this.messageLogger = messageLogger || new MessageLogger();
    }
    getName(): string {
        return this.name;
    }
    abstract onMeet(other: string): void;
    protected addFriend(other: Node): void {
      const otherName = other.getName();
      // console.log(`${this.name} meets ${otherName}`);
      if (typeof this.friends[other.getName()] !== 'undefined') {
        throw new Error(`${this.name} is already friends with ${otherName}`);
      }
      this.friends[otherName] = other;
    }
    getFriends(): string[] {
      return Object.keys(this.friends);
    }
  
    meet(other: Node): void {
      this.addFriend(other);
      this.sendMessage(other.getName(), new Meet());
      this.onMeet(other.getName());
    }
  
    abstract handleMeetMessage(sender: string, message: Meet): void;
    abstract handleProbeMessage(sender: string, message: Probe): void;
    abstract handleLoopMessage(sender: string, message: Loop): void;

    protected sendMessage(to: string, message: Message): void {
      this.messageLogger.logMessageSent(this.name, to, message);
      this.friends[to].receiveMessage(this, message);
    }
    receiveMessage(sender: Node, message: Message): void {
      this.messageLogger.logMessageReceived(sender.getName(), this.name, message);
      // console.log(`${this.name} receives message from ${sender}`, message);
      if (message.getMessageType() === `meet`) {
        this.addFriend(sender);
        this.handleMeetMessage(sender.getName(), message as Meet);
      } else if (message.getMessageType() === `probe`) {
        this.handleProbeMessage(sender.getName(), message as Probe);
      } else if (message.getMessageType() === `loop`) {
        this.handleLoopMessage(sender.getName(), message as Loop);
      }
    }
    getMessageLog(): string[] {
      return this.messageLogger.getLocalLog(this.name);
    }
}