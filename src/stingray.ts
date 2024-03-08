import { Probe, Loop } from "./messages.js";
import { genRanHex } from "./util.js";
import { Node, MessageForwarder } from "./node.js";

export class StingrayProbeStore {
  private probes: {
    [id: string]: {
      from: string[];
      to: string[];
      flood: boolean;
      homeMinted: boolean;
    }
  } = {};
  constructor() {}
  has(id: string): boolean {
    return (typeof this.probes[id] !== 'undefined');
  }
  get(id: string): {
    from: string[];
    to: string[];
    flood: boolean;
    homeMinted: boolean;
  } {
    return this.probes[id];
  }
  haveSentTo(friend: string, id: string): boolean {
    return (typeof this.probes[id] !== 'undefined' && this.probes[id].to.includes(friend));
  }
  haveReceivedFrom(friend: string, id: string): boolean {
    return (typeof this.probes[id] !== 'undefined' && this.probes[id].from.includes(friend));
  }
  haveSentOrReceived(friend: string, id: string): boolean {
    return (this.haveSentTo(friend, id) || this.haveReceivedFrom(friend, id)); 
  }
  ensure(id: string, flood: boolean, homeMinted: boolean): void {
    if (typeof this.probes[id] === 'undefined') {
      this.probes[id] = { from: [], to: [], flood, homeMinted };
    }
  }
  recordIncoming(id: string, from: string): void {
    if (this.has(id)) {
      if (this.probes[id].flood) {
        // console.log(`RECORDING FLOOD PROBE ${id} COMING IN THROUGH ${from}`);
      } else {
        // console.log(`RECORDING PIN PROBE ${id} COMING IN THROUGH ${from}`);
      }
    } else {
      // console.log(`RECORDING NEW PROBE ${id} COMING IN THROUGH ${from} - MARKING FOR FLOOD`);
      this.ensure(id, true, false);
    }
    if (this.haveReceivedFrom(from, id)) {
      // console.log(`ALREADY RECEIVED PROBE ${id} FROM ${from}`);
    } else {
      this.probes[id].from.push(from);
    }
  }
  recordOutgoing(id: string, to: string, flood: boolean, homeMinted: boolean): void {
    if (this.has(id)) {
      if (this.probes[id].flood !== flood) {
        throw new Error(`PROBE ${id} ALREADY EXISTS AND HAS DIFFERENT FLOOD STATUS`);
      } else if (flood) {
        // console.log(`EXISTING FLOOD PROBE ${id} GOES OUT TO ${to}`);
      } else {
        throw new Error(`PIN PROBES SHOULD BE SENT OUT ONLY ONCE!`);
      }
    } else {
      this.ensure(id, flood, homeMinted);
    }
    this.probes[id].to.push(to);
  }
  getKeys(): string[] {
    return Object.keys(this.probes);
  }
  getProbes(): {
    [id: string]: {
      from: string[];
      to: string[];
    }
  } {
    return this.probes;
  }
  getProbeReport(id: string, sender: string): {
    from: string;
    to: string;
    proofsComm: boolean;
  } {
    if (this.probes[id].flood) {
      throw new Error(`PROBE ${id} IS A FLOOD PROBE`);
    }
    if (this.probes[id].from.length !== 1) {
      throw new Error(`PROBE ${id} HAS BEEN RECEIVED FROM MULTIPLE SOURCES`);
    }
    if (this.probes[id].to.length !== 1) {
      throw new Error(`PROBE ${id} HAS BEEN SENT TO MULTIPLE DESTINATIONS`);
    }
    if (this.probes[id].from[0] !== sender) {
      throw new Error(`PROBE ${id} HAS BEEN RECEIVED FROM ${this.probes[id].from[0]} INSTEAD OF ${sender}`);
    }
    // See https://github.com/ledgerloops/strategy-pit/issues/4#issuecomment-1985648430
    // for theory on proof of communication
    const comm1 = this.probes[id].homeMinted;
    const comm2 = (!this.probes[id].to.includes(sender));
    const proofsComm = comm1 && comm2;
    return { from: this.probes[id].from[0], to: this.probes[id].to[0], proofsComm };
  }
}

export class StingrayLoopStore {
  private loops: {
    [probeId: string]: {
      [loopId: string]: {
        from: string[];
        to: string[];
        homeMinted: boolean;
      }
    }
  } = {};
  constructor() {}
  has(probeId: string, loopId: string): boolean {
    return ((typeof this.loops[probeId] !== 'undefined') && (typeof this.loops[probeId][loopId] !== 'undefined'));
  }
  get(probeId: string, loopId: string): {
    from: string[];
    to: string[];
  } {
    return this.loops[probeId][loopId];
  }
  haveSentTo(friend: string, probeId: string, loopId: string): boolean {
    const { to } = this.get(probeId, loopId);
    return (to.includes(friend));
  }
  haveReceivedFrom(friend: string, probeId: string, loopId: string): boolean {
    const { from } = this.get(probeId, loopId);
    return (from.includes(friend));
  }
  haveSentOrReceived(friend: string, probeId: string, loopId: string): boolean {
    const { from, to } = this.get(probeId, loopId);
    return (from.includes(friend) || to.includes(friend));
  }
  ensure(probeId: string, loopId: string, homeMinted: boolean): void {
    if (typeof this.loops[probeId] === 'undefined') {
      this.loops[probeId] = {};
    }
    if (typeof this.loops[probeId][loopId] === 'undefined') {
      this.loops[probeId][loopId] = { from: [], to: [], homeMinted };
    }
  }
  recordIncoming(probeId: string, loopId: string, from: string): void {
    this.ensure(probeId, loopId, false);
    this.loops[probeId][loopId].from.push(from);
  }
  recordOutgoing(probeId: string, loopId: string, to: string, homeMinted: boolean): void {
    this.ensure(probeId, loopId, homeMinted);
    this.loops[probeId][loopId].to.push(to);
  }
  getKeys(): string[] {
    const loops: string[] = [];
    Object.keys(this.loops).forEach(probeId => Object.keys(this.loops[probeId]).forEach(loopId => loops.push(`${probeId}:${loopId}`)));
    return loops;
  }
  getLoops(): {
    [probeId: string]: {
      [loopId: string]: {
        from: string[];
        to: string[];
      }
    }
  } {
    return this.loops;
  }
}

// Stingray nodes always send all the probes they can to all their friends.
export class Stingray extends Node {
  protected probeStore: StingrayProbeStore = new StingrayProbeStore();
  protected loopStore: StingrayLoopStore = new StingrayLoopStore();

  constructor(name: string, messageForwarder?: MessageForwarder) {
    super(name, messageForwarder);
  }
  protected offerProbe(friend: string, probeId: string, flood: boolean, homeMinted: boolean): void {
    if (!this.probeStore.haveSentOrReceived(friend, probeId)) {
      this.probeStore.recordOutgoing(probeId, friend, flood, homeMinted);
      this.sendMessage(friend, new Probe(probeId));
    }
  }
  protected offerAllFloodProbes(other: string): void {
    this.probeStore.getKeys().forEach((probeId) => {
      this.offerProbe(other, probeId, true, this.probeStore.get(probeId).homeMinted);
    }); 
  }
  protected offerFloodProbeToAll(probeId: string, homeMinted: boolean): void {
    this.getFriends().forEach(friend => {
      this.offerProbe(friend, probeId, true, homeMinted);
    });
  }
  protected createFloodProbe(): void {
    this.offerFloodProbeToAll(genRanHex(8), true);
  }
  protected createPinProbe(recipient: string): void {
    const probeForNewLink = genRanHex(8);
    this.offerProbe(recipient, probeForNewLink, false, true);
  }
  // when this node has sent a `meet` message
  onMeet(other: string): void {
    this.offerAllFloodProbes(other);
    this.createFloodProbe();
  }
  // when this node has received a `meet` message
  handleMeetMessage(sender: string): void {
    this.offerAllFloodProbes(sender);
  }
  getProbes(): {
    [id: string]: {
      from: string[];
      to: string[];
    }
  } {
    return this.probeStore.getProbes();
  }
  getLoops(): {
    [probeId: string]: {
      [loopId: string]: {
        from: string[];
        to: string[];
      }
    }
  } {
    return this.loopStore.getLoops();
  }
  createLoopTrace(probeId: string, friend: string): void {
    const loopId = genRanHex(8);
    this.loopStore.recordOutgoing(probeId, loopId, friend, true);
    this.sendMessage(friend, new Loop(probeId, loopId));
  }
  whenFloodProbeLoopsBack(sender: string): void {
    this.createPinProbe(sender);
  }
  whenPinProbeLoopsBack(probeId: string, sender: string): void {
    this.createLoopTrace(probeId, sender);
  }
  handleProbeMessage(sender: string, message: Probe): void {
    if (this.probeStore.haveReceivedFrom(sender, message.getId())) {
      // console.log(`ALREADY RECEIVED PROBE ${message.getId()} FROM ${sender}`);
      return;
    }
    if (this.probeStore.has(message.getId())) {
      // flood probe looping back on itself, responding with pin probe
      // (see https://github.com/ledgerloops/strategy-pit/issues/4)
      this.whenFloodProbeLoopsBack(sender);
      return;
    }
    // INCOMING PROBE IS NEW TO US, FLOOD IT FORWARD
    this.probeStore.recordIncoming(message.getId(), sender);
    this.offerFloodProbeToAll(message.getId(), false);
  }
  handleLoopMessage(sender: string, message: Loop): void {
    if (this.loopStore.has(message.getProbeId(), message.getLoopId())) {
      if (this.loopStore.haveReceivedFrom(sender, message.getProbeId(), message.getLoopId())) {
        // console.log(`NEIGHBOUR ${sender} IS REPEATING LOOP TRACE ${message.getLoopId()} FOR PROBE ${message.getProbeId()} TO US?`);
      } else if (this.loopStore.haveSentTo(sender, message.getProbeId(), message.getLoopId())) {
        // console.log(`NEIGHBOUR ${sender} IS ECHOING LOOP TRACE ${message.getLoopId()} FOR PROBE ${message.getProbeId()} BACK TO US?`);
      } else {
        // console.log(`LOOP TRACE ${message.getLoopId()} FOR PROBE ${message.getProbeId()} COMING TO US FROM UNEXPECTED SENDER ${sender}`);
      }
    } else {
      this.loopStore.recordIncoming(message.getProbeId(), message.getLoopId(), sender);
      const recipients = this.probeStore.get(message.getProbeId()).from;
      let used = false;
      recipients.forEach(recipient => {
        if (used) {
          const newLoopId = genRanHex(8);
          this.loopStore.recordOutgoing(message.getProbeId(), newLoopId, recipient, true);
          this.sendMessage(recipients[0], new Loop(message.getProbeId(), newLoopId));
        } else {
          used = true;
          this.loopStore.recordOutgoing(message.getProbeId(), message.getLoopId(), recipient, false);
          this.sendMessage(recipient, message);
        }
      });
    }
  }
}
