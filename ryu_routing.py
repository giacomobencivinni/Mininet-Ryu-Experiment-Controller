import requests
import time

BASE = "http://127.0.0.1:8080" 

def dpid_of(name: str) -> str:
    assert name[0] in ("r", "s"), "Atteso prefisso r/s"
    num = int(name[1:])
    return f"{num:016x}"

def post(url, data):
    r = requests.post(url, json=data, timeout=5)
    r.raise_for_status()
    return r.json()

def add_addr(router, cidr, vlan=None):
    path = f"/router/{dpid_of(router)}" + (f"/{vlan}" if vlan is not None else "")
    print(f"[{router}] + address {cidr}")
    return post(BASE + path, {"address": cidr})

def add_route(router, dest, gw, vlan=None):
    path = f"/router/{dpid_of(router)}" + (f"/{vlan}" if vlan is not None else "")
    payload = {"destination": dest, "gateway": gw}
    print(f"[{router}] + route {dest} via {gw}")
    return post(BASE + path, payload)

def add_default(router, gw, vlan=None):
    path = f"/router/{dpid_of(router)}" + (f"/{vlan}" if vlan is not None else "")
    print(f"[{router}] + default via {gw}")
    return post(BASE + path, {"gateway": gw})

def main():
    
    add_addr("r1", "10.1.1.1/24")
    add_addr("r1", "100.0.0.1/30")
    add_addr("r1", "170.0.0.1/30")

    add_addr("r2", "10.4.1.1/24")
    add_addr("r2", "100.0.0.2/30")

    add_addr("r3", "10.2.1.1/24")
    add_addr("r3", "10.3.1.1/24")
    add_addr("r3", "180.1.2.1/30")

    add_addr("r4", "10.8.1.1/24")
    add_addr("r4", "170.0.0.2/30")
    add_addr("r4", "180.1.2.2/30")

    #Piccola pausa per far aggiornare le tabelle interne
    time.sleep(0.5)

    #R1: raggiunge le LAN dietro R2 e R3/R4
    add_route("r1", "10.4.1.0/24", "100.0.0.2")     
    add_route("r1", "10.8.1.0/24", "170.0.0.2")    
    add_route("r1", "10.2.1.0/24", "170.0.0.2")    
    add_route("r1", "10.3.1.0/24", "170.0.0.2")    

    # R2: raggiunge il resto passando da R1
    add_route("r2", "10.1.1.0/24", "100.0.0.1")
    add_route("r2", "10.8.1.0/24", "100.0.0.1")    
    add_route("r2", "10.2.1.0/24", "100.0.0.1")    
    add_route("r2", "10.3.1.0/24", "100.0.0.1")

    # R3: tutto tramite R4
    add_route("r3", "10.1.1.0/24", "180.1.2.2")    
    add_route("r3", "10.4.1.0/24", "180.1.2.2")   
    add_route("r3", "10.8.1.0/24", "180.1.2.2")    

    # R4: instrada verso R1 e R3
    add_route("r4", "10.1.1.0/24", "170.0.0.1")   
    add_route("r4", "10.4.1.0/24", "170.0.0.1")   
    add_route("r4", "10.2.1.0/24", "180.1.2.1")   
    add_route("r4", "10.3.1.0/24", "180.1.2.1")   

    print("\nConfigurazione completata. Verifica con:")
    for r in ("r1", "r2", "r3", "r4"):
        print(f"  curl {BASE}/router/{dpid_of(r)}")

if __name__ == "__main__":
    main()
