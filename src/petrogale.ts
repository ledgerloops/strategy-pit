import { Meet, Probe } from "./messages.js";
import { genRanHex } from "./util.js";
import { Node } from "./node.js";
import { Pelican } from "./pelican.js";

export class Petrogale extends Pelican {
  constructor(name: string) {
    super(name);
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
      if (typeof probes[other.getName()] === 'undefined') {
        this.probes[id][other.getName()] = true;
        other.receiveMessage(new Probe(this, id));
      }
    });
  }
  meet(other: Node): void {
    this.addFriend(other);
    other.receiveMessage(new Meet(this as Node));
    this.onMeet(other);
  }
}