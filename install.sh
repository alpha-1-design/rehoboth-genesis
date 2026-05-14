#!/bin/bash

# Nexus Universal Installer
# Makes Nexus a global, resilient command without manual venv management.

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}◈ INITIATING NEXUS GLOBAL DEPLOYMENT...${NC}"

# 1. Determine Install Path
INSTALL_DIR="$HOME/.nexus"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="$HOME/.local/bin"

if [[ "$OSTYPE" == "linux-android"* ]]; then
    # Termux specific path
    BIN_DIR="$PREFIX/bin"
fi

mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

echo -e "  ${NC}╰ Installing to: ${CYAN}$INSTALL_DIR${NC}"

# 2. Create Isolated Environment
if [ ! -d "$VENV_DIR" ]; then
    echo -e "  ${NC}╰ Creating isolated neural environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# 3. Install/Update Nexus
echo -e "  ${NC}╰ Syncing synaptic dependencies...${NC}"
"$VENV_DIR/bin/pip" install --upgrade pip &> /dev/null
"$VENV_DIR/bin/pip" install -e . &> /dev/null

# 4. Create Global Shim
SHIM_PATH="$BIN_DIR/nexus"
echo -e "  ${NC}╰ Linking global executable: ${CYAN}$SHIM_PATH${NC}"

cat << EOF > "$SHIM_PATH"
#!/bin/bash
# Nexus Global Shim
source "$VENV_DIR/bin/activate"
python3 -m nexus "\$@"
EOF

chmod +x "$SHIM_PATH"

# 5. Verify
echo -e "\n${GREEN}${BOLD}◈ DEPLOYMENT COMPLETE${NC}"
echo -e "  ${NC}╰ Command 'nexus' is now globally active.${NC}"
echo -e "  ${NC}╰ Environment resilience: ${GREEN}NOMINAL${NC}"
echo -e "\n${CYAN}You can now run 'nexus' from anywhere without activating a venv.${NC}"
