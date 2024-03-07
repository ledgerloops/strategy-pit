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
        const initialLoopId = genRanHex(8);
        if (typeof this.pelicanLoops[probeMessage.getId()] === 'undefined') {
          this.pelicanLoops[probeMessage.getId()] = {};
        }
        this.pelicanLoops[probeMessage.getId()][initialLoopId] = true;
        Object.keys(this.probes[probeMessage.getId()]).forEach(name => {
          this.friends[name].receiveMessage(new Loop(this, probeMessage.getId(), initialLoopId));
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
      // when a loop message is received:
      const loopMessage = message as Loop;
      if (!this.pelicanLoops[loopMessage.getProbeId()] || !this.pelicanLoops[loopMessage.getProbeId()][loopMessage.getLoopId()]) {
          // console.log(`${this.name} received loop message about ${loopMessage.getProbeId()} from ${message.getSender().getName()} - loop id ${loopMessage.getLoopId()}`);
        let loopId = loopMessage.getLoopId();
        Object.keys(this.probes[loopMessage.getProbeId()]).forEach(name => {
          if (name !== message.getSender().getName()) {
            this.friends[name].receiveMessage(new Loop(this, loopMessage.getProbeId(), loopId));
            if (typeof this.pelicanLoops[loopMessage.getProbeId()] === 'undefined') {
              this.pelicanLoops[loopMessage.getProbeId()] = {};
            }
            this.pelicanLoops[loopMessage.getProbeId()][loopId] = true;

            // Make sure the next forward (in case of a fork) will use a different loop id
            loopId = genRanHex(8);
          }
        });
      } else {
        // console.log(`LOOP ${loopMessage.getProbeId()} IS NOT NEW TO ME`);
      }
    }
  }
}
