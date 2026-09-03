# Antigravity UI & Media Guidelines

When interacting with the TalkerACR database through the **Antigravity UI** (Windows 11 or Android), specific formatting rules apply for successfully rendering and playing media files (specifically audio) natively in the chat interface. 

The desire to play audio links directly from the interface was a primary driver for migrating the operational harness from the AGY CLI (Linux) to the Antigravity UI (Windows 11).

## Rendering Audio Links (Method 3)
To ensure audio files are playable across both Windows 11 PC and Android Antigravity interfaces, you **must use direct markdown file links**.

**The Gold Standard Syntax:**
\[Click here to play audio](file:///absolute/path/to/file.mp3)\

### Anti-Patterns to Avoid:
*   **Raw HTML (\<audio>\):** Do not use HTML tags like \<audio controls>\. The Antigravity markdown renderer actively strips or sanitizes raw HTML for security, which results in the fallback error message: *" Your browser does not support the audio element.\*
*
