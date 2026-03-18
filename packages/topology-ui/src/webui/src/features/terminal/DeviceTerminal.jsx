import React from 'react';
import { useState, useEffect } from 'react';

import TelnetClient from './TelnetClient';

import { useDevice } from '../topology/Icon';
import { useGetValueQuery } from 'api/data';
import { useActionMutation } from '/api/data';


function Terminal({ device, active }) {
  console.debug('Terminal Render');
  const [ consoleLoggerStopped, setConsoleLoggerStopped ] = useState('');
  const output = `Stopping console logger... ${consoleLoggerStopped}\r\n`;

  const { keypath, hypervisor, id } = useDevice(device) || {};
  const { data: ip } = useGetValueQuery(
    `/topology:topologies/libvirt/hypervisor{${hypervisor}}/host`);

  const [ action ] = useActionMutation();
  const stopConsoleLogger = async() => {
    const { data } = await action({ path: `${keypath}/console/stop` });
    setConsoleLoggerStopped(data);
  };

  useEffect(() => {
    if (keypath) {
      stopConsoleLogger();
      return () => action({ path: `${keypath}/console/start` });
    }
  }, [] );

  return (
    (ip && consoleLoggerStopped != '') ?
      <TelnetClient
        ip={ip}
        port={`160${`0${id}`.slice(-2)}`}
        keypath={keypath}
        active={active}
        history={output}
      /> : active ?
      <div className="terminal">
        <pre className="terminal__telnet">{output}</pre>
      </div> : null
  );
}

export default Terminal;
