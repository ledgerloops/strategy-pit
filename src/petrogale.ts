import { Probe } from "./messages.js";
import { Node } from "./node.js";
import { Pelican } from "./pelican.js";

export class Petrogale extends Pelican {
  constructor(name: string) {
    super(name);
  }
  protected sendExistingProbesToNewFriend(other: Node): void {
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (typeof probes[other.getName()] === 'undefined') {
        this.probes[id][other.getName()] = true;
        this.sendMessage(other, new Probe(this, id));
      }
    });
  }
}