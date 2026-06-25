# VHS Tape for microjail demo
# To render: vhs demo.tape

# Output options
Output demo.webm

# Terminal settings
Set FontSize 20
Set Width 1300
Set Height 720
Set Padding 30
Set Theme "Catppuccin Frappe"
Set TypingSpeed 60ms

Hide
Type "source .venv/bin/activate"
Enter
Type "mkdir -p /tmp/microjail-demo && cd /tmp/microjail-demo && clear"
Enter
Type "tmux -f /dev/null -L demo-session new-session -d -s demo-session -- bash" Enter
Type "tmux -L demo-session set-option status off" Enter
Type "tmux -L demo-session set-option default-command bash" Enter
Type "tmux -L demo-session attach-session -t demo-session" Enter
Show

Type "# Initialize microjail for the project"
Enter
Type "microjail init demo-project"
Enter
Sleep 1s

# Run the workload in the left pane
Copy "# Start the workload inside the network-sealed microjail"
Paste
Enter
Type `microjail exec -- bash -c 'while true; do echo "Workload running..."; sleep 1; done'`
Enter
Sleep 3s

# Split the tmux pane vertically
Ctrl+B
Type `"`
Hide
Enter
Sleep 1s
Show

# 3. We are now in the right pane of tmux. Show the config
Type "eza --tree -a"
Enter
Sleep 2s
Copy "# Let's inspect the active lockdown config:"
Paste
Enter
Sleep 1s
Type "cat .microjail/config.yaml"
Enter
Sleep 4s

# 4. Violate policy in the right pane by adding the network interface back
Copy "# Let's violate the gate policy by adding the network interface back"
Paste
Enter
Copy "# Watch above: the Warden detects the violation and kills the workload!"
Paste
Enter
Copy `lxc network attach workshopbr0 "demo-project-$(cat .workshop.lock)" --project "workshop.$([[ $(whoami) != *@* ]] && whoami || id -u)"`
Paste
Enter
Sleep 5s

Ctrl+D
Sleep 100ms
Type "clear"
Enter
Sleep 500ms
Copy"# Release the lockdown and cleanup the environment"
Paste
Enter
Type "microjail unlock && microjail destroy"
Enter
Wait+Line@30s />/
Type "eza --tree -a"
Enter
Sleep 5s
Ctrl+D
