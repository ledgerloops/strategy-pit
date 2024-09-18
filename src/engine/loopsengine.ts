import EventEmitter from "events";
import { genRanHex } from "../genRanHex.js";
import { createHmac } from "node:crypto";

function sha256(secret: string): string {
  return createHmac('sha256', secret).digest('hex');
}

export class GiraffeLoopsEngine extends EventEmitter {
  profit: number;
  loops: string[];
  announcements: string[][];
  lifts: {
    [hash: string]: {
      loop: string,
      legId: string,
      secret?: string,
      incomingAmount?: number,
      outgoingAmount: number
    }
  }
  constructor() {
    super();
    this.loops = [];
    this.announcements = [];
    this.lifts = {};
    this.profit = 0.01;
  }
  setProfit(profit: number): void {
    this.profit = profit;
  }
  makeProfit(incomingAmount: number): number {
    return incomingAmount * (1 - this.profit);
  }
  recordAnnouncement(announcement: string[]): void {
    this.announcements.push(announcement);
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  handleLoopFound(probeId: string, traceId: string, legId: string, outgoing: { name: string, maxBalance: number, exchangeRate: number }, incoming: { name: string, maxBalance: number, exchangeRate: number }): void {
    this.recordLoop(incoming.name, outgoing.name, probeId, traceId, legId);
    this.emit('debug', `${probeId} ${traceId} ${legId} ${JSON.stringify(outgoing)} ${JSON.stringify(incoming)}`);
    const spec = {
      sender: incoming.name,
      probeId,
      traceId,
      legId
    };
    this.emit('lookup-trace', spec, (_traceTo: string | undefined, equivalent: string[]) => {
      this.emit('debug', `Trace lookup found equivalents ${JSON.stringify(equivalent)}`);
      const duplicates = [`${probeId} ${traceId} ${legId}`].concat(equivalent.map(traceSpec => {
        const [probeId, traceId, legId] = traceSpec.split(' ');
        return { thisProbeId: probeId, traceId, legId };
      }).filter(({ thisProbeId }) => {
        return (probeId !== thisProbeId);
      }).map(({ thisProbeId, traceId, legId}) => {
        return `${thisProbeId} ${traceId} ${legId}`;
      }));
      this.recordAnnouncement(duplicates);
      this.emit('message', outgoing.name, `announce ${duplicates.join(' === ')}`);
    });
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  handleAnnounceComplete(probeId: string, traceId: string, legId: string, outgoing: { name: string, maxBalance: number, exchangeRate: number }): void {
    const secret = genRanHex(32);
    const hash = sha256(secret);
    this.emit('debug', `secret is ${secret} and hash is ${hash}`);

    // const hash: string = SHA256(secret).toString();
    this.emit('message', outgoing.name, `propose ${probeId} ${traceId} ${legId} ${hash} 1`);
    this.lifts[hash] = {
      loop: `${probeId} ${traceId}`,
      legId,
      secret,
      outgoingAmount: 1,
    };
  }
  recordLoop(from: string, to: string, probeId: string, traceId: string, legId: string): void {
    const str = `${from} ${to} ${probeId} ${traceId} ${legId}`;
    if (this.loops.indexOf(str) === -1) {
      this.loops.push(str);
    }
  }
  handleAnnounceMessage(sender: string, message: string): void {
    const strings = message.substring(`announce `.length).split(' === ');
    const parsed = strings.map(spec => {
      const [ probeId, traceId, legId ] = spec.split(' ');
      return { probeId, traceId, legId };
    });
    let done = false;
    this.emit('debug', `checking if announcement is ours ${JSON.stringify(this.announcements)} ${JSON.stringify(strings)}`);
    this.announcements.forEach(sent => {
      if (JSON.stringify(sent) === JSON.stringify(strings)) {
          this.emit('debug', `ANNOUNCE COMPLETE ${sender} ${JSON.stringify(strings)}`);
        done = true;
        this.handleAnnounceComplete(parsed[0].probeId, parsed[0].traceId, parsed[0].legId, { name: '?', maxBalance: 0, exchangeRate: 1});
      }
    });
    if (!done) {
      this.emit('debug', `ANNOUNCE ${sender} ${JSON.stringify(parsed)}, checking our loops ${JSON.stringify(this.loops)}`);
      let forwardTo: string;
      parsed.forEach(announcement => {
        this.emit('lookup-trace', { sender, ... announcement }, (traceTo: string | undefined, equivalent: string[]) => {
          this.emit('debug', `Trace lookup found equivalents ${JSON.stringify(equivalent)}`);
          if (typeof traceTo !== 'undefined') {
            this.recordLoop(sender, traceTo, announcement.probeId, announcement.traceId, announcement.legId);
          }
        });
        let known = false;
        this.loops.forEach(loopStr => {
          const [ from, to, probeId, traceId, legId ] = loopStr.split(' ');
          this.emit('debug', `considering "${message}" against "${loopStr}"`);
          if ((announcement.probeId === probeId) && (announcement.traceId === traceId) && (announcement.legId === legId)) {
            this.emit('debug', `KNOWN LOOP IN ANOUNCEMENT ${from} ${to} ${probeId} ${traceId} ${legId} - comparing ${JSON.stringify(sender)} ${JSON.stringify(from)} ${JSON.stringify(to)}`);
            known = true;
            let thisForwardTo: string;
            if (from === sender) {
              thisForwardTo = to;
            }
            if (to === sender) {
              thisForwardTo = from;
            }
            if (typeof forwardTo === 'undefined') {
              this.emit('debug', `SETTING forwardTo ${thisForwardTo}`);
              forwardTo = thisForwardTo;
            } else if (thisForwardTo === forwardTo) {
              this.emit('debug', `CONFIRMING forwardTo ${forwardTo}`);
            } else {
              this.emit('debug', `FORK FOUND! thisForwardTo ${thisForwardTo} forwardTo ${forwardTo}`);
              // TODO: handle this case
            }
          }
        });
        if (!known) {
          // this.recordLoop(...
        }
      });
      if (typeof forwardTo === 'string') {
        this.emit('message', forwardTo, message);
      }
    }
  }
  handleProposeMessage(from: string, message: string, proposer: { name: string, maxBalance: number, exchangeRate: number }, committer: { name: string, maxBalance: number, exchangeRate: number }): void {
    this.emit('debug', `${from} ${message} ${JSON.stringify(committer)} ${JSON.stringify(proposer)}`);
    const [messageType, probeId, traceId, legId, hash, amount] = message.split(' ');
    this.recordLoop(proposer.name, committer.name, probeId, traceId, legId);
    if (messageType !== 'propose') {
      this.emit('debug', `expected propose message but got ${messageType}`);
    }
    if (typeof this.lifts[hash] !== 'undefined') {
      this.lifts[hash].incomingAmount = parseFloat(amount);
      this.emit('debug', `initiator decides on lift: is ${this.lifts[hash].incomingAmount} more than ${this.lifts[hash].outgoingAmount}?`);
      if (this.lifts[hash].incomingAmount >= this.lifts[hash].outgoingAmount) {
        this.emit('message', proposer.name, `commit ${probeId} ${traceId} ${legId} ${hash} ${this.lifts[hash].incomingAmount} ${this.lifts[hash].secret}`);
      }
    } else {
      const incomingAmount = parseFloat(amount);
      const outgoingAmount = this.makeProfit(incomingAmount * proposer.exchangeRate / committer.exchangeRate);
      this.lifts[hash] = {
        loop: `${probeId} ${traceId}`,
        legId,
        incomingAmount,
        outgoingAmount,
      }
      this.emit('debug', `forwarding propose ${JSON.stringify(this.lifts[hash])}`);
      this.emit('message', committer.name, `propose ${probeId} ${traceId} ${legId} ${hash} ${outgoingAmount}`);
    }
  }
  handleCommitMessage(from: string, message: string, committer: { name: string, maxBalance: number, exchangeRate: number }, proposer: { name: string, maxBalance: number, exchangeRate: number }): void {
    this.emit('debug', `${from} ${message} ${JSON.stringify(committer)} ${JSON.stringify(proposer)}`);
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const [messageType, probeId, traceId, legId, hash, amount, secret] = message.split(' ');
    if (messageType !== 'commit') {
      this.emit('debug', `expected commit message but got ${messageType}`);
      return;
    }
    if (typeof this.lifts[hash] === 'undefined') {
      this.emit('debug', `commit message for unknown hash ${hash}`);
      return;
    }
    this.emit('debug', `${message} is about ${JSON.stringify(this.lifts[hash])}`);
    if (amount !== this.lifts[hash].outgoingAmount.toString()) {
      this.emit('debug', `commit message for hash ${hash} with unexpected amount ${amount} != ${this.lifts[hash].outgoingAmount}`);
      return;
    }
    if (hash !== sha256(secret)) {
      this.emit('debug', `commit message for hash ${hash} with unexpected secret ${secret}`);
      return;
    }
    if (typeof this.lifts[hash].secret !== 'undefined') {
      // we are not the initiator
      this.emit('debug', 'lift was successfully completed');
    } else {
      this.lifts[hash].secret = secret;
      this.emit('debug', `forwarding commit ${JSON.stringify(this.lifts[hash])}`);
      this.emit('message', proposer.name, `commit ${probeId} ${traceId} ${legId} ${hash} ${this.lifts[hash].incomingAmount} ${this.lifts[hash].secret}`);
    }
  }
  getLoops(): string[] {
    return this.loops;
  }
}

export class SaigaLoopsEngine extends GiraffeLoopsEngine {
  constructor() {
    super();
  }
  makeProfit(incomingAmount: number): number {
    return incomingAmount;
  }
}
