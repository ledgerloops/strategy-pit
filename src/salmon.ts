import { Message, Meet, Probe } from "./messages.js";
import { genRanHex } from "./util.js";

// Salmon nodes always send all the probes they can to all their friends.
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
  
    // create new probe for new link
    const probeForNewLink = genRanHex(8);
    if (typeof this.probes[probeForNewLink] === 'undefined') {
      this.probes[probeForNewLink] = {};
    }
    Object.values(this.friends).forEach(friend => {
      this.probes[probeForNewLink][friend.getName()] = true;
      friend.receiveMessage(new Probe(this, probeForNewLink))
    });

    // send existing probes to new friend
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (typeof probes[other.getName()] === 'undefined') {
        this.probes[id][other.getName()] = true;
        other.receiveMessage(new Probe(this, id));
      }
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

    //   console.log(`${this.name} may send some probes to her new friend ${message.getSender().getName()}`, Object.keys(this.probes));
    //   // send existing probes to new friend
    //   Object.entries(this.probes).forEach(([id, probes]) => {
    //     if (typeof probes[message.getSender().getName()] === 'undefined') {
    //       console.log(`${this.name} needs to add ${message.getSender().getName()} in probe ${id}`);
    //       this.probes[id][message.getSender().getName()] = true;
    //       message.getSender().receiveMessage(new Probe(this, id));
    //     } else {
    //       console.log(`${this.name} already has ${message.getSender().getName()} in probe ${id}`);
    //     }
    //   });
    } else if (message.getMessageType() === `probe`) {
      const probeMessage = message as Probe;
      if (typeof this.probes[probeMessage.getId()] === 'undefined') {
        this.probes[probeMessage.getId()] = {};
      } else {
        console.log(`LOOP DETECTED!: ${this.name} already has probe ${probeMessage.getId()} from ${Object.keys(this.probes[probeMessage.getId()]).join(' and ')}`);
      }
      this.probes[probeMessage.getId()][message.getSender().getName()] = true;

      // check if we can forward this to anyone
      Object.values(this.friends).forEach(friend => {
        if (typeof this.probes[probeMessage.getId()][friend.getName()] === 'undefined') {
          this.probes[probeMessage.getId()][friend.getName()] = true;
          friend.receiveMessage(new Probe(this, probeMessage.getId()));
        }
      });
      // this.addFriend(message.getSender());
    }
  }
}
