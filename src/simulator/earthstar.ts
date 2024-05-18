import { MixedNetworkSimulator, TransportPackage } from "./networksimulator.js";

export class EarthstarMessaging {
    networkSimulator: MixedNetworkSimulator;
    constructor(networkSimulator: MixedNetworkSimulator) {
        // console.log('EarthstarMessaging instantiated');
        this.networkSimulator = networkSimulator;
    }
    send(transportPackage: TransportPackage): void {
        // console.log('EarthstarMessaging.send', transportPackage);
        this.networkSimulator.receive(transportPackage);
    }
}