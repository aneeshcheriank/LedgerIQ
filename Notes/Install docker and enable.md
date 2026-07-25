## install docker and add user into usergroup

```Bash
# Install Docker Engine
sudo apt update
sudo apt install -y docker.io

# Start and enable the background service
sudo systemctl enable --now docker

# Ensure your user account has permission
sudo usermod -aG docker $USER
```

### Check docker

```Bash
newgrp docker
docker ps
```