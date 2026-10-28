#!/usr/bin/env python3
"""
CEG 4330/6330 - Lab 5 Python client for the ESP32.

  - Shows the ESP32 camera feed (TCP port 8000, 4-byte little-endian length + JPEG per frame)
  - Prints every JSON message the ESP32 sends (TCP port 8001, one JSON object per line)
  - Sends JSON commands typed in this terminal:
        pwm <frequency_Hz> <duty_percent>   ->  {"frequency": ..., "dutyCycle": ...}
        <frequency_Hz> <duty_percent>       ->  same as above (shortcut)
        led on | led off                    ->  {"ledState": 1 | 0}
        send <any text>                     ->  raw line (TCP echo test)
        help, quit

Install:  pip install opencv-python
Run:      python lab5_client.py 192.168.1.50          (use the IP the ESP32 prints on Serial)
          python lab5_client.py 192.168.1.50 --no-video
Press q (or Esc) in the video window, or type quit, to exit.
"""

import argparse
import json
import socket
import struct
import threading
import time

import cv2
import numpy as np

stop_event = threading.Event()
print_lock = threading.Lock()


def log(msg=""):
    with print_lock:
        print(msg, flush=True)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed by ESP32")
        buf.extend(chunk)
    return bytes(buf)


# ---------------------------------------------------------------- JSON link
class JsonLink:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.send_lock = threading.Lock()

    def run(self):
        """Connect, read newline-delimited messages, reconnect if the link drops."""
        while not stop_event.is_set():
            try:
                sock = socket.create_connection((self.host, self.port), timeout=5)
                sock.settimeout(1.0)
                self.sock = sock
                log(f"[json] connected to {self.host}:{self.port}")
                buf = b""
                while not stop_event.is_set():
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        raise ConnectionError("connection closed by ESP32")
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self.handle_line(line.decode("utf-8", errors="replace").strip())
            except OSError as e:
                if not stop_event.is_set():
                    log(f"[json] {e}; retrying in 2 s")
            finally:
                if self.sock:
                    self.sock.close()
                self.sock = None
            stop_event.wait(2)

    def handle_line(self, line):
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"[esp32] {line}")
            return

        kind = msg.get("type") if isinstance(msg, dict) else None
        if kind == "pwmReply":
            req_f, act_f = msg.get("requestedFrequency"), msg.get("actualFrequency")
            req_d, act_d = msg.get("requestedDutyCycle"), msg.get("actualDutyCycle")
            log("[pwm reply] " + json.dumps(msg))
            if None not in (req_f, act_f, req_d, act_d):
                f_err = (act_f - req_f) / req_f * 100 if req_f else 0.0
                log(f"            frequency: requested {req_f:g} Hz, actual {act_f:.4f} Hz ({f_err:+.4f}%)")
                log(f"            duty cycle: requested {req_d:g}%, actual {act_d:.4f}% "
                    f"({act_d - req_d:+.4f} points, {msg.get('resolutionBits')}-bit timer)")
        elif kind == "state":
            log("[state] " + json.dumps(msg))
        else:
            log("[esp32] " + json.dumps(msg))

    def send_line(self, text):
        sock = self.sock
        if sock is None:
            log("[json] not connected yet")
            return
        with self.send_lock:
            try:
                sock.sendall((text + "\n").encode("utf-8"))
                log(f"[sent] {text}")
            except OSError as e:
                log(f"[json] send failed: {e}")

    def send_json(self, obj):
        self.send_line(json.dumps(obj))


# ---------------------------------------------------------------- terminal input
HELP = """Commands:
  pwm <freq_Hz> <duty_%>   e.g. pwm 1000 25
  <freq_Hz> <duty_%>       shortcut, e.g. 5000 75
  send <text>              send a raw line (echo test)
  help | quit"""


def input_loop(link):
    log(HELP)
    while not stop_event.is_set():
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        try:
            if cmd in ("quit", "exit", "q"):
                stop_event.set()
                return
            elif cmd == "help":
                log(HELP)
            elif cmd == "send" and len(parts) >= 2:
                link.send_line(line.split(None, 1)[1])
            elif cmd == "pwm" and len(parts) == 3:
                send_pwm(link, parts[1], parts[2])
            elif len(parts) == 2:
                send_pwm(link, parts[0], parts[1])
            else:
                log("Unknown command. Type help.")
        except ValueError as e:
            log(f"Invalid value: {e}")


def send_pwm(link, freq_text, duty_text):
    freq = float(freq_text)
    duty = float(duty_text)
    if freq <= 0:
        raise ValueError("frequency must be > 0")
    if not 0 <= duty <= 100:
        raise ValueError("duty cycle must be 0-100 %")
    link.send_json({"frequency": freq, "dutyCycle": duty})


# ---------------------------------------------------------------- video
def video_loop(host, port):
    window = f"ESP32 camera - {host}  (q to quit)"
    window_open = False
    while not stop_event.is_set():
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.settimeout(5)
            log(f"[video] connected to {host}:{port}")
            frames, t0, fps = 0, time.time(), 0.0
            while not stop_event.is_set():
                (length,) = struct.unpack("<I", recv_exact(sock, 4))
                if length == 0 or length > 4_000_000:
                    raise ConnectionError(f"bad frame length {length}")
                jpg = recv_exact(sock, length)
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                frames += 1
                if time.time() - t0 >= 1.0:
                    fps = frames / (time.time() - t0)
                    frames, t0 = 0, time.time()
                cv2.putText(frame, f"{fps:.1f} fps  {length / 1024:.0f} KB", (8, 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                cv2.imshow(window, frame)
                window_open = True
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    stop_event.set()
                elif cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    stop_event.set()
        except OSError as e:
            if not stop_event.is_set():
                log(f"[video] {e}; retrying in 2 s")
        finally:
            if sock:
                sock.close()
        # keep the window responsive while waiting to reconnect
        deadline = time.time() + 2
        while not stop_event.is_set() and time.time() < deadline:
            if window_open:
                cv2.waitKey(50)
            else:
                time.sleep(0.05)
    cv2.destroyAllWindows()


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description="CEG 4330/6330 Lab 5 ESP32 client")
    parser.add_argument("host", help="ESP32 IP address (printed on the Serial Monitor)")
    parser.add_argument("--video-port", type=int, default=8000)
    parser.add_argument("--json-port", type=int, default=8001)
    parser.add_argument("--no-video", action="store_true", help="JSON only, no camera window")
    args = parser.parse_args()

    link = JsonLink(args.host, args.json_port)
    threading.Thread(target=link.run, daemon=True).start()
    threading.Thread(target=input_loop, args=(link,), daemon=True).start()

    try:
        if args.no_video:
            while not stop_event.is_set():
                stop_event.wait(0.5)
        else:
            video_loop(args.host, args.video_port)  # OpenCV windows must run on the main thread
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        log("Bye.")


if __name__ == "__main__":
    main()
