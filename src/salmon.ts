import { Message, Meet, Probe, Loop } from "./messages.js";
import { genRanHex } from "./util.js";
import { Node } from "./node.js";

export class SalmonLoopStore {
  private loops: {
    [id: string]: boolean
  } = {};
  constructor() {}
  has(id: string): boolean {
    return this.loops[id] === true;
  }
  set(id: string): void {
    this.loops[id] = true;
  }
  getKeys(): string[] {
    return Object.keys(this.loops);
  }
}

// Salmon nodes always send all the probes they can to all their friends.
export class Salmon extends Node {
  protected friends: {
   [name: string]: Node
  }  = {};
  protected probes: {
    [id: string]: { [name: string]: boolean }
  } = {};
  protected loopStore: SalmonLoopStore = new SalmonLoopStore();

  constructor(name: string) {
    super(name);
  }
  protected addFriend(other: Node): void {
    const otherName = other.getName();
    // console.log(`${this.name} meets ${otherName}`);
    if (typeof this.friends[other.getName()] !== 'undefined') {
      throw new Error(`${this.name} is already friends with ${otherName}`);
    }
    this.friends[otherName] = other;
  }
  meet(other: Node): void {
    this.addFriend(other);
    other.receiveMessage(new Meet(this));

    // create new probe for new link
    const probeForNewLink = genRanHex(8);
    if (typeof this.probes[probeForNewLink] === 'undefined') {
      this.probes[probeForNewLink] = {};
    }
    Object.values(this.friends).forEach(friend => {
      if (typeof this.probes[probeForNewLink][friend.getName()] === 'undefined') {
        this.probes[probeForNewLink][friend.getName()] = true;
        friend.receiveMessage(new Probe(this, probeForNewLink));
        return;
      }
    });

    // send existing probes to new friend
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (this.loopStore.has(id)) {
        // console.log(`existing probe apparently looped back`);
      } else {
        if (typeof probes[other.getName()] === 'undefined') {
          this.probes[id][other.getName()] = true;
          other.receiveMessage(new Probe(this, id));
        }
      }
    });
  }
  getFriends(): string[] {
    return Object.keys(this.friends);
  }
  getProbes(): { [id: string]: { [name: string]: boolean } } {
    return this.probes;
  }
  getLoops(): string[] {
    return this.loopStore.getKeys();
  }
  receiveMessage(message: Message): void {
    // console.log(`${this.name} receives message from ${message.getSender().getName()}`, message);
    if (message.getMessageType() === `meet`) {
      this.addFriend(message.getSender());
    } else if (message.getMessageType() === `probe`) {
      const probeMessage = message as Probe;
      if (typeof this.probes[probeMessage.getId()] === 'undefined') {
        this.probes[probeMessage.getId()] = {};
      } else {
        // console.log(`LOOP DETECTED!: ${this.name} already has probe ${probeMessage.getId()} from (or sent to) ${Object.keys(this.probes[probeMessage.getId()]).join(' and ')}`);
        this.loopStore.set(probeMessage.getId());
        Object.keys(this.probes[probeMessage.getId()]).forEach(name => {
          this.friends[name].receiveMessage(new Loop(this, probeMessage.getId()));
        });
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
    } else if (message.getMessageType() === `loop`) {
      const loopMessage = message as Loop;
      if (!this.loopStore.has(loopMessage.getProbeId())) {
        // console.log(`${this.name} received loop message about ${loopMessage.getProbeId()} from ${message.getSender().getName()}`);
        Object.keys(this.probes[loopMessage.getProbeId()]).forEach(name => {
          if (name !== message.getSender().getName()) {
            this.friends[name].receiveMessage(new Loop(this, loopMessage.getProbeId()));
          }
        });
        this.loopStore.set(loopMessage.getProbeId());
      } else {
        // console.log(`LOOP ${loopMessage.getProbeId()} IS NOT NEW TO ME`);
      }
    }
  }
}
