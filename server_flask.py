from flask import Flask, request, jsonify
import subprocess
import threading
import time
import json
from datetime import datetime
import os
import signal
import sys
import logging

#psutil è opzionale: se non presente usa pgrep come fallback
try:
    import psutil
except Exception:
    psutil = None

app = Flask(__name__)

IPERF_SERVER_HOST = "10.4.1.10"  # H7 (iPerf server)
JSON_RESULTS = "experiment_results.json"
EXPERIMENT_DURATION_PER_HOST = 30  # offset tra attivazioni (s)
EXCLUDED_HOSTS = {"h6", "h7"}  # esclude Experiment Controller (H6) e iPerf Server (H7)

HOSTS_CONFIG = {
    "h1": "10.1.1.10",
    "h2": "10.1.1.20",
    "h3": "10.1.1.30",
    "h4": "10.2.1.10",
    "h5": "10.2.1.20",
    "h6": "10.3.1.10",  
    "h7": "10.4.1.10",  
    "h8": "10.4.1.20",
    "h9": "10.8.1.10"
}

# Stato globale (protezione con state_lock)
experiment_state = {
    "running": False,
    "current_experiment_id": None,
    "active_hosts": [],
    "results": [],
    "start_time": None,
    "iperf_server_process": None
}

json_lock = threading.Lock()
state_lock = threading.Lock()

def find_mininet_processes():
    processes = {}
    if psutil is None:
        return processes
    try:
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if not cmdline:
                    continue
                cmdline_str = ' '.join(cmdline)
                if 'mininet:' in cmdline_str:
                    for part in cmdline:
                        if part.startswith('mininet:'):
                            hostname = part.split(':', 1)[1]
                            processes[hostname] = proc.info['pid']
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return processes

def get_host_pid(hostname: str):
    procs = find_mininet_processes()
    if hostname in procs:
        return procs[hostname]
    patterns = [
        f"mininet:{hostname}",
        f"mnexec.*{hostname}",
        f"mininet.*{hostname}",
    ]
    for pat in patterns:
        try:
            res = subprocess.run(['pgrep', '-f', pat], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                return int(res.stdout.strip().splitlines()[0])
        except Exception:
            continue
    app.logger.error(f"get_host_pid: PID non trovato per {hostname} (patterns provati: {patterns})")
    return None

def mnexec_cmd(hostname: str, cmd: list, background=False, timeout=None):
    pid = get_host_pid(hostname)
    if not pid:
        app.logger.error(f"mnexec_cmd: PID non trovato per {hostname}")
        return None
    base_cmd = ["sudo", "mnexec", "-a", str(pid)] + cmd
    try:
        if background:
            proc = subprocess.Popen(
                base_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  
            )
            return proc
        else:
            cp = subprocess.run(base_cmd, capture_output=True, text=True, timeout=timeout)
            return cp
    except Exception as e:
        app.logger.error(f"mnexec_cmd errore su {hostname}: {e}")
        return None

def save_result(result: dict):
    # salva su JSON (append)
    with json_lock:
        try:
            data = []
            if os.path.exists(JSON_RESULTS):
                try:
                    with open(JSON_RESULTS, "r") as f:
                        data = json.load(f)
                except json.JSONDecodeError:
                    app.logger.warning("JSON corrotto, ricreo")
                    data = []
            data.append(result)
            with open(JSON_RESULTS, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            app.logger.error(f"save_result JSON error: {e}")

def parse_iperf_text_fallback(output: str) -> float:
    try:
        for line in output.splitlines():
            if 'bits/sec' in line and ('sender' in line or 'receiver' in line):
                parts = line.split()
                for i, part in enumerate(parts):
                    if 'bits/sec' in part and i > 0:
                        val = parts[i-1]
                        try:
                            num = float(val)
                            if 'Gbits' in part:
                                return num * 1000.0
                            if 'Mbits' in part:
                                return num
                            if 'Kbits' in part:
                                return num / 1000.0
                        except Exception:
                            continue
    except Exception:
        pass
    return 0.0

def parse_iperf_output(output: str) -> float:
    if not output:
        return 0.0
    try:
        j = json.loads(output)
    except Exception:
        return parse_iperf_text_fallback(output)
    end = j.get("end", {})
    candidates = []
    for key in ("sum_received", "sum_sent", "sum"):
        if isinstance(end.get(key), dict):
            bps = end[key].get("bits_per_second")
            if bps is not None:
                candidates.append(bps)
    streams = end.get("streams", [])
    for s in streams:
        for side in ("recv", "send"):
            sec = s.get(side)
            if isinstance(sec, dict):
                bps = sec.get("bits_per_second")
                if bps is not None:
                    candidates.append(bps)
    for bps in candidates:
        try:
            mbps = float(bps) / 1_000_000.0
            return round(mbps, 3)
        except Exception:
            continue
    return 0.0

def start_iperf_server():
    try:
        chk = mnexec_cmd("h7", ["pgrep", "-f", "iperf3"], background=False, timeout=2)
        if chk and getattr(chk, "returncode", 1) == 0 and chk.stdout.strip():
            app.logger.info("iperf3 già in esecuzione su H7: provo a terminarlo (pkill in H7)")
            mnexec_cmd("h7", ["pkill", "-f", "iperf3"], background=False, timeout=2)
            time.sleep(1.0)
    except Exception:
        pass
    proc = mnexec_cmd("h7", ["iperf3", "-s", "-p", "5201"], background=True)
    if proc:
        app.logger.info("Server iperf avviato su H7 (mnexec background)")
        time.sleep(1.5)
    else:
        app.logger.error("Impossibile avviare server iperf su H7")
    return proc

def stop_iperf_server(proc):
    if proc and isinstance(proc, subprocess.Popen):
        try:
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait()
            app.logger.info("iperf server (proc) terminato")
        except Exception as e:
            app.logger.warning(f"Errore terminazione proc iperf: {e}")
    try:
        mnexec_cmd("h7", ["pkill", "-f", "iperf3"], background=False, timeout=2)
    except Exception:
        pass

def run_traffic_test(hostname, ip, protocol, bitrate, duration, experiment_id, delay_before_start=0):
    app.logger.info(f"[{hostname}] scheduled delay={delay_before_start}s dur={duration}s proto={protocol} br={bitrate}")
    if delay_before_start > 0:
        waited = 0.0
        step = 0.5
        while waited < delay_before_start:
            with state_lock:
                if not experiment_state["running"]:
                    app.logger.info(f"[{hostname}] cancellato (esperimento fermato)")
                    return None
            time.sleep(step)
            waited += step
    with state_lock:
        if not experiment_state["running"]:
            return None
    start_time = datetime.now().isoformat()
    cmd = ["iperf3", "-c", IPERF_SERVER_HOST, "-t", str(duration), "-p", "5201", "-J"]
    if str(protocol).lower() == "udp":
        cmd += ["-u", "-b", str(bitrate)]
    app.logger.debug(f"[{hostname}] cmd: {' '.join(cmd)}")
    cp = mnexec_cmd(hostname, cmd, background=False, timeout=duration + 20)
    end_time = datetime.now().isoformat()
    if cp is None:
        app.logger.error(f"[{hostname}] mnexec_cmd fallito")
        throughput = 0.0
    else:
        stdout = getattr(cp, "stdout", "") or ""
        stderr = getattr(cp, "stderr", "") or ""
        returncode = getattr(cp, "returncode", -1)
        if stderr:
            app.logger.debug(f"[{hostname}] stderr (troncato): {stderr[:200]}")
        if returncode != 0:
            app.logger.warning(f"[{hostname}] iperf3 ritorna codice {returncode}")
        throughput = parse_iperf_output(stdout)
    result = {
        "experiment_id": experiment_id,
        "hostname": hostname,
        "ip": ip,
        "protocol": protocol,
        "bitrate": str(bitrate),
        "throughput": throughput,
        "start_time": start_time,
        "end_time": end_time,
        "duration": duration
    }
    save_result(result)
    app.logger.info(f"[{hostname}] completato -> {throughput} Mbps")
    return result

def run_experiment_sequence(host_configs, experiment_id):
    app.logger.info(f"Avvio esperimento {experiment_id}")
    with state_lock:
        experiment_state["running"] = True
        experiment_state["current_experiment_id"] = experiment_id
        experiment_state["start_time"] = datetime.now().isoformat()
        experiment_state["results"].clear()
        experiment_state["active_hosts"].clear()
    iperf_proc = start_iperf_server()
    with state_lock:
        experiment_state["iperf_server_process"] = iperf_proc
    if iperf_proc is None:
        app.logger.error("Server iperf non disponibile: esco")
        with state_lock:
            experiment_state["running"] = False
        return
    try:
        active_hosts = [h for h in sorted(host_configs.keys()) if h not in EXCLUDED_HOSTS and h in HOSTS_CONFIG]
        total_hosts = len(active_hosts)
        if total_hosts == 0:
            app.logger.warning("Nessun host valido per esperimento")
            return
        total_experiment_duration = total_hosts * EXPERIMENT_DURATION_PER_HOST
        threads = []
        for i, hostname in enumerate(active_hosts):
            cfg = host_configs[hostname]
            start_delay = i * EXPERIMENT_DURATION_PER_HOST
            traffic_duration = total_experiment_duration - start_delay
            ip = HOSTS_CONFIG.get(hostname, "0.0.0.0")
            def make_task(h, ip, cfg, dur, delay):
                def task():
                    try:
                        res = run_traffic_test(h, ip, cfg.get("protocol", "TCP"), cfg.get("bitrate", "1M"), dur, experiment_id, delay)
                        if res:
                            with state_lock:
                                experiment_state["results"].append(res)
                    except Exception as e:
                        app.logger.error(f"Errore task {h}: {e}")
                return task
            task_fn = make_task(hostname, ip, cfg, traffic_duration, start_delay)
            t = threading.Thread(target=task_fn, name=f"traffic_{hostname}", daemon=True)
            t.start()
            threads.append(t)
            with state_lock:
                experiment_state["active_hosts"].append(hostname)
            app.logger.info(f"Scheduled {hostname}: start {start_delay}s dur {traffic_duration}s")
        for t in threads:
            t.join(timeout=total_experiment_duration + 30)
            if t.is_alive():
                app.logger.warning(f"Thread {t.name} ancora vivo dopo timeout")
    except Exception as e:
        app.logger.error(f"Errore durante sequenza esperimento: {e}")
    finally:
        stop_iperf_server(iperf_proc)
        with state_lock:
            experiment_state["running"] = False
            experiment_state["active_hosts"].clear()
            experiment_state["iperf_server_process"] = None
        app.logger.info(f"Esperimento {experiment_id} terminato")

# Flask API
@app.route("/start_experiment", methods=["POST"])
def start_experiment():
    with state_lock:
        if experiment_state["running"]:
            return jsonify({"error": "Esperimento già in corso"}), 409
    data = request.get_json()
    if not data or "hosts" not in data:
        return jsonify({"error": "Devi fornire 'hosts' con configurazioni"}), 400
    host_configs = data["hosts"]
    for h, cfg in host_configs.items():
        if h in EXCLUDED_HOSTS:
            continue
        if h not in HOSTS_CONFIG:
            return jsonify({"error": f"Host {h} non valido"}), 400
        proto = cfg.get("protocol", "").upper()
        if proto not in ("TCP", "UDP"):
            return jsonify({"error": f"Protocollo non valido per {h} (TCP/UDP)"}), 400
        if "bitrate" not in cfg:
            return jsonify({"error": f"Bitrate mancante per {h}"}), 400
    experiment_id = f"exp_{int(time.time())}"
    t = threading.Thread(target=run_experiment_sequence, args=(host_configs, experiment_id), name="experiment_runner", daemon=True)
    t.start()
    return jsonify({"status": "started", "experiment_id": experiment_id}), 202

@app.route("/experiment_status", methods=["GET"])
def experiment_status():
    with state_lock:
        return jsonify({
            "running": experiment_state["running"],
            "current_experiment_id": experiment_state["current_experiment_id"],
            "active_hosts": list(experiment_state["active_hosts"]),
            "start_time": experiment_state["start_time"],
            "results_count": len(experiment_state["results"])
        })

@app.route("/results", methods=["GET"])
def get_results():
    experiment_id = request.args.get("experiment_id")
    try:
        if os.path.exists(JSON_RESULTS):
            with open(JSON_RESULTS, "r") as f:
                data = json.load(f)
        else:
            data = []
        if experiment_id:
            data = [r for r in data if r.get("experiment_id") == experiment_id]
        return jsonify(data)
    except Exception as e:
        app.logger.error(f"/results error: {e}")
        return jsonify({"error": "Errore accesso JSON"}), 500

@app.route("/results/current", methods=["GET"])
def get_current_results():
    with state_lock:
        return jsonify({"experiment_id": experiment_state["current_experiment_id"], "results": list(experiment_state["results"])})

@app.route("/hosts", methods=["GET"])
def list_hosts():
    available = {h: ip for h, ip in HOSTS_CONFIG.items() if h not in EXCLUDED_HOSTS}
    return jsonify({"hosts": available, "excluded": list(EXCLUDED_HOSTS)})

@app.route("/stop_experiment", methods=["POST"])
def stop_experiment():
    with state_lock:
        if not experiment_state["running"]:
            return jsonify({"error": "Nessun esperimento in corso"}), 400
        experiment_state["running"] = False
        proc = experiment_state.get("iperf_server_process")
        experiment_state["iperf_server_process"] = None
    stop_iperf_server(proc)
    return jsonify({"status": "stopped"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

def signal_handler(sig, frame):
    app.logger.info("Ricevuto segnale, fermo esperimento e chiudo")
    with state_lock:
        proc = experiment_state.get("iperf_server_process")
        experiment_state["running"] = False
        experiment_state["iperf_server_process"] = None
    stop_iperf_server(proc)
    sys.exit(0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    signal.signal(signal.SIGINT, signal_handler)
    app.logger.info("Avvio Experiment Controller Flask (solo JSON, nessun DB SQLite)")
    app.run(host="0.0.0.0", port=5000, debug=False)
