from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink
import time
import os


def create_network():

    # Inizializza Mininet con controller remoto (Ryu)
    net = Mininet(
        controller=RemoteController,  # Controller SDN remoto
        switch=OVSSwitch,  # Switch OpenFLow ad alta performance
        link=TCLink,  # TCLink permette di impostare vari parametri per ogni link come banda massima, ritardo, etc...
        autoSetMacs=True  # Assegna automaticamente indirizzi MAC prevedibili e costanti per facilitare test e debug
    )

    info('*** Aggiunta del controller Ryu\n')
    controller = net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',  
        port=6633  
    )
    
    controller_c1 = net.addController(
        'c1',
        controller=RemoteController,
        ip='127.0.0.1',  
        port=6634  
    )
    

    info('*** Aggiunta degli switch\n')
    """Gli switch e i router vengono creati allo stesso modo
    la differenza avviene con le logiche di controllo nel controller SDN per i router
    e nell'abilitazione dell'IP forwarding per gli switch """

    
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    r1 = net.addSwitch('r1', protocols='OpenFlow13')
    r2 = net.addSwitch('r2', protocols='OpenFlow13')
    r3 = net.addSwitch('r3', protocols='OpenFlow13')
    r4 = net.addSwitch('r4', protocols='OpenFlow13')

    info('*** Aggiunta degli host\n')
    h1 = net.addHost('h1', ip='10.1.1.10/24', defaultRoute='via 10.1.1.1')
    h2 = net.addHost('h2', ip='10.1.1.20/24', defaultRoute='via 10.1.1.1')
    h3 = net.addHost('h3', ip='10.1.1.30/24', defaultRoute='via 10.1.1.1')

    h4 = net.addHost('h4', ip='10.2.1.10/24', defaultRoute='via 10.2.1.1')
    h5 = net.addHost('h5', ip='10.2.1.20/24', defaultRoute='via 10.2.1.1')

    h6 = net.addHost('h6', ip='10.3.1.10/24', defaultRoute='via 10.3.1.1')

    h7 = net.addHost('h7', ip='10.4.1.10/24', defaultRoute='via 10.4.1.1')
    h8 = net.addHost('h8', ip='10.4.1.20/24', defaultRoute='via 10.4.1.1')

    h9 = net.addHost('h9', ip='10.8.1.10/24', defaultRoute='via 10.8.1.1')

    info('*** Creazione dei collegamenti con parametri specificati\n')
    net.addLink(h1, s1, bw=54, delay='0.05ms')
    net.addLink(h2, s1, bw=54, delay='0.05ms')
    net.addLink(h3, s1, bw=54, delay='0.05ms')
    net.addLink(s1, r1, bw=1000, delay='0.05ms')

    net.addLink(h4, r3, bw=1, delay='0.5ms')
    net.addLink(h5, r3, bw=1, delay='0.5ms')

    net.addLink(h6, r3, bw=1, delay='0.5ms')

    net.addLink(h7, r2, bw=1000, delay='0.01ms')
    net.addLink(h8, r2, bw=100, delay='0.01ms')  

    net.addLink(h9, r4, bw=100, delay='0.05ms') 

    net.addLink(r1, r2, bw=100, delay='2ms')
    net.addLink(r1, r4, bw=10, delay='2ms')
    net.addLink(r4, r3, bw=50, delay='2ms')
    
    info('*** Costruzione rete\n')
    net.build()
    
    info('***Avvio controller\n')
    controller.start()
    controller_c1.start()
    
    info('***Assegnazione controller')
    s1.start([controller_c1])    
    r1.start([controller])             
    r2.start([controller])
    r3.start([controller])
    r4.start([controller])

    info('*** Rete pronta\n')
    info('*** Avvia il controller Ryu con: ryu-manager rest_router.py --ofp-tcp-listen-port 6633 --verbose \n ryu-manager simple_switch_13.py --ofp-tcp-listen-port 6634 --verbose\n')
    info('*** Poi configura i router tramite REST API\n')

    return net


def display_network_info():
    """Mostra informazioni sulla configurazione di rete"""
    info('\n*** CONFIGURAZIONE DI RETE ***\n')
    info('Subnet configurate:\n')
    info(' 10.1.1.0/24 - H1, H2, H3, S1 (via R1)\n')
    info(' 10.2.1.0/24 - H4, H5 (via R3)\n')
    info(' 10.3.1.0/24 - H6 (via R3)\n')
    info(' 10.4.1.0/24 - H7, H8 (via R2)\n')
    info(' 10.8.1.0/24 - H9 (via R4)\n')
    info('\nSubnet point-to-point:\n')
    info(' 180.1.2.0/30 - R3-R4\n')
    info(' 170.0.0.0/30 - R4-R1\n')
    info(' 100.0.0.0/30 - R1-R2\n')


def main():
    """Funzione principale"""
    setLogLevel('info')

    #Info configurazione
    display_network_info()

    #Creazione rete
    net = create_network()

    try:
        # Avvia CLI per test manuali
        info('\n*** Rete creata. Configura i router tramite REST API prima di testare\n')
        CLI(net)

    finally:
        info('*** Fermata della rete\n')
        net.stop()


if __name__ == '__main__':
    main()
