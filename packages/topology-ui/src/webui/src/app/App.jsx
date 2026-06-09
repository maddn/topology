import React from 'react';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { useSelector } from 'react-redux';
import classNames from 'classnames';

import WebuiOne from 'features/nso/WebuiOne';
import TopologyViewer from 'features/topology/TopologyViewer';
import ConfigViewer from 'features/config/ConfigViewer';
import TerminalViewer from 'features/terminal/TerminalViewer';
import MenuSidebar from 'features/menu/MenuSidebar';
import ConfigHeaderActions from 'features/config/ConfigHeaderActions';
import DeviceTerminal from 'features/terminal/DeviceTerminal';

import { getEditMode } from 'features/topology/topologySlice';
import {
  QuerySelectionProvider
} from 'features/topology/QuerySelectionContext';

const getDeviceStatus = ({ device }) => device.provisioningStatus === 'ready'
  ? device.operationalStatus
  : device.provisioningStatus;

const getDeviceEditorKeypath = (device) => device?.keypath;

function App () {
  console.debug('App Render');

  const editMode = useSelector((state) => getEditMode(state));

  return (
    <DndProvider backend={HTML5Backend}>
      <QuerySelectionProvider
        devices={{
          selection: [
            'id',
            'definition',
            'provisioning-status',
            'operational-status'
          ],
          subscribe: true
        }}
        connections={{
          selection: [
            'igp-metric',
            'te-metric',
            'delay-metric'
          ]
        }}
      >
        <WebuiOne title="Topology">
          <MenuSidebar/>
          <div className={classNames('centre-pane', {
            'centre-pane--edit-mode': editMode
          })}>
            <TopologyViewer getDeviceStatus={getDeviceStatus}/>
            <TerminalViewer DeviceTerminal={DeviceTerminal}/>
          </div>
          <ConfigViewer
            ConfigHeaderActions={ConfigHeaderActions}
            getDeviceEditorKeypath={getDeviceEditorKeypath}
          />
        </WebuiOne>
      </QuerySelectionProvider>
    </DndProvider>
  );
}

export default App;
