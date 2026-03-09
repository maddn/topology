import paramiko


class CommandExecutionError(Exception):
    """Raised when command execution fails"""

class SshExecutor:
    """
    Maintains a persistent SSH connection to a single host.
    """

    def __init__(self, name, log, host, username, password=None):
        """
        Args:
            name: Name for logging purposes (e.g. hypervisor name)
            log: Logger instance
            host: Hypervisor hostname or IP
            username: SSH username
            password: SSH password (optional, will use SSH keys if None)
        """
        self._name = name
        self._host = host
        self._username = username
        self._password = password
        self._log = log
        self._client = None
        self._connected = False

    def connect(self):
        if self._connected and self._client:
            return

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self._log.debug(f'Establishing SSH connection to {self._host}')

        self._client.connect(
            self._host,
            username=self._username,
            password=self._password,
            timeout=10,
            look_for_keys=True if not self._password else False
        )

        self._connected = True

        self._log.debug(f'SSH connection established to {self._host}')

    def execute(self, commands, description=None):
        """
        Execute commands over persistent SSH connection.
        If executing multiple commands, it is expected they should all
        succeed. Any failures will generate a warning.
        If executing a single command (for example to check the
        existence of an interface), then a failure may be expected and will
        not generate a warning.

        Args:
            commands: Single command string or list of commands
            description: Optional description for logging

        Returns:
            Single result dict or list of result dicts:
            {
                'stdout': str,
                'stderr': str,
                'exit_code': int
            }
        """
        self.connect()  # No-op if already connected

        single_command = isinstance(commands, str)
        if single_command:
            commands = [commands]

        if self._log and description:
            self._log.info(f'[{self._name}] {description}')

        results = []
        for cmd in commands:
            if self._log:
                self._log.debug(f'[{self._name}] Executing: {cmd}')

            _, stdout, stderr = self._client.exec_command(cmd)

            # Wait for command to complete and get results
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')

            results.append({
                'stdout': stdout_data,
                'stderr': stderr_data,
                'exit_code': exit_code
            })

            if exit_code != 0 and not single_command:
                raise CommandExecutionError(
                    f'[{self._name}] Command failed (exit {exit_code}): {cmd}\n'
                    f'stderr: {stderr_data}'
                )

        return results[0] if single_command else results

    def close(self):
        if self._client:
            self._log.debug(f'Closing SSH connection to {self._host}')
            self._client.close()
            self._client = None
            self._connected = False

    def __del__(self):
        self.close()
