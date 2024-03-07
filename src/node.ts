import { Message, Meet, Probe, Loop } from "./messages.js";

export abstract class Node {
    protected messageLog: string[] = [];
    protected name: string;
    protected friends: {
      [name: string]: Node
     }  = {};
   
    constructor(name: string) {
      this.name = name;
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
      this.messageLog.push(`TO[${to}] ${message.toString()}`);
      this.friends[to].receiveMessage(this, message);
    }
    receiveMessage(sender: Node, message: Message): void {
      this.messageLog.push(`FROM[${sender.getName()}] ${message.toString()}`);
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
      return this.messageLog;
    }  
}