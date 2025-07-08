<p align="center">
  <img src="logo.png" alt="Spotube Fetch Logo" width="300"/>
</p>

# Spotube Fetch

> **Note:** This app is only for downloading Spotify playlists, but it does so by searching for the songs on YouTube and downloading the audio from there.

A beautiful, modern desktop app to fetch and download YouTube audio for your Spotify playlists or any CSV of tracks. Designed for simplicity and elegance, inspired by Apple UI principles.

---

## Features
- 🎵 **Spotify Integration** (coming soon): Log in, pick a playlist, and fetch tracks automatically
- 📄 **Manual Mode**: Use your own CSV of tracks if you prefer
- 🎧 **Automatic Download**: Optionally download audio after fetching links
- 🖥️ **Modern UI**: Clean, Apple-like design with logo, progress bar, and log area
- 🏁 **Cross-platform**: Works on macOS, Windows, and Linux

---

## Setup

1. **Install dependencies**
   ```sh
   pip install pyqt5 pandas yt-dlp
   ```
2. **(Optional) For Spotify integration:**
   ```sh
   pip install spotipy
   ```

---

## Usage

1. **Run the app:**
   ```sh
   python spotube_app.py
   ```
2. **Export your playlist from Spotify:**
   - Go to [Exportify](https://watsonbox.github.io/exportify/), log in, and export your playlist as a CSV.
3. **In Spotube:**
   - Select your exported CSV as the input file.
   - Choose your download directory (where audio and CSVs will be saved).
   - Select your preferred audio format (Opus, FLAC, or MP3).
   - Choose the number of threads for faster downloads (default: 1).
   - Click **Start**.
4. **Watch progress and logs** in the app. Downloads and CSVs will be saved automatically in your chosen directory.

---

## Packaging as a Desktop App

To create a standalone app with icon:

1. **Install PyInstaller:**
   ```sh
   pip install pyinstaller
   ```
2. **Build the app:**
   ```sh
   pyinstaller --windowed --onefile --icon=logo.png spotube_app.py
   ```
   - On macOS: Produces `dist/spotube_app.app`
   - On Windows: Produces `dist/spotube_app.exe`
   - On Linux: Produces a binary in `dist/`

---

## Project Structure

```
Spotube-Fetch/
  logo.png
  spotube_app.py
  fetcher_core.py
  README.md
```

---

## Legal & Responsibility

This project is provided under the MIT License.

**Users are solely responsible for ensuring their use of Spotube complies with the Terms of Service of Spotify, YouTube, and any other services accessed.** The authors and contributors are not responsible for any misuse or violations of third-party service agreements. Use this tool for personal, legal purposes only. 