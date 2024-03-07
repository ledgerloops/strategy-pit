export abstract class Message {
  abstract getMessageType(): string;
  abstract toString(): string; 
}

export class Meet extends Message {
  getMessageType(): string {
    return 'meet';
  }
  toString(): string {
    return 'meet';
  }
}

export class Probe extends Message {
  private id: string;
  constructor(id: string) {
      super();
      this.id = id;
  }
  getMessageType(): string {
    return 'probe';
  }
  getId(): string {
    return this.id;
  }
  toString(): string {
    return `probe ${this.id}`;
  }
}

export class Loop extends Message {
  private loopId: string;
  private probeId: string;
  constructor(probeId: string, loopId?: string) {
      super();
      this.probeId = probeId;
      this.loopId = loopId  || 'default';
  }
  getMessageType(): string {
    return 'loop';
  }
  getProbeId(): string {
    return this.probeId;
  }
  getLoopId(): string {
    return this.loopId;
  }
  toString(): string {
    return `loop ${this.probeId} ${this.loopId}`;
  }

}
