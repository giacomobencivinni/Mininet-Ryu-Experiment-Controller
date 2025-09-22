# Mininet-Ryu-Experiment-Controller
Emulated SDN network in Mininet with Ryu controller, featuring 4 routers, 1 switch, and 9 hosts. A Flask-based Experiment Controller manages traffic experiments toward an IPERF server, collecting throughput results to evaluate performance and resource sharing.

## Obiettivi e vincoli

Il progetto ha come obiettivo la realizzazione di una rete emulata in Mininet, composta da 4 router, 1 switch e  9 host, configurata secondo una topologia predefinita e con indirizzamenti IP e parametri di banda e ritardo specificati. Sul nodo H6 viene sviluppato un server HTTP, denominato *Experiment Controller*, basato su Flask e dotato di API REST per la gestione di esperimenti di traffico verso l’host H7 (IPERF Server).

Gli esperimenti prevedono l’attivazione sequenziale dei flussi di ciascun host ogni 30 secondi, con protocolli e data-rate configurabili, e la terminazione simultanea dei flussi dopo che l’ultimo host ha trasmesso per almeno 30 secondi. I risultati, raccolti e salvati in formati standard, comprendono in particolare il throughput per evidenziare le prestazioni della rete e l’impatto della condivisione delle risorse.

## Ambiente di Sviluppo

Per lo sviluppo di questo progetto si è optato per una configurazione dell’ambiente Linux su una macchina virtuale tramite OracleVirtualBox, con installazione di Ubuntu, per sfruttare la predisposiione nativa di Mininet. È stato necessario installare pyenv per gestire versioni multiple di Python, a causa di problemi di incompatibilità tra la versione di default Python 3.10 presente sulla VM e le ultime versioni di Mininete, Eyu controller e Flask. 

## Schema Architetturale del Sistema

Il sistema implementato segue un'architettura SDN (Software Defined Network) con i seguenti componenti principali:

### 1. Piano Dati

- **4 Router L3** (r1, r2, r3, r4): implementati come switch OpenFlow per il controllo SDN
- **1 Switch L2** (s1): per la gestione del traffico nella subnet 10.1.1.0/24
- **9 Host** (h1-h9): distribuiti nelle diverse subnet secondo la topologia

### 2. Piano Controllo

- **Controller Ryu primario** (porta 6633): gestisce il routing L3 tramite rest_router
- **Controller Ryu secondario** (porta 6634): gestisce il forwarding L2 tramite simple_switch_13

### 3. Piano Applicativo

- **Experiment Controller** (H6): server Flask con API REST per orchestrazione esperimenti
- **IPERF Server** (H7): destinazione del traffico di test

## Topologia di Rete

La topologia di rete è stata implementata utilizzando Mininet, con quattro nodi configurati come router L3 (r1, r2, r3, r4), un unico switch L2 (s1) e nove host (h1-h9):

- I router e lo switch sono stati modellati come switch OpenFlow per poterli controllare tramite un controller SDN Ryu.
- Gli host sono stati configurati con indirizzi IP nelle rispettive subnet, rispettando l’assegnazione indicata.
- Sono stati definiti anche i link point-to-point tra router con subnet /30 dedicate, come da specifica.

## Configurazoini IP e Routing tramite REST API

La configurazione degli indirizzi IP e delle tabelle di routing è stata realizzata utilizzando le **REST API del controller Ryu**, in particolare tramite il modulo *rest_router.py*. In questo modo è stato possibile assegnare in maniera programmabile gli indirizzi IP alle interfacce dei router, rispettando fedelmente le sottoreti previste dalla topologia emulata in Mininet. Sono state configurate sia le interfacce verso le LAN degli host, sia i collegamenti punto-punto tra i diversi router. Parallelamente, sono state definite rotte statiche coerenti con la struttura della rete, garantendo la piena raggiungibilità end-to-end fra tutti i nodi. L’utilizzo delle REST API ha consentito di evitare configurazioni manuali sulle interfacce di Mininet, permettendo invece una gestione dinamica e centralizzata attraverso il controller SDN.

### Controller Flask “Experiment Controller” su H6

Sul nodo H6 è stato sviluppato l’**Experiment Controller**, un server HTTP basato su Flask che espone un insieme di API REST per la gestione degli esperimenti di performance. Questo componente riceve dall’utente le configurazioni di traffico per ciascun host (esclusi H6 e H7), comprendenti il protocollo di trasporto scelto (TCP o UDP) e il data-rate applicativo desiderato. Una volta ricevute le specifiche, il controller si occupa di avviare in maniera controllata le sessioni di traffico, sfruttando  mnexec per eseguire i comandi direttamente sugli host emulati. In parallelo, su H7 viene attivato un server *iperf3* che rimane in esecuzione per l’intera durata dell’esperimento e funge da punto di raccolta dei flussi generati dagli altri host.

### API REST Implementate:

- **POST /start_experiment**: avvia un nuovo esperimento
- **GET /experiment_status**: stato corrente dell'esperimento
- **GET /results**: recupera risultati (con filtro per experiment_id)
- **GET /results/current**: risultati dell'esperimento in corso
- **GET /hosts**: lista host disponibili
- **POST /stop_experiment**: termina esperimento corrente
- **GET /health**: verifica stato del servizio

## Test di raggiungibilità host

Prima di continuare con lo sviluppo del server_flask.py si è verificato che tutti gli host potessero comunicare correttamente, tramite l’utilizzo del comando pingall, che verifica l’invio e la ricezione di pacchetti verso tutti i nodi della rete:
![]()

## Analisi e validazione delle specifiche richieste

| **Requisito progetto** | Soddisfacimento del requisito |
| --- | --- |
| **1. Tutti gli host devono essere raggiungibili fra loro** | In **mininet_topology.py** vengono creati i router (R1–R4) e collegati con link P2P.<br><br>In **ryu_routing.py** vengono assegnati indirizzi IP coerenti alle interfacce router (add_addr) e definite le rotte statiche (add_route) che garantiscono connettività end-to-end tra tutte le sottoreti.<br><br>È stata correttamente verificata tramite comando `pingall` in Mininet. |
| **2. Gli indirizzamenti IP devono rispettare le sottoreti indicate nello schema** | In **mininet_topology.py** ogni host è creato con un IP coerente alla sua subnet (es. h1 = 10.1.1.10/24, h4 = 10.2.1.10/24, ecc.).<br><br>In **ryu_routing.py** i router sono configurati con gli indirizzi gateway corrispondenti.<br>Sono gestiti anche i link P2P tra router (100.0.0.0/30, 170.0.0.0/30, 180.1.2.0/30). |
| **3. I link emulati devono avere rate e ritardo come nello schema** | In **mininet_topology.py**, la funzione `net.addLink()` assegna a ciascun collegamento banda e delay. |
| **4. Sul nodo H6 sviluppare un server Flask "EXPERIMENT CONTROLLER" con REST API** | In **server_flask.py** è implementata un’app Flask che gira su H6.<br><br>Espone API REST (`/start_experiment`, `/stop_experiment`, `/results`, `/experiment_status`, ecc.).<br><br>Riceve la configurazione di traffico da parte dell’utente (host, protocollo TCP/UDP, data-rate).<br>Lancia i comandi `iperf3` sugli host tramite `mnexec_cmd()`. |
| **5. Esperimento di traffico sequenziale verso H7 (IPERF SERVER)** | In **server_flask.py**, la funzione `run_experiment_sequence()` gestisce la sequenza nel seguente modo: H1 parte a t=0, ogni host successivo parte con offset di 30 secondi, tutti gli stream terminano simultaneamente.<br><br>Su H7 viene avviato un server `iperf3` per tutta la durata (`start_iperf_server()`). |
| **6. Salvataggio log in formato standard (json/)** | In **server_flask.py**, la funzione `save_result()` salva i risultati di throughput in un file JSON (`experiment_results.json`).<br><br>Sono gestite corse multiple concorrenti con adeguata sincronizzazione tramite locking.<br><br>I dati includono: host, protocollo, bitrate, throughput, start/end time, durata. |
| **7. Test con massimo rate per saturazione banda** | Supportato dall’API `/start_experiment`: l’utente può configurare gli host con data-rate pari alla capacità del link, saturando la rete e osservando eventuali degradi delle prestazioni. |
| **8. Analisi grafica del throughput** | Dai dati salvati in JSON si possono generare grafici temporali di throughput per host, mostrando l’effetto dell’attivazione sequenziale dei flussi. |
|

## Istruzioni d’uso

1. Avvio della rete mininet: aprire un terminale e avviare la mininet eseguendo `sudo python3 mininet_topology.py` 
2.  Avvio del controller ryu: in due terminali separati avviare i due controller necessari. 
Controller principale sulla porta 6633, che gestisce il routing REST:`ryu-manager --ofp-tcp-listen-port 6633 --verbose ryu.app.rest_router`
Secondo controller sulla porta 6634, che gestisce lo switch semplice:`ryu-manager --ofp-tcp-listen-port 6634 --verbose ryu.app.simple_switch.13` 
3.  Configurazione del routing tramite script**:** Questo script imposta le interfacce IP e le rotte statiche per garantire la raggiungibilità end-to-end, eseguendo ****`ryu_routing.py` 
4.  Sul nodo H6, avviare il server Flask che controlla gli esperimenti di traffico e la raccolta dati. Questo comando lancia il controller di esperimenti in background, pronto a ricevere richieste API REST per gestire i test di performance: `h6 sudo python3 server_flask.py &`
5. Eseguire gli esperimenti seguendo la sintassi del seguente esempio: 
    
    ```markdown
    h1 curl -X POST http://10.3.1.10:5000/start_experiment \
      -H "Content-Type: application/json" \
      -d '{
        "hosts": {
          "h1": {"protocol": "TCP", "bitrate": "10M"},
          "h2": {"protocol": "TCP", "bitrate": "10M"},
          "h3": {"protocol": "UDP", "bitrate": "5M"},
          "h4": {"protocol": "TCP", "bitrate": "1M"},
          "h5": {"protocol": "TCP", "bitrate": "1M"},
          "h8": {"protocol": "TCP", "bitrate": "50M"},
          "h9": {"protocol": "TCP", "bitrate": "10M"}
        }
      }'
    ```
    
6. Monitorare i risultati tramite i seguenti comandi
    
    ```markdown
    # Stato esperimento
    h1 curl http://10.3.1.10:5000/experiment_status
    
    # Risultati
    h1 curl http://10.3.1.10:5000/results
    
    # Risultati esperimento corrente
    h1 curl http://10.3.1.10:5000/results/current
    ```
