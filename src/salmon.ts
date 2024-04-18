import { ProbeMessage, TraceMessage } from "./messages.js";
import { genRanHex } from "./genRanHex.js";
import { Node, BasicMessageForwarder } from "./node.js";

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

  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  protected sendExistingProbesToNewFriend(other: string): void {
    // send existing probes to new friend
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (this.loopStore.has(id)) {
        // console.log(`existing probe apparently looped back`);
      } else {
        if (typeof probes[other] === 'undefined') {
          this.probes[id][other] = true;
          this.sendMessage(other, new ProbeMessage(id));
        }
      }
    });
  }
  protected sendNewProbeToExistingFriends(probeForNewLink: string): void {
    Object.values(this.friends).forEach(friend => {
      if (typeof this.probes[probeForNewLink][friend.node.getName()] === 'undefined') {
        this.probes[probeForNewLink][friend.node.getName()] = true;
        this.sendMessage(friend.node.getName(), new ProbeMessage(probeForNewLink));
      }
    });
  }
  onMeet(other: string): void {
    // create new probe for new link
    const probeForNewLink = genRanHex(8);
    if (typeof this.probes[probeForNewLink] === 'undefined') {
      this.probes[probeForNewLink] = {};
    }
    this.sendNewProbeToExistingFriends(probeForNewLink);
    this.sendExistingProbesToNewFriend(other);
  }
  getProbes(): { [id: string]: { [name: string]: boolean } } {
    return this.probes;
  }
  getLoops(): string[] {
    return this.loopStore.getKeys();
  }
  handleMeetMessage(): void {
  }
  protected onLoopDetected(message: ProbeMessage): void {
      // console.log(`LOOP DETECTED!: ${this.name} already has probe ${message.getId()} from (or sent to) ${Object.keys(this.probes[message.getId()]).join(' and ')}`);
      this.loopStore.set(message.getId());
      Object.keys(this.probes[message.getId()]).forEach(name => {
        this.sendMessage(name, new TraceMessage( message.getId(), 'default', 'default'));
      });
  }
  handleProbeMessage(sender: string, message: ProbeMessage): void {
    if (typeof this.probes[message.getId()] === 'undefined') {
      this.probes[message.getId()] = {};
    } else {
      this.onLoopDetected(message);
    }
    this.probes[message.getId()][sender] = true;

    // check if we can forward this to anyone
    Object.values(this.friends).forEach(friend => {
      if (typeof this.probes[message.getId()][friend.node.getName()] === 'undefined') {
        this.probes[message.getId()][friend.node.getName()] = true;
        this.sendMessage(friend.node.getName(), new ProbeMessage(message.getId()));
      }
    });
    // this.addFriend(message.getSender());
  }
  handleTraceMessage(sender: string, message: TraceMessage): void {
    if (!this.loopStore.has(message.getProbeId())) {
      // console.log(`${this.name} received loop message about ${message.getProbeId()} from ${message.getSender().getName()}`);
      Object.keys(this.probes[message.getProbeId()]).forEach(name => {
        if (name !== sender) {
          this.sendMessage(name, new TraceMessage(message.getProbeId(), 'default', 'default'));
        }
      });
      this.loopStore.set(message.getProbeId());
    } else {
      // console.log(`TRACE ${message.getProbeId()} IS NOT NEW TO ME`);
    }

  }
}
