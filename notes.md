## create docker group
- [url](https://docs.docker.com/engine/install/linux-postinstall/)
- Create the `docker` group: `sudo groupadd docker`
- Add user to the `docker` group: `sudo usermod -aG docker $USER`
- Log out and log back in
- user membership is re-evaluated
- `newgrp docker`
- Verify that you can run `docker` command without `sudo`
- `docker run hello-world`