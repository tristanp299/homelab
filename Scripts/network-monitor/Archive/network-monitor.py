import threading
import sqlite3
import json
from scapy.all import sniff, IP, TCP, UDP, DNS, Raw
import datetime
import pandas as pd
from sklearn.ensemble import IsolationForest
import numpy as np

# Configuration file path
CONFIG_PATH = "config.json"

# Global variables
traffic_log = []
lock = threading.Lock()

# Load configuration
def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

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

# Insert packet into database
def log_to_db(packet_data):
    conn = sqlite3.connect("traffic_log.db")
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO traffic (timestamp, source_ip, dest_ip, protocol, length, info)
    VALUES (?, ?, ?, ?, ?, ?)
    """, packet_data)
    conn.commit()
    conn.close()

# Packet processing function
def process_packet(packet):
    global traffic_log
    if IP in packet:
        timestamp = datetime.datetime.now().isoformat()
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        protocol = "TCP" if TCP in packet else "UDP" if UDP in packet else "Other"
        length = len(packet)
        info = f"Flags: {packet[TCP].flags}" if TCP in packet else "DNS Query" if DNS in packet else "Other Protocol"

        # Append to in-memory log
        packet_data = (timestamp, src_ip, dst_ip, protocol, length, info)
        with lock:
            traffic_log.append(packet_data)

        # Log to database
        log_to_db(packet_data)

        # Print live details
        print(f"[{timestamp}] {src_ip} -> {dst_ip} | Protocol: {protocol} | Length: {length}")

# Analyze traffic using machine learning
def analyze_traffic():
    print("Performing anomaly detection...")
    with lock:
        if len(traffic_log) < 10:  # Minimum packets for analysis
            print("Not enough data for analysis.")
            return
        df = pd.DataFrame(traffic_log, columns=["Timestamp", "Source_IP", "Dest_IP", "Protocol", "Length", "Info"])
        feature_vector = np.array(df["Length"]).reshape(-1, 1)

    # Train Isolation Forest for anomaly detection
    model = IsolationForest(contamination=0.1, random_state=42)
    predictions = model.fit_predict(feature_vector)
    anomalies = df[predictions == -1]

    if not anomalies.empty:
        print(f"Detected anomalies:\n{anomalies}")
    else:
        print("No anomalies detected.")

# Monitor traffic
def start_sniffing(interface=None):
    print("Starting traffic capture...")
    sniff(iface=interface, prn=process_packet, store=False)

# Background analysis thread
def background_analyze(interval=60):
    while True:
        threading.Event().wait(interval)
        analyze_traffic()

# Main function
def main():
    # Load configuration
    config = load_config()
    interface = config.get("network_interface", None)
    analysis_interval = config.get("analysis_interval", 60)

    # Initialize database
    init_db()

    # Start threads
    sniff_thread = threading.Thread(target=start_sniffing, args=(interface,))
    analysis_thread = threading.Thread(target=background_analyze, args=(analysis_interval,))
    sniff_thread.daemon = True
    analysis_thread.daemon = True
    sniff_thread.start()
    analysis_thread.start()

    # Keep main thread alive
    try:
        sniff_thread.join()
    except KeyboardInterrupt:
        print("Stopping traffic analysis...")

if __name__ == "__main__":
    main()
