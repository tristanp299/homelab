import threading
import sqlite3
import json
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scapy.all import sniff, IP, TCP, UDP, Raw
from sklearn.ensemble import IsolationForest

# Configuration file
CONFIG_PATH = "config.json"

# Global variables
traffic_log = []
bruteforce_attempts = {}
malware_signatures = []
lock = threading.Lock()

# Load configuration
def load_config():
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    global malware_signatures
    malware_signatures = [bytes(sig, "utf-8") for sig in config.get("malware_signatures", [])]
    return config

# Initialize database
def init_db():
    conn = sqlite3.connect("traffic_log.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traffic (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        source_ip TEXT,
        dest_ip TEXT,
        protocol TEXT,
        length INTEGER,
        info TEXT
    )
    """)
    conn.commit()
    conn.close()

# Log packet to database
def log_to_db(packet_data):
    conn = sqlite3.connect("traffic_log.db")
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO traffic (timestamp, source_ip, dest_ip, protocol, length, info)
    VALUES (?, ?, ?, ?, ?, ?)
    """, packet_data)
    conn.commit()
    conn.close()

# Detect malware in packets
def detect_malware(packet):
    if Raw in packet:
        payload = bytes(packet[Raw].load)
        for signature in malware_signatures:
            if signature in payload:
                return f"Malware signature matched: {signature}"
    return None

# Detect brute-force attempts
def detect_bruteforce(packet, config):
    if TCP in packet:
        src_ip = packet[IP].src
        dst_port = packet[TCP].dport
        timestamp = datetime.datetime.now()
        key = (src_ip, dst_port)

        with lock:
            if key not in bruteforce_attempts:
                bruteforce_attempts[key] = []
            bruteforce_attempts[key].append(timestamp)

            # Remove old entries
            bruteforce_attempts[key] = [t for t in bruteforce_attempts[key] if (timestamp - t).seconds < config["bruteforce_window"]]

            # Check for threshold breach
            if len(bruteforce_attempts[key]) > config["bruteforce_threshold"]:
                return f"Brute-force detected from {src_ip} on port {dst_port}"
    return None

# Process packets
def process_packet(packet):
    if IP in packet:
        config = load_config()
        timestamp = datetime.datetime.now().isoformat()
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        protocol = "TCP" if TCP in packet else "UDP" if UDP in packet else "Other"
        length = len(packet)
        info = ""

        # Malware detection
        malware_info = detect_malware(packet)
        if malware_info:
            info += malware_info + "; "

        # Brute-force detection
        bruteforce_info = detect_bruteforce(packet, config)
        if bruteforce_info:
            info += bruteforce_info + "; "

        # Log to memory and database
        packet_data = (timestamp, src_ip, dst_ip, protocol, length, info)
        with lock:
            traffic_log.append(packet_data)
        log_to_db(packet_data)

        # Print live details
        print(f"[{timestamp}] {src_ip} -> {dst_ip} | Protocol: {protocol} | Length: {length} | Info: {info}")

# Analyze traffic with ML
def analyze_traffic():
    with lock:
        if len(traffic_log) < 10:
            print("Not enough data for analysis.")
            return

        df = pd.DataFrame(traffic_log, columns=["Timestamp", "Source_IP", "Dest_IP", "Protocol", "Length", "Info"])
        feature_vector = np.array(df["Length"]).reshape(-1, 1)

    model = IsolationForest(contamination=0.1, random_state=42)
    predictions = model.fit_predict(feature_vector)
    anomalies = df[predictions == -1]

    if not anomalies.empty:
        print(f"Anomalies detected:\n{anomalies}")
        # Visualize anomalies
        plt.hist(df["Length"], bins=30, alpha=0.7, label="Packet Lengths")
        plt.scatter(anomalies.index, anomalies["Length"], color="red", label="Anomalies")
        plt.xlabel("Packet Index")
        plt.ylabel("Length")
        plt.legend()
        plt.show()

# Sniff packets
def start_sniffing(interface=None):
    print("Starting packet capture...")
    sniff(iface=interface, prn=process_packet, store=False)

# Periodic analysis
def background_analysis(interval):
    while True:
        threading.Event().wait(interval)
        analyze_traffic()

# Main function
def main():
    config = load_config()
    interface = config.get("network_interface", None)
    analysis_interval = config.get("analysis_interval", 60)

    # Initialize database
    init_db()

    # Start threads
    sniff_thread = threading.Thread(target=start_sniffing, args=(interface,))
    analysis_thread = threading.Thread(target=background_analysis, args=(analysis_interval,))
    sniff_thread.daemon = True
    analysis_thread.daemon = True
    sniff_thread.start()
    analysis_thread.start()

    try:
        sniff_thread.join()
    except KeyboardInterrupt:
        print("Stopping packet capture...")

if __name__ == "__main__":
    main()
