import { Message, Meet, Probe, Loop } from "./messages.js";

export abstract class Node {
    protected messageLog: {
      [other: string]: {
        in: Message[],
        out: Message[]
      }
    } = {};
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
      other.receiveMessage(new Meet(this as Node));
      this.onMeet(other.getName());
    }
  
    abstract handleMeetMessage(message: Meet): void;
    abstract handleProbeMessage(message: Probe): void;
    abstract handleLoopMessage(message: Loop): void;

    protected sendMessage(to: string, message: Message): void {
      if (typeof this.messageLog[to] === 'undefined') {
        this.messageLog[to] = {
          in: [],
          out: []
        };
      }
      this.messageLog[to].out.push(message);
      this.friends[to].receiveMessage(message);
    }
    receiveMessage(message: Message): void {
      if (typeof this.messageLog[message.getSender().getName()] === 'undefined') {
        this.messageLog[message.getSender().getName()] = {
          in: [],
          out: []
        };
      }
      this.messageLog[message.getSender().getName()].in.push(message);
      // console.log(`${this.name} receives message from ${message.getSender().getName()}`, message);
      if (message.getMessageType() === `meet`) {
        this.handleMeetMessage(message as Meet);
      } else if (message.getMessageType() === `probe`) {
        this.handleProbeMessage(message as Probe);
      } else if (message.getMessageType() === `loop`) {
        this.handleLoopMessage(message as Loop);
      }
    }
  
}