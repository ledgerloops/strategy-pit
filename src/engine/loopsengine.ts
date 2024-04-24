import EventEmitter from "events";

export class LoopsEngine extends EventEmitter {
    loops: string[];
    constructor() {
        super();
        this.loops = [];
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    handleLoopFound(probeId: string, traceId: string, legId: string, outgoing: { maxBalance: number, exchangeRate: number}, incoming: { maxBalance: number, exchangeRate: number}): void {
        this.emit('debug', `${probeId} ${traceId} ${legId} ${JSON.stringify(outgoing)} ${JSON.stringify(incoming)}`);
        this.loops.push(`${probeId} ${traceId}`);
    }
    getLoops(): string[] {
        return this.loops;
    }
}