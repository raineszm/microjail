# VHS Tape for microjail demo
# To render: vhs demo.tape

# Output options
Output demo.gif

# Terminal settings
Set FontSize 20
Set Width 1300
Set Height 720
Set Padding 30
Set Theme "Catppuccin Frappe"
Set WindowBar Colorful
Set TypingSpeed 60ms

Hide
Type "source .venv/bin/activate"
Enter
Type "mkdir -p /tmp/microjail-demo && cd /tmp/microjail-demo && clear"
Enter
Show

# 1. Initialize Microjail
Type "# Initialize microjail for the project"
Enter
Sleep 500ms
Type "microjail init demo-project"
Enter
Sleep 1s

# 2. Setup tmux layout cleanly
Hide
Type "tmux -f /dev/null -L demo-session new-session -d -s demo-session -- bash" Enter
Type "tmux -L demo-session set-option status off" Enter
Type "tmux -L demo-session split-window -h -- bash" Enter
Type "tmux -L demo-session select-pane -t 0" Enter
Type "tmux -L demo-session attach-session -t demo-session" Enter
Show

# Run the workload in the left pane
Type "# Start the workload inside the network-sealed microjail"
Enter
Sleep 500ms
Type `microjail run -- bash -c 'while true; do echo "Workload running..."; sleep 1; done'`
Enter
Sleep 3s

# Switch to the right pane (o goes to the next pane)
Ctrl+B
Type "o"
Sleep 1s

# 3. We are now in the right pane of tmux. Show the config
Type "eza --tree -a"
Enter
Sleep 2s
Type "# Let's inspect the active lockdown config:"
Enter
Sleep 1s
Type "cat .microjail/config.yaml"
Enter
Sleep 4s

# 4. Violate policy in the right pane by adding the network interface back
Type "# Let's violate the gate policy by adding the network interface back"
Enter
Type "# Watch the left pane: the Warden detects the violation and kills the workload!"
Enter
Type `lxc network attach workshopbr0 "demo-project-$(cat .workshop.lock)" --project "workshop.1000"`
Enter
Sleep 4s

# 6. Exit tmux and clean up
Hide
Type "tmux -L demo-session kill-session -t demo-session" Enter
Show
Sleep 1.5s
Type "clear"
Enter
Sleep 500ms
Type "# Release the lockdown and cleanup the environment"
Enter
Sleep 1.5s
Type "microjail unlock && microjail destroy"
Enter
Sleep 15
Type "eza --tree -a"
Enter
Sleep 5s
