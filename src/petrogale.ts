import { Probe } from "./messages.js";
import { BasicMessageForwarder } from "./node.js";
import { Pelican } from "./pelican.js";

export class Petrogale extends Pelican {
  constructor(name: string, messageForwarder?: BasicMessageForwarder) {
    super(name, messageForwarder);
  }
  protected sendExistingProbesToNewFriend(other: string): void {
    Object.entries(this.probes).forEach(([id, probes]) => {
      if (typeof probes[other] === 'undefined') {
        this.probes[id][other] = true;
        this.sendMessage(other, new Probe(id));
      }
    });
  }
}