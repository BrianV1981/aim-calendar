# Antigravity UI & Media Guidelines

When interacting with the A.I.M. Calendar database through the **Antigravity UI** (Windows 11 or Android), specific formatting rules apply for successfully rendering and playing media files (specifically audio) natively in the chat interface.

The desire to play audio links directly from the interface was a primary driver for migrating the operational harness from the AGY CLI (Linux) to the Antigravity UI (Windows 11).

## Rendering Audio Links (Method 3)
To ensure audio files are playable across both Windows 11 PC and Android Antigravity interfaces, you **must use direct markdown file links**:

```markdown
[Click here to play audio](file:///absolute/path/to/file.mp3)
```

### Anti-Patterns to Avoid
*   **Raw HTML (`<audio>`):** Do not use HTML tags like `<audio controls>`. The Antigravity markdown renderer strips or sanitizes raw HTML for security, resulting in the fallback error message: *"Your browser does not support the audio element."*
*   **Raw `.amr` Links:** Standard browser audio players do not natively decode `.amr` files. Always convert `.amr` recordings to `.mp3` via `ffmpeg` before linking them for UI playback.
