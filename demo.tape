# VenomQA product demo — generates demo.gif
# Requirements: vhs, ffmpeg, ttyd

Output demo.gif

Set Shell "zsh"
Set FontSize 15
Set FontFamily "JetBrains Mono"
Set Width 860
Set Height 520
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms
Set PlaybackSpeed 1.0
Set CursorBlink false

# ── Opening: show what the tool does ─────────────────────────────────────────

Sleep 400ms
Type "# VenomQA finds bugs that unit tests miss"
Sleep 1.2s
Enter

Sleep 300ms
Type "# Works by exploring every sequence of API calls"
Sleep 1s
Enter

Sleep 300ms
Type "# Let's demo it against a mock GitHub + Stripe API"
Sleep 1.2s
Enter
Sleep 400ms

# ── Run the demo ──────────────────────────────────────────────────────────────

Type "python3 demo.py"
Sleep 300ms
Enter

# Wait for server startup + exploration
Sleep 7s

# ── Pause on the result ───────────────────────────────────────────────────────

Sleep 4s
