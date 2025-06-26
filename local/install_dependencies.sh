#!/bin/bash
#Date: 24th Jun 2025
set -e  # Exit on error

echo "📦 Step 1: Updating system packages..."
sudo apt update -y

echo "🎥 Step 2: Installing system dependencies (FFmpeg, V4L)..."
sudo apt install -y \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libv4l-dev \
    python3-venv \
    python3-pip

echo "🐍 Step 3: Creating Python virtual environment: local_env"
python3 -m venv --system-site-packages local_env

echo "📥 Step 4: Activating virtual environment and installing Python packages..."
cd local_env
source bin/activate
pip install --upgrade pip
pip install aiortc aiohttp av opencv-python

