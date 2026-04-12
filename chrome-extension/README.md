# Viewfinder Chrome Extension

One-click YouTube video summarization from any YouTube page.

## Setup

1. Open `chrome://extensions/` in Chrome
2. Enable "Developer mode" (top right)
3. Click "Load unpacked" and select this `chrome-extension/` directory
4. Icons: replace `icon16.png`, `icon48.png`, `icon128.png` with real icons

## Configuration

Click the extension icon in the toolbar to configure:
- **Server URL**: Your Viewfinder server (default: `http://localhost:8080`)
- **API Key**: Optional, if your server has auth enabled

## Usage

1. Navigate to any YouTube video
2. Click the green "Summarize" button that appears near the video actions
3. A sidebar panel opens showing the summary

## Requirements

- A running Viewfinder server (`viewfinder --serve`)
- The server must have CORS enabled (it does by default)
