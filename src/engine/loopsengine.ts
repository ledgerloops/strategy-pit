import EventEmitter from "events";

export class LoopsEngine extends EventEmitter {
    loops: string[];
    constructor() {
        super();
        this.loops = [];
    }
    handleLoopFound(probeId: string, traceId: string): void {
        this.loops.push(`${probeId} ${traceId}`);
    }
    getLoops(): string[] {
        return this.loops;
    }
}