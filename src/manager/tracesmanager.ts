import EventEmitter from "node:events";

export class TracesManager extends EventEmitter {
  handleProbeLoopback(probeId: string, situation: string, from: string[], to: string[]): void {
    this.emit('debug', `handleProbeLoopback ${probeId} ${situation} ${from.join(' ')} ${to.join(' ')}`);
  }
}
  