# VenomQA product demo — generates demo.gif

Output demo.gif

Set Shell "zsh"
Set FontSize 14
Set FontFamily "JetBrains Mono"
Set Width 900
Set Height 550
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 35ms
Set PlaybackSpeed 1.0
Set CursorBlink false

# ── Navigate to project and set env ──────────────────────────────────────────
Sleep 300ms

Type "cd ~/venomQA && export PYTHONPATH=src"
Enter
Sleep 500ms

# ── Comments to set the scene ─────────────────────────────────────────────────
Type "# VenomQA: finds bugs that unit tests miss"
Enter
Sleep 800ms

Type "# Explores every sequence of API calls, checks invariants after each step"
Enter
Sleep 800ms

Type "# Demo: mock GitHub + Stripe APIs with 2 planted bugs"
Enter
Sleep 1s

# ── Run ───────────────────────────────────────────────────────────────────────
Type "python3 demo.py"
Sleep 400ms
Enter

# Wait for servers to start + full exploration to complete (~8s)
Sleep 12s
