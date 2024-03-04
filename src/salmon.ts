import { Message, Meet, Probe } from "./messages.js";
import { genRanHex } from "./util.js";

export class Salmon {
  private name: string;
  private friends: {
   [name: string]: Salmon
  }  = {};
  private probes: {
    [id: string]: { [name: string]: boolean }
  } = {};
  constructor(name: string) {
    this.name = name;
  }
  private addFriend(other: Salmon): void {
    const otherName = other.getName();
    console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[other.name] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }    
    this.friends[otherName] = other;
  }
  meet(other: Salmon): void {
    this.addFriend(other);
    other.receiveMessage(new Meet(this));
    const probeForNewLink = genRanHex(8);
    if (typeof this.probes[probeForNewLink] === 'undefined') {
      this.probes[probeForNewLink] = {};
    }
    
    Object.values(this.friends).forEach(friend => {
      this.probes[probeForNewLink][friend.getName()] = true;
      friend.receiveMessage(new Probe(this, probeForNewLink))
    });
  }
  getName(): string {
    return this.name;
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }
  getProbes(): { [id: string]: { [name: string]: boolean } } {
    return this.probes;
  }
  receiveMessage(message: Message): void {
    console.log(`${this.name} receives message from ${message.getSender().getName()}`, message);
    if (message.getMessageType() === `meet`) {
      this.addFriend(message.getSender());
    } else if (message.getMessageType() === `probe`) {
      const probeMessage = message as Probe;
      if (typeof this.probes[probeMessage.getId()] === 'undefined') {
        this.probes[probeMessage.getId()] = {};
      }
      this.probes[probeMessage.getId()][message.getSender().getName()] = true;
      // this.addFriend(message.getSender());
    }
  }
}
