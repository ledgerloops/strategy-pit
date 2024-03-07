import { Probe, Loop } from "./messages.js";
import { genRanHex } from "./util.js";
import { Node, MessageLogger } from "./node.js";

export class StingrayProbeStore {
  private probes: {
    [id: string]: {
      from: string;
      to: string[];
    }
  } = {};
  constructor() {}
  has(id: string): boolean {
    return (typeof this.probes[id] !== 'undefined');
  }
  set(id: string, from: string, to: string[]): void {
    this.probes[id] = { from, to };
  }
  getKeys(): string[] {
    return Object.keys(this.probes);
  }
}

export class StingrayLoopStore {
  private loops: {
    [probeId: string]: {
      [loopId: string]: {
        from: string;
        to: string[];
      }
    }
  } = {};
  constructor() {}
  has(probeId: string, loopId: string): boolean {
    return ((typeof this.loops[probeId] !== 'undefined') && (typeof this.loops[probeId][loopId] !== 'undefined'));
  }
  set(probeId: string, loopId: string, from: string, to: string[]): void {
    if (typeof this.loops[probeId] === 'undefined') {
      this.loops[probeId] = {};
    }
    this.loops[probeId][loopId] = { from, to };
  }
  getKeys(): string[] {
    const loops: string[] = [];
    Object.keys(this.loops).forEach(probeId => Object.keys(this.loops[probeId]).forEach(loopId => loops.push(`${probeId}:${loopId}`)));
    return loops;
  }
}

// Stingray nodes always send all the probes they can to all their friends.
export class Stingray extends Node {
  protected probeStore: StingrayProbeStore = new StingrayProbeStore();
  protected loopStore: StingrayLoopStore = new StingrayLoopStore();

  constructor(name: string, messageLogger?: MessageLogger) {
    super(name, messageLogger);
  }
  protected sendExistingProbesToNewFriend(other: string): void {
    // send existing probes to new friend
    this.probeStore.getKeys().forEach(probeId) => {
      // ...
    });    
  }
  protected sendNewProbeToExistingFriends(probeForNewLink: string): void {
    Object.values(this.friends).forEach(friend => {
      if (typeof this.probes[probeForNewLink][friend.getName()] === 'undefined') {
        this.probes[probeForNewLink][friend.getName()] = true;
        this.sendMessage(friend.getName(), new Probe(probeForNewLink));
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
  protected onLoopDetected(message: Probe): void {
      // console.log(`LOOP DETECTED!: ${this.name} already has probe ${message.getId()} from (or sent to) ${Object.keys(this.probes[message.getId()]).join(' and ')}`);
      this.loopStore.set(message.getId());
      Object.keys(this.probes[message.getId()]).forEach(name => {
        this.sendMessage(name, new Loop( message.getId()));
      });
  }
  handleProbeMessage(sender: string, message: Probe): void {
    if (typeof this.probes[message.getId()] === 'undefined') {
      this.probes[message.getId()] = {};
    } else {
      this.onLoopDetected(message);
    }
    this.probes[message.getId()][sender] = true;

    // check if we can forward this to anyone
    Object.values(this.friends).forEach(friend => {
      if (typeof this.probes[message.getId()][friend.getName()] === 'undefined') {
        this.probes[message.getId()][friend.getName()] = true;
        this.sendMessage(friend.getName(), new Probe(message.getId()));
      }
    });
    // this.addFriend(message.getSender());
  }
  handleLoopMessage(sender: string, message: Loop): void {
    if (!this.loopStore.has(message.getProbeId())) {
      // console.log(`${this.name} received loop message about ${message.getProbeId()} from ${message.getSender().getName()}`);
      Object.keys(this.probes[message.getProbeId()]).forEach(name => {
        if (name !== sender) {
          this.sendMessage(name, new Loop(message.getProbeId()));
        }
      });
      this.loopStore.set(message.getProbeId());
    } else {
      // console.log(`LOOP ${message.getProbeId()} IS NOT NEW TO ME`);
    }

  }
}
