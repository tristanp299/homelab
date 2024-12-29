import re
import threading
import sqlite3
from scapy.all import sniff, IP, TCP, UDP, Raw
import datetime
import json

# Configuration file path
CONFIG_PATH = "config.json"

# Global variables
malware_signatures = [
    b"malicious_payload",  # Example: Add known malware payloads
    b"suspicious_command"
]
bruteforce_attempts = {}
TRAFFIC_LOG = []
LOCK = threading.Lock()

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

# Advanced malware detection
def detect_malware(packet):
    if Raw in packet:
        payload = bytes(packet[Raw].load)
        for signature in malware_signatures:
            if signature in payload:
                print(f"** Malware Detected! Source: {packet[IP].src}, Destination: {packet[IP].dst}, Payload: {payload}")
                return True
    return False

# Brute-force attack detection
def detect_bruteforce(packet):
    if TCP in packet:
        src_ip = packet[IP].src
        dst_port = packet[TCP].dport
        timestamp = datetime.datetime.now()

        key = (src_ip, dst_port)
        with LOCK:
            if key not in bruteforce_attempts:
                bruteforce_attempts[key] = []
            bruteforce_attempts[key].append(timestamp)

        # Remove old entries beyond 1 minute
        bruteforce_attempts[key] = [t for t in bruteforce_attempts[key] if (timestamp - t).seconds < 60]

        # Trigger alert if attempts exceed threshold
        if len(bruteforce_attempts[key]) > 10:  # Threshold: 10 attempts in 1 minute
            print(f"** Brute-force Detected! Source: {src_ip}, Port: {dst_port}")
            return True
    return False

# Process packets
def process_packet(packet):
    if IP in packet:
        timestamp = datetime.datetime.now().isoformat()
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        protocol = "TCP" if TCP in packet else "UDP" if UDP in packet else "Other"
        length = len(packet)
        info = ""

        # Detect malware and brute-forcing
        is_malware = detect_malware(packet)
        is_bruteforce = detect_bruteforce(packet)

        if is_malware:
            info += "Malware detected; "
        if is_bruteforce:
            info += "Brute-force attack detected; "

        # Log packet
        packet_data = (timestamp, src_ip, dst_ip, protocol, length, info)
        with LOCK:
            TRAFFIC_LOG.append(packet_data)
        log_to_db(packet_data)

        # Print details
        print(f"[{timestamp}] {src_ip} -> {dst_ip} | Protocol: {protocol} | Length: {length} | Info: {info}")

# Packet capture
def start_sniffing(interface=None):
    print("Starting packet capture...")
    sniff(iface=interface, prn=process_packet, store=False)

# Main function
def main():
    # Load configuration
    config = load_config()
    interface = config.get("network_interface", None)

    # Initialize database
    init_db()

    # Start sniffing
    try:
        start_sniffing(interface)
    except KeyboardInterrupt:
        print("Stopping packet capture...")

if __name__ == "__main__":
    main()
