import { Probe } from "./messages.js";
import { Pelican } from "./pelican.js";

export class Petrogale extends Pelican {
  constructor(name: string) {
    super(name);
  }
  protected sendExistingProbesToNewFriend(other: string): void {
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (typeof probes[other] === 'undefined') {
        this.probes[id][other] = true;
        this.sendMessage(other, new Probe(this, id));
      }
    });
  }
}