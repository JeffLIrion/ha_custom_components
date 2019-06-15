#!/bin/bash

# input_number
rm -rf input_number
mkdir input_number
wget -O input_number/__init__.py https://raw.githubusercontent.com/home-assistant/home-assistant/dev/homeassistant/components/input_number/__init__.py
wget -O input_number/manifest.json https://raw.githubusercontent.com/home-assistant/home-assistant/dev/homeassistant/components/input_number/manifest.json
wget -O input_number/services.yaml https://raw.githubusercontent.com/home-assistant/home-assistant/dev/homeassistant/components/input_number/services.yaml
