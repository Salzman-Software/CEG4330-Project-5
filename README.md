# WiFi Camera Server — Project 5

1. Set `SSID` and `PASSWORD` at the top of `src/main.cpp`.
2. Connect a push button between GPIO 15 and GND. The internal pull-up is enabled.
3. Build and upload with PlatformIO. Open Serial Monitor at 9600 baud.
4. Connect the computer to the same WiFi network and use the ESP32 IP printed on Serial Monitor.
5. Install the Python dependencies: `python3 -m pip install opencv-python numpy`.
6. Run `python3 project5_client.py <ESP32-IP>`. Add `--no-video` for JSON only.

The button uses a 100 ms debounce interval. Each press updates and prints JSON such as `{"buttonPresses":1,"buttonPressTime":12345}`. `buttonPressTime` is milliseconds since startup when the press becomes stable. A connected Python client receives the JSON on each press and the current state when it connects.

WiFi connection attempts retry every 10 seconds using `millis()`, without `delay()`.

For a send/receive test, the ESP32 sends `test` when the JSON client connects. Type `send test` in Python to print the received text on Serial Monitor; that plain text also produces the expected JSON deserialization error. Type `pwm 1000 25` to set the LED to 1000 Hz and 25 percent duty cycle. PWM uses channel 4 with 8-bit resolution, separate from the camera clock.

Hardware operation has not been verified.
