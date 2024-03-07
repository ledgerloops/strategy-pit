import { Probe, Loop } from "./messages.js";
import { genRanHex } from "./util.js";
import { Salmon } from "./salmon.js";
import { MessageLogger } from "./node.js";

// Pelican nodes always send all the probes they can to all their friends.
// Unlike Salmons, Pelicans are able to fork multiple Loop messages from one successful Probe.
export class Pelican extends Salmon {
  protected pelicanLoops: {
    [probeId: string]: {
      [loopId: string]: boolean
    }
  } = {};
  constructor(name: string, messageLogger?: MessageLogger) {
    super(name, messageLogger);
  }
  protected sendExistingProbesToNewFriend(other: string): void {
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (this.pelicanLoops[id]) {
        // console.log(`existing probe apparently looped back`);
      } else {
        if (typeof probes[other] === 'undefined') {
          this.probes[id][other] = true;
          this.sendMessage(other, new Probe(id));
        }
      }
    });
  }
  getLoops(): string[] {
    const loops: string[] = [];
    Object.keys(this.pelicanLoops).forEach(probeId => Object.keys(this.pelicanLoops[probeId]).forEach(loopId => loops.push(`${probeId}:${loopId}`)));
    return loops;
  }
  onLoopDetected(message: Probe): void {
    // console.log(`LOOP DETECTED!: ${this.name} already has probe ${message.getId()} from (or sent to) ${Object.keys(this.probes[message.getId()]).join(' and ')}`);
    const initialLoopId = genRanHex(8);
    if (typeof this.pelicanLoops[message.getId()] === 'undefined') {
      this.pelicanLoops[message.getId()] = {};
    }
    this.pelicanLoops[message.getId()][initialLoopId] = true;
    Object.keys(this.probes[message.getId()]).forEach(name => {
      this.sendMessage(name, new Loop(message.getId(), initialLoopId));
    });
  }

  handleLoopMessage(sender: string, message: Loop): void {
    if (!this.pelicanLoops[message.getProbeId()] || !this.pelicanLoops[message.getProbeId()][message.getLoopId()]) {
        // console.log(`${this.name} received loop message about ${message.getProbeId()} from ${sender} - loop id ${message.getLoopId()}`);
      let loopId = message.getLoopId();
      Object.keys(this.probes[message.getProbeId()]).forEach(name => {
        if (name !== sender) {
          this.sendMessage(name, new Loop(message.getProbeId(), loopId));
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
}
