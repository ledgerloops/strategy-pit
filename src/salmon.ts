import { Meet, Probe, Loop } from "./messages.js";
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
  protected probes: {
    [id: string]: { [name: string]: boolean }
  } = {};
  protected loopStore: SalmonLoopStore = new SalmonLoopStore();

  constructor(name: string) {
    super(name);
  }
  protected sendExistingProbesToNewFriend(other: Node): void {
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
  onMeet(other: Node): void {
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
    this.sendExistingProbesToNewFriend(other);
  }
  getProbes(): { [id: string]: { [name: string]: boolean } } {
    return this.probes;
  }
  getLoops(): string[] {
    return this.loopStore.getKeys();
  }
  handleMeetMessage(message: Meet): void {
    this.addFriend(message.getSender());
  }
  handleProbeMessage(message: Probe): void {
    if (typeof this.probes[message.getId()] === 'undefined') {
      this.probes[message.getId()] = {};
    } else {
      // console.log(`LOOP DETECTED!: ${this.name} already has probe ${message.getId()} from (or sent to) ${Object.keys(this.probes[message.getId()]).join(' and ')}`);
      this.loopStore.set(message.getId());
      Object.keys(this.probes[message.getId()]).forEach(name => {
        this.friends[name].receiveMessage(new Loop(this, message.getId()));
      });
    }
    this.probes[message.getId()][message.getSender().getName()] = true;

    // check if we can forward this to anyone
    Object.values(this.friends).forEach(friend => {
      if (typeof this.probes[message.getId()][friend.getName()] === 'undefined') {
        this.probes[message.getId()][friend.getName()] = true;
        friend.receiveMessage(new Probe(this, message.getId()));
      }
    });
    // this.addFriend(message.getSender());
  }
  handleLoopMessage(message: Loop): void {
    if (!this.loopStore.has(message.getProbeId())) {
      // console.log(`${this.name} received loop message about ${message.getProbeId()} from ${message.getSender().getName()}`);
      Object.keys(this.probes[message.getProbeId()]).forEach(name => {
        if (name !== message.getSender().getName()) {
          this.friends[name].receiveMessage(new Loop(this, message.getProbeId()));
        }
      });
      this.loopStore.set(message.getProbeId());
    } else {
      // console.log(`LOOP ${message.getProbeId()} IS NOT NEW TO ME`);
    }

  }
}
