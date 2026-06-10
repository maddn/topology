import React from 'react';
import { useState, useEffect } from 'react';

import Terminal from 'features/terminal/Terminal';

import { useDevice } from 'features/topology/Icon';
import { useGetValueQuery } from 'api/data';
import { useActionMutation } from '/api/data';


function DeviceTerminal({ device, active }) {
  console.debug('Terminal Render');
  const [ consoleLoggerStopped, setConsoleLoggerStopped ] = useState('');
  const output = `Stopping console logger... ${consoleLoggerStopped}\r\n`;

  const { keypath, container: hypervisor, id } = useDevice(device) || {};
  const { data: ip } = useGetValueQuery({ keypath:
    `/topology:topologies/libvirt/hypervisor{${hypervisor}}/host` });

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
      <Terminal
        ip={ip}
        port={`160${`0${id}`.slice(-2)}`}
        keypath={keypath}
        active={active}
        history={output}
        onClose={() => action({ path: `${keypath}/console/start` })}
      /> : active ?
      <div className="terminal">
        <pre className="terminal__text">{output}</pre>
      </div> : null
  );
}

export default DeviceTerminal;
