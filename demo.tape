# VenomQA product demo — generates demo.gif

Output demo.gif

Set Shell "zsh"
Set FontSize 14
Set FontFamily "JetBrains Mono"
Set Width 900
Set Height 560
Set Theme "Catppuccin Mocha"
Set Padding 24
Set TypingSpeed 50ms
Set PlaybackSpeed 1.0
Set CursorBlink false

# Navigate to project
Sleep 300ms
Type "cd ~/venomQA && export PYTHONPATH=src"
Enter
Sleep 600ms

# Explain what VenomQA does using echo
Type `echo "VenomQA — finds sequence bugs no unit test will catch"`
Enter
Sleep 700ms

Type `echo "Exploring 12 actions x 60 steps against mock GitHub + Stripe..."`
Enter
Sleep 700ms

# Run the demo
Type "python3 demo.py"
Sleep 300ms
Enter

# Wait for full run to complete
Sleep 13s
