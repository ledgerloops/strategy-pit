import { Message, Meet, Probe, Loop } from "./messages.js";
import { genRanHex } from "./util.js";
import { Node } from "./node.js";
import { Salmon } from "./salmon.js";

// Pelican nodes always send all the probes they can to all their friends.
// Unlike Salmons, Pelicans are able to fork multiple Loop messages from one successful Probe.
export class Pelican extends Salmon {
  protected pelicanLoops: {
    [probeId: string]: {
      [loopId: string]: boolean
    }
  } = {};
 constructor(name: string) {
    super(name);
  }
  meet(other: Node): void {
    this.addFriend(other);
    other.receiveMessage(new Meet(this as Node));
    this.onMeet(other);
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
        friend.receiveMessage(new Probe(this as Node, probeForNewLink));
        return;
      }
    });

    // send existing probes to new friend
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (this.pelicanLoops[id]) {
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
    const loops: string[] = [];
    Object.keys(this.pelicanLoops).forEach(probeId => Object.keys(this.pelicanLoops[probeId]).forEach(loopId => loops.push(`${probeId}:${loopId}`)));
    return loops;
  }
  handleMeetMessage(message: Meet): void {
    this.addFriend(message.getSender());
  }
  handleProbeMessage(message: Probe): void {
    if (typeof this.probes[message.getId()] === 'undefined') {
      this.probes[message.getId()] = {};
    } else {
      // console.log(`LOOP DETECTED!: ${this.name} already has probe ${message.getId()} from (or sent to) ${Object.keys(this.probes[message.getId()]).join(' and ')}`);
      const initialLoopId = genRanHex(8);
      if (typeof this.pelicanLoops[message.getId()] === 'undefined') {
        this.pelicanLoops[message.getId()] = {};
      }
      this.pelicanLoops[message.getId()][initialLoopId] = true;
      Object.keys(this.probes[message.getId()]).forEach(name => {
        this.friends[name].receiveMessage(new Loop(this, message.getId(), initialLoopId));
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
    if (!this.pelicanLoops[message.getProbeId()] || !this.pelicanLoops[message.getProbeId()][message.getLoopId()]) {
        // console.log(`${this.name} received loop message about ${message.getProbeId()} from ${message.getSender().getName()} - loop id ${message.getLoopId()}`);
      let loopId = message.getLoopId();
      Object.keys(this.probes[message.getProbeId()]).forEach(name => {
        if (name !== message.getSender().getName()) {
          this.friends[name].receiveMessage(new Loop(this, message.getProbeId(), loopId));
          if (typeof this.pelicanLoops[message.getProbeId()] === 'undefined') {
            this.pelicanLoops[message.getProbeId()] = {};
          }
          this.pelicanLoops[message.getProbeId()][loopId] = true;

          // Make sure the next forward (in case of a fork) will use a different loop id
          loopId = genRanHex(8);
        }
      });
    } else {
      // console.log(`LOOP ${message.getProbeId()} IS NOT NEW TO ME`);
    }
  }
  receiveMessage(message: Message): void {
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
