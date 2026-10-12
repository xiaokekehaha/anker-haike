TUNNEL_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: connect start restart status check check-access

connect:
	@sh "$(TUNNEL_DIR)connect.sh"

start:
	@mkdir -p "$(TUNNEL_DIR)../../logs"
	@launchctl bootstrap gui/$$(id -u) "$(HOME)/Library/LaunchAgents/com.haike.aws-tunnel.plist"

status:
	@launchctl print gui/$$(id -u)/com.haike.aws-tunnel | rg 'state =|pid =|last exit code ='

restart:
	@launchctl bootout gui/$$(id -u)/com.haike.aws-tunnel
	@$(MAKE) -f "$(TUNNEL_DIR)Makefile" start

check:
	@sh -n "$(TUNNEL_DIR)bootstrap.sh"
	@sh -n "$(TUNNEL_DIR)connect.sh"

check-access:
	@python3 "$(TUNNEL_DIR)test_access.py"
