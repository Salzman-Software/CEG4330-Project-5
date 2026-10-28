#include "esp_camera.h"
#include <WiFi.h>
#include <ArduinoJson.h>

// WiFi Settings
#define SSID "your-ssid-here"
#define PASSWORD "your-password-here"
#define CAMERA_PORT 8000
#define JSON_PORT 8001

// Button and LED Settings
#define BUTTON_PIN 15     // Physical pin 23, button to ground
#define LED_PIN 2         // Onboard LED
#define DEBOUNCE_MS 30
#define PWM_CHANNEL 4     // LEDC channel 0 is used by the camera clock, so don't use it for the LED

// Camera Settings
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     21
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       19
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       5
#define Y2_GPIO_NUM       4
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WiFiServer cameraServer;
WiFiServer jsonServer;
WiFiClient cameraClient;
WiFiClient jsonClient;

JsonDocument json;

// Button state (debounced)
int lastReading = HIGH;
int stableReading = HIGH;
unsigned long lastChangeTime = 0;
int buttonState = 0;               // 1 = pressed, 0 = released
int buttonPresses = 0;
unsigned long buttonPressTime = 0; // millis() of the last press
unsigned long lastPressTime = 0; // millis() of the last press

// LED state
int ledState = 0;
bool pwmOn = false;

void connectToWiFi(const char* ssid, const char* password)
{
}

void startCameraServer(int port)
{
  // If we're not connected to WiFi, do nothing
  if (WiFi.status() != WL_CONNECTED) return;

  // Setup the camera settings
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // Adjust the size and quality to your liking
  // NOTE: Higher quality and size may result in slow transmissions
  config.frame_size   = FRAMESIZE_QVGA; // Size of the output image: FRAMESIZE_ + QVGA|CIF|VGA|SVGA|XGA|SXGA|UXGA
  config.jpeg_quality = 10;             // Quality of JPEG output. 0-63 lower means higher quality
  config.fb_count     = 1;

  // Initialize the camera with the settings
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK)
  {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  // Start the server and wait for clients
  cameraServer = WiFiServer(port);
  cameraServer.begin();
  Serial.println("Camera server started on port " + String(port));
}

void startJSONServer(int port)
{
}

void updateJSON()
{
  json["buttonPresses"] = buttonPresses;
  json["buttonPressTime"] = buttonPressTime;
}

void setup()
{
  // Start the serial monitor
  Serial.begin(9600);
  Serial.setTimeout(10); // Timeout is needed to continue to camera processing quickly

  // Button with internal pull up, LED off
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Connect to the SSID with PASSWORD
  connectToWiFi(SSID, PASSWORD);

  // Start the camera server
  startCameraServer(CAMERA_PORT);

  // Start the JSON server
  startJSONServer(JSON_PORT);

  // Initialize the JSON
  updateJSON();

  Serial.println("Setup complete!");
}

bool sendJSONToClient(WiFiClient client)
{
  return false;
}

bool sendImageToClient(WiFiClient client)
{
  // Get a pointer to the frame buffer of the camera
  camera_fb_t *fb = esp_camera_fb_get();

  // If the frame buffer is null (we did not get an image!)
  if (!fb)
  {
    Serial.println("Capture failed");
    return true;
  }

  // Send the frame buffer (4-byte length, then the JPEG)
  uint32_t len = fb->len;
  client.write((uint8_t*)&len, sizeof(len));
  client.write(fb->buf, fb->len);

  // Tell the camera that it can reuse this frame buffer now that we've sent it off
  esp_camera_fb_return(fb);

  return false;
}

void handleJSONFromClient(WiFiClient client)
{

}

void loop()
{
  // Check if a new camera client connected
  if (!cameraClient.connected()) cameraClient = cameraServer.accept();

  // Check if a new JSON client connected, and send it the current state
  if (!jsonClient.connected())
  {
    jsonClient = jsonServer.accept();
    if (jsonClient)
    {
      Serial.println("JSON client connected");
      sendJSONToClient(jsonClient);
    }
  }

  // If the JSON client sent us something, handle it
  if (jsonClient.connected() && jsonClient.available())
  {
    handleJSONFromClient(jsonClient);
  }

  // Send an image to the camera client
  if (cameraClient.connected()) sendImageToClient(cameraClient);
}
