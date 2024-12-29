import os
import threading
import sqlite3
import json
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, jsonify, render_template, request
from scapy.all import sniff, IP, TCP, UDP, Raw
from sklearn.ensemble import IsolationForest
from smtplib import SMTP

# Configuration
CONFIG_PATH = "config.json"
TRAFFIC_LOG_DB = "traffic_log.db"
ALERTS_LOG = "alerts.log"

# Flask app
app = Flask(__name__)

# Global variables
traffic_log = []
bruteforce_attempts = {}
lock = threading.Lock()

# Load configuration
def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

# Initialize database
def init_db():
    conn = sqlite3.connect(TRAFFIC_LOG_DB)
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
    conn = sqlite3.connect(TRAFFIC_LOG_DB)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO traffic (timestamp, source_ip, dest_ip, protocol, length, info)
    VALUES (?, ?, ?, ?, ?, ?)
    """, packet_data)
    conn.commit()
    conn.close()

# Send email alert
def send_email_alert(subject, body):
    config = load_config()
    email_config = config.get("email_alerts", {})
    if not email_config.get("enabled", False):
        return

    with SMTP(email_config["smtp_server"], email_config["smtp_port"]) as server:
        server.starttls()
        server.login(email_config["username"], email_config["password"])
        message = f"Subject: {subject}\n\n{body}"
        server.sendmail(email_config["sender"], email_config["recipient"], message)

# Block IP using iptables (Linux only)
def block_ip(ip):
    try:
        os.system(f"iptables -A INPUT -s {ip} -j DROP")
        print(f"Blocked IP: {ip}")
    except Exception as e:
        print(f"Error blocking IP {ip}: {e}")

# Detect malware
def detect_malware(packet, signatures):
    if Raw in packet:
        payload = bytes(packet[Raw].load)
        for signature in signatures:
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
                block_ip(src_ip)
                send_email_alert("Brute-Force Attack Detected", f"Source IP: {src_ip}, Port: {dst_port}")
                return f"Brute-force detected from {src_ip} on port {dst_port}"
    return None

# Process packets
def process_packet(packet):
    config = load_config()
    signatures = [bytes(sig, "utf-8") for sig in config.get("malware_signatures", [])]
    timestamp = datetime.datetime.now().isoformat()
    src_ip = packet[IP].src
    dst_ip = packet[IP].dst
    protocol = "TCP" if TCP in packet else "UDP" if UDP in packet else "Other"
    length = len(packet)
    info = ""

    # Malware detection
    malware_info = detect_malware(packet, signatures)
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

    print(f"[{timestamp}] {src_ip} -> {dst_ip} | Protocol: {protocol} | Length: {length} | Info: {info}")

# Periodic analysis with ML
def analyze_traffic():
    with lock:
        if len(traffic_log) < 10:
            return

        df = pd.DataFrame(traffic_log, columns=["Timestamp", "Source_IP", "Dest_IP", "Protocol", "Length", "Info"])
        feature_vector = np.array(df["Length"]).reshape(-1, 1)

    model = IsolationForest(contamination=0.1, random_state=42)
    predictions = model.fit_predict(feature_vector)
    anomalies = df[predictions == -1]

    if not anomalies.empty:
        print(f"Anomalies detected:\n{anomalies}")
        anomalies.to_csv(ALERTS_LOG, mode='a', header=False)

# Background analysis
def background_analysis(interval):
    while True:
        threading.Event().wait(interval)
        analyze_traffic()

# Web dashboard
@app.route("/")
def dashboard():
    conn = sqlite3.connect(TRAFFIC_LOG_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM traffic ORDER BY timestamp DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return render_template("dashboard.html", rows=rows)

@app.route("/api/traffic", methods=["GET"])
def api_traffic():
    conn = sqlite3.connect(TRAFFIC_LOG_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM traffic ORDER BY timestamp DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

# Start sniffing
def start_sniffing(interface):
    sniff(iface=interface, prn=process_packet, store=False)

# Main function
def main():
    config = load_config()
    interface = config["network_interface"]
    interval = config["analysis_interval"]

    init_db()

    sniff_thread = threading.Thread(target=start_sniffing, args=(interface,))
    analysis_thread = threading.Thread(target=background_analysis, args=(interval,))
    sniff_thread.daemon = True
    analysis_thread.daemon = True
    sniff_thread.start()
    analysis_thread.start()

    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()
